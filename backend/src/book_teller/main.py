"""The web app: the page, the health address, and the two routes of a run.

    POST /runs           start a run: the chapter is in the body
    GET  /runs/{number}  how far is this run, and what did it make?

Both routes of a run need the owner's key, in the header
"Authorization: Bearer <the key>".

The web app does the run itself: it saves the run, answers at once with the
number, and does the work after the answer has left. A known limit: when
the app stops in the middle of a run, the run stays "writing" or "checking"
for ever.
"""

import logging
import secrets
import threading
from pathlib import Path
from typing import Annotated

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from book_teller import runs
from book_teller.database import engine_from_environment
from book_teller.episode import Ask
from book_teller.guard import Problem
from book_teller.job import ask_from_environment, do_run
from book_teller.settings import RunSettings, SettingsError, read_run_settings

STATIC_FOLDER = Path(__file__).parent / "static"

# Where this file writes a line when something goes wrong. Python's own
# logging prints such a line to the output of the program, which Azure
# keeps.
log = logging.getLogger(__name__)

# The limit on the pasted text. A longer text is refused before it costs
# anything. Words are the pieces between spaces. The limit on characters
# stops one endless "word".
MAX_WORDS = 5_000
MAX_CHARACTERS = 40_000


class NewRun(BaseModel):
    """The body of the request that starts a run."""

    chapter: str


class Started(BaseModel):
    """The answer to a start: the number of the new run."""

    id: int


class FaultAnswer(BaseModel):
    """One fault of a run: what the checker said, and what the guard said."""

    # What the checker said. Sentence 0: no sentence holds the fault.
    sentence: int
    kind: str
    paragraph: int
    quote: str
    reason: str
    # What the guard said. found_in: the paragraph of the chapter that holds
    # the quote, or 0 for none. problems: why the fault is not proven.
    found_in: int
    proven: bool
    problems: list[str]


class RunAnswer(BaseModel):
    """A run as the page gets it. The chapter is left out: it can be long."""

    id: int
    # waiting, writing, checking, done or failed.
    status: str
    # Why a failed run failed. None for every other status.
    failure: str | None
    # None until the run is done.
    script: list[str] | None
    faults: list[FaultAnswer]
    tokens_in: int
    tokens_out: int
    thinking_tokens: int
    model_seconds: float


class Parts:
    """What the routes need: the settings of a run, the database, the model.

    A part that was handed in is used as it is: the tests do that. A part
    that was not is made from the environment variables when a request
    first needs it, and then kept. So the app starts with nothing set up,
    and says "503" only when a request needs what is missing.
    """

    def __init__(
        self, settings: RunSettings | None, engine: Engine | None, ask: Ask | None
    ) -> None:
        self._settings = settings
        self._engine = engine
        self._ask = ask
        # The routes run in several threads. The lock lets only one of them
        # make a part.
        self._lock = threading.Lock()

    def settings(self) -> RunSettings:
        with self._lock:
            if self._settings is None:
                self._settings = read_run_settings()
            return self._settings

    def engine(self) -> Engine:
        with self._lock:
            if self._engine is None:
                self._engine = engine_from_environment()
            return self._engine

    def ask(self) -> Ask:
        with self._lock:
            if self._ask is None:
                self._ask = ask_from_environment()
            return self._ask


def same_key(sent: str, key: str) -> bool:
    """Is the key that was sent the owner's key?

    "compare_digest" takes the same time for a right and for a wrong key.
    A plain "==" stops at the first letter that differs, so the time of the
    answer would tell an attacker how many letters were right. It compares
    bytes: as text it refuses a letter outside ASCII.
    """
    return secrets.compare_digest(sent.encode(), key.encode())


def check_the_key(settings: RunSettings, authorization: str | None) -> None:
    """Let the request go on only when it carries the owner's key.

    With no key set up, nobody may: the app never falls open. An empty
    key counts as no key, also here: an empty key would be "right" for a
    request that sends an empty one.
    """
    if not (settings.owner_key or "").strip():
        raise HTTPException(503, "The app has no owner's key set up.")
    assert settings.owner_key is not None
    # The header is "Bearer", a space, and the key.
    scheme, _, sent = (authorization or "").partition(" ")
    if scheme != "Bearer" or not same_key(sent.strip(), settings.owner_key):
        raise HTTPException(
            401,
            "The owner's key is missing or wrong.",
            # The usual header of a 401: which kind of key is wanted.
            headers={"WWW-Authenticate": "Bearer"},
        )


def check_the_chapter(chapter: str) -> None:
    """Refuse an empty chapter, and one that is over the limit."""
    words = len(chapter.split())
    if words == 0:
        raise HTTPException(422, "The chapter is empty.")
    # NUL, the character with the number 0. PostgreSQL takes it in no text.
    if "\x00" in chapter:
        raise HTTPException(422, "The chapter holds a NUL character.")
    if len(chapter) > MAX_CHARACTERS:
        raise HTTPException(
            422,
            f"The chapter has {len(chapter):,} characters. "
            f"The limit is {MAX_CHARACTERS:,} characters.",
        )
    if words > MAX_WORDS:
        raise HTTPException(
            422,
            f"The chapter has {words:,} words. The limit is {MAX_WORDS:,} words.",
        )


def start_run(tasks: BackgroundTasks, engine: Engine, run_id: int, ask: Ask) -> None:
    """The one place that decides how a saved run is started.

    Today: FastAPI calls do_run after the answer has left, in a thread of
    this program. With a queue, this function would send a message instead,
    and a worker would call do_run.
    """
    tasks.add_task(do_run, engine, run_id, ask)


def answer_for(run: runs.SavedRun) -> RunAnswer:
    return RunAnswer(
        id=run.id,
        status=run.status.value,
        failure=run.failure,
        script=run.script,
        faults=[
            FaultAnswer(
                sentence=fault.sentence,
                kind=fault.kind.value,
                paragraph=fault.paragraph,
                quote=fault.quote,
                reason=fault.reason,
                found_in=fault.found_in,
                proven=fault.proven,
                problems=_problems(fault),
            )
            for fault in run.faults
        ],
        tokens_in=run.tokens_in,
        tokens_out=run.tokens_out,
        thinking_tokens=run.thinking_tokens,
        model_seconds=run.model_seconds,
    )


def _problems(fault: runs.SavedFault) -> list[str]:
    """The guard's problems, from its two answers as the database holds them."""
    problems: list[str] = []
    if not fault.sentence_exists:
        problems.append(Problem.NO_SUCH_SENTENCE.value)
    if fault.found_in == 0:
        problems.append(Problem.QUOTE_NOT_FOUND.value)
    return problems


def make_app(
    settings: RunSettings | None = None,
    engine: Engine | None = None,
    ask: Ask | None = None,
) -> FastAPI:
    """Make the web app. The real app hands in nothing; a test hands in its parts."""
    parts = Parts(settings, engine, ask)

    # FastAPI can serve pages that document the API. They are off: they load
    # scripts without a checksum.
    app = FastAPI(title="Book Teller", docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(SettingsError)
    def not_set_up(request: Request, error: SettingsError) -> JSONResponse:
        # A setting is missing or wrong. Which one goes into the log, not
        # into the answer: the message can hold the wrong value.
        log.error("The app is not set up: %s", error)
        return JSONResponse({"detail": "The app is not set up."}, 503)

    @app.exception_handler(SQLAlchemyError)
    def no_database(request: Request, error: SQLAlchemyError) -> JSONResponse:
        # The words of the library stay out of the answer: they can hold the
        # address of the database. Their first line goes into the log; the
        # lines after it hold the SQL statement and its values.
        log.error("The database gave an error: %s", str(error).splitlines()[0])
        return JSONResponse({"detail": "The database gave an error."}, 503)

    def the_owner(
        authorization: Annotated[str | None, Header()] = None,
    ) -> RunSettings:
        """Let only the owner go on. FastAPI calls this before a route of a run.

        It is a "dependency": a function that a route names, and that
        FastAPI calls first, for each request of that route. FastAPI fills
        "authorization" from the header of that name. It runs before the
        body of the request is checked, so a stranger learns nothing but
        "401", whatever the request holds.
        """
        run_settings = parts.settings()
        check_the_key(run_settings, authorization)
        return run_settings

    @app.get("/")
    def page() -> FileResponse:
        """The page. The file is read on every request, so a change shows on reload."""
        return FileResponse(STATIC_FOLDER / "index.html", media_type="text/html")

    @app.get("/health")
    def health() -> dict[str, str]:
        """A machine asks this address to learn whether the app is alive."""
        return {"status": "ok"}

    # 202: "accepted". The run is saved, and its work is not done yet.
    @app.post("/runs", status_code=202)
    def start_a_run(
        body: NewRun,
        tasks: BackgroundTasks,
        run_settings: Annotated[RunSettings, Depends(the_owner)],
    ) -> Started:
        """Start a run: three guards, then a new row, then the answer.

        FastAPI fills the arguments in: "body" from the JSON of the request,
        "tasks" as the list of work to do after the answer, and
        "run_settings" as what the_owner returned. The first guard, the
        key, is the_owner: when this function starts, the key was right.
        """
        check_the_chapter(body.chapter)
        database = parts.engine()
        # The cap of the day. Every run that was started today counts.
        if runs.count_started_today(database) >= run_settings.runs_a_day:
            raise HTTPException(
                429,
                "The cap of the day is reached: "
                f"{run_settings.runs_a_day} runs a day. It starts again at "
                "midnight UTC.",
            )
        # Before the row is written: without a model, the run could never
        # be done, and would wait for ever.
        model = parts.ask()
        run_id = runs.new_run(database, body.chapter)
        start_run(tasks, database, run_id, model)
        return Started(id=run_id)

    # "dependencies": the_owner is called first, and what it returns is not
    # needed here. So the key is checked before the run is looked for, and a
    # stranger does not learn which runs exist.
    @app.get("/runs/{run_id}", dependencies=[Depends(the_owner)])
    def how_far(run_id: int) -> RunAnswer:
        """How far is this run? When it is done: the script, the faults, the sums."""
        run = runs.read_run(parts.engine(), run_id)
        if run is None:
            raise HTTPException(404, f"There is no run {run_id}.")
        return answer_for(run)

    return app


# What uvicorn serves: "uvicorn book_teller.main:app".
app = make_app()
