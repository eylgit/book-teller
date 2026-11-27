"""Tests of the two routes of a run: start one, and ask how far it is.

They call the app in memory, and hand it a fake "ask the model": no model
is asked, and no network is used. Most need the database of the tests: see
conftest.py.

The app is made by make_app, and its parts are handed in there:

    make_app(settings=..., engine=..., ask=...)

A part that is not handed in is made from the environment variables when a
request first needs it. So a test can leave one out and see what the app
does without it.

The test client sends a request and waits for the answer. It also waits for
the background task of that request. So when "post" returns here, the run
is already done. In the real app the answer leaves first.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from book_teller.check_step import Flag, Flags, Kind
from book_teller.database import make_engine
from book_teller.main import check_the_key, make_app, same_key
from book_teller.model_call import ModelCallError, Reason
from book_teller.runs import new_run, read_run
from book_teller.settings import DatabaseSettings, RunSettings
from book_teller.tables import Status
from fake_ask import FLAGS, SCRIPT, FakeAsk

CHAPTER = "Habit is a second nature.\n\nIn most cases people mean a bad habit."

# The owner's key of the tests. Not a real key of anything.
KEY = "the-owner-key-of-the-tests"
RIGHT_KEY = {"Authorization": f"Bearer {KEY}"}
WRONG_KEY = {"Authorization": "Bearer not-the-key"}
SETTINGS = RunSettings(owner_key=KEY)

# A flag whose quote is not in the chapter: the guard marks it.
MADE_UP = Flag(
    sentence=1,
    kind=Kind.WRONG_FACT,
    paragraph=1,
    quote="Habit is a third nature.",
    reason="The script says second.",
)


def client_for(
    engine: Engine, ask: FakeAsk, settings: RunSettings = SETTINGS
) -> TestClient:
    """The app with its three parts handed in, and a client that calls it."""
    return TestClient(make_app(settings=settings, engine=engine, ask=ask))


def count_of_runs(engine: Engine) -> int:
    with engine.connect() as connection:
        count = connection.scalar(text("SELECT count(*) FROM runs"))
    assert isinstance(count, int)
    return count


# ---- Starting a run. ----


def test_the_right_key_and_a_chapter_start_a_run(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    # 202: "accepted". The work is not done when the answer leaves.
    assert response.status_code == 202
    run_id = response.json()["id"]
    run = read_run(database, run_id)
    assert run is not None
    # The chapter is saved as it came.
    assert run.chapter == CHAPTER


def test_a_finished_run_is_read_with_its_script_its_faults_and_its_sums(
    database: Engine,
) -> None:
    ask = FakeAsk(flags=Flags(flags=[MADE_UP, *FLAGS.flags]))
    client = client_for(database, ask)
    run_id = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY).json()[
        "id"
    ]

    response = client.get(f"/runs/{run_id}", headers=RIGHT_KEY)

    assert response.status_code == 200
    run = response.json()
    assert run["id"] == run_id
    assert run["status"] == "done"
    assert run["failure"] is None
    assert run["script"] == SCRIPT.sentences
    # Each fault in the checker's order, with the guard's answer: proven, or
    # what is wrong with it.
    assert run["faults"] == [
        {
            "sentence": 1,
            "kind": "wrong_fact",
            "paragraph": 1,
            "quote": "Habit is a third nature.",
            "reason": "The script says second.",
            "found_in": 0,
            "proven": False,
            "problems": ["quote_not_found"],
        },
        {
            "sentence": 2,
            "kind": "wrong_strength",
            "paragraph": 1,
            "quote": "in most cases",
            "reason": "The script says always.",
            # The checker named paragraph 1. The guard found the quote in 2.
            "found_in": 2,
            "proven": True,
            "problems": [],
        },
    ]
    assert run["tokens_in"] == 300
    assert run["tokens_out"] == 130
    assert run["thinking_tokens"] == 70
    assert run["model_seconds"] == pytest.approx(4.0)
    # The chapter can be long, and the reader has it already.
    assert "chapter" not in run


def test_a_fault_on_a_sentence_that_does_not_exist_is_read_with_that_problem(
    database: Engine,
) -> None:
    no_sentence = FLAGS.flags[0].model_copy(update={"sentence": 9})
    client = client_for(database, FakeAsk(flags=Flags(flags=[no_sentence])))
    run_id = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY).json()[
        "id"
    ]

    fault = client.get(f"/runs/{run_id}", headers=RIGHT_KEY).json()["faults"][0]

    assert fault["proven"] is False
    assert fault["problems"] == ["no_such_sentence"]


# ---- The owner's key. ----


@pytest.mark.parametrize(
    "headers",
    [
        {},
        WRONG_KEY,
        # The right key, sent in a way that is not "Bearer".
        {"Authorization": KEY},
        {"Authorization": f"Basic {KEY}"},
        {"Authorization": "Bearer "},
    ],
)
def test_without_the_right_key_no_run_starts(
    database: Engine, headers: dict[str, str]
) -> None:
    ask = FakeAsk()
    client = client_for(database, ask)

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=headers)

    # 401: "who are you?" The header says which kind of key is wanted.
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert count_of_runs(database) == 0
    assert ask.asked == []


@pytest.mark.parametrize("sent", [{}, RIGHT_KEY, {"Authorization": "Bearer "}])
def test_an_app_with_no_key_set_up_starts_no_run_whatever_is_sent(
    database: Engine, sent: dict[str, str]
) -> None:
    # The app must never fall open: no key set up means "nobody may", not
    # "everybody may".
    ask = FakeAsk()
    client = client_for(database, ask, RunSettings(owner_key=None))

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=sent)

    # 503: the service is not ready. The fault is on our side.
    assert response.status_code == 503
    assert count_of_runs(database) == 0
    assert ask.asked == []


def test_two_keys_are_the_same_only_when_every_letter_is() -> None:
    assert same_key(KEY, KEY)
    assert not same_key(KEY + "x", KEY)
    assert not same_key(KEY[:-1], KEY)
    assert not same_key("", KEY)
    # A letter outside ASCII is compared too, and is no error.
    assert same_key("clé", "clé")
    assert not same_key("clé", "cle")


def test_reading_a_run_needs_the_key_too(database: Engine) -> None:
    client = client_for(database, FakeAsk())
    run_id = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY).json()[
        "id"
    ]

    for headers in ({}, WRONG_KEY):
        response = client.get(f"/runs/{run_id}", headers=headers)

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        # Nothing of the run is in the answer.
        assert SCRIPT.sentences[0] not in response.text


def test_without_the_key_the_answer_does_not_tell_which_runs_exist(
    database: Engine,
) -> None:
    client = client_for(database, FakeAsk())

    response = client.get("/runs/999", headers=WRONG_KEY)

    # 401, not 404: the key is checked before the run is looked for.
    assert response.status_code == 401


def test_an_app_with_no_key_set_up_lets_nobody_read(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)
    client = client_for(database, FakeAsk(), RunSettings(owner_key=None))

    response = client.get(f"/runs/{run_id}", headers=RIGHT_KEY)

    assert response.status_code == 503


def test_no_answer_of_the_app_holds_the_owners_key(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    started = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)
    answers = [
        started,
        client.get(f"/runs/{started.json()['id']}", headers=RIGHT_KEY),
        client.get("/runs/999", headers=RIGHT_KEY),
        client.post("/runs", json={"chapter": CHAPTER}, headers=WRONG_KEY),
        client.post("/runs", json={"chapter": ""}, headers=RIGHT_KEY),
        client.get("/"),
    ]

    for answer in answers:
        assert KEY not in answer.text
        assert KEY not in str(answer.headers)


# ---- The limit on the pasted text. ----


@pytest.mark.parametrize("chapter", ["", "   ", "\n\n \t\n"])
def test_an_empty_chapter_starts_no_run(database: Engine, chapter: str) -> None:
    ask = FakeAsk()
    client = client_for(database, ask)

    response = client.post("/runs", json={"chapter": chapter}, headers=RIGHT_KEY)

    # 422: the request was understood, and its content cannot be used.
    assert response.status_code == 422
    assert count_of_runs(database) == 0
    assert ask.asked == []


def test_a_request_with_no_chapter_at_all_starts_no_run(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.post("/runs", json={"text": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 422
    assert count_of_runs(database) == 0


def test_a_chapter_of_5000_words_passes(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.post("/runs", json={"chapter": "word " * 5000}, headers=RIGHT_KEY)

    assert response.status_code == 202


def test_a_chapter_of_5001_words_is_refused_and_the_answer_names_the_limit(
    database: Engine,
) -> None:
    ask = FakeAsk()
    client = client_for(database, ask)

    response = client.post("/runs", json={"chapter": "word " * 5001}, headers=RIGHT_KEY)

    assert response.status_code == 422
    assert "5,000 words" in response.json()["detail"]
    assert count_of_runs(database) == 0
    assert ask.asked == []


def test_a_chapter_of_few_words_and_too_many_characters_is_refused(
    database: Engine,
) -> None:
    # One endless "word" would pass a limit that counts only words.
    ask = FakeAsk()
    client = client_for(database, ask)

    passes = client.post("/runs", json={"chapter": "a" * 40_000}, headers=RIGHT_KEY)
    refused = client.post("/runs", json={"chapter": "a" * 40_001}, headers=RIGHT_KEY)

    assert passes.status_code == 202
    assert refused.status_code == 422
    assert "40,000 characters" in refused.json()["detail"]
    assert count_of_runs(database) == 1


# ---- The cap of the day. ----


def test_when_the_cap_of_the_day_is_reached_no_run_starts(database: Engine) -> None:
    ask = FakeAsk()
    client = client_for(database, ask, RunSettings(owner_key=KEY, runs_a_day=2))
    new_run(database, CHAPTER)
    new_run(database, CHAPTER)

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    # 429: "too many requests".
    assert response.status_code == 429
    assert "2 runs" in response.json()["detail"]
    assert count_of_runs(database) == 2
    assert ask.asked == []


def test_one_run_below_the_cap_the_run_starts(database: Engine) -> None:
    client = client_for(database, FakeAsk(), RunSettings(owner_key=KEY, runs_a_day=2))
    new_run(database, CHAPTER)

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 202
    # And that run was the last of the day.
    again = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)
    assert again.status_code == 429


def test_the_runs_of_an_earlier_day_do_not_count(database: Engine) -> None:
    client = client_for(database, FakeAsk(), RunSettings(owner_key=KEY, runs_a_day=1))
    old = new_run(database, CHAPTER)
    with database.begin() as connection:
        connection.execute(
            text(
                "UPDATE runs SET created_at = now() - interval '25 hours' "
                "WHERE id = :id"
            ),
            {"id": old},
        )

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 202


def test_a_cap_of_0_refuses_every_run(database: Engine) -> None:
    client = client_for(database, FakeAsk(), RunSettings(owner_key=KEY, runs_a_day=0))

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 429
    assert count_of_runs(database) == 0


# ---- An app that is not set up. ----


def test_without_the_settings_of_the_model_no_run_starts(
    database: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No "ask the model" is handed in, so the app makes the real one from
    # the environment variables, and those are not there.
    monkeypatch.delenv("BOOK_TELLER_MODEL_ENDPOINT", raising=False)
    monkeypatch.delenv("BOOK_TELLER_MODEL_DEPLOYMENT", raising=False)
    client = TestClient(make_app(settings=SETTINGS, engine=database))

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 503
    # No row: a run that can never be done must not stay "waiting".
    assert count_of_runs(database) == 0


def test_without_the_settings_of_the_database_the_app_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOOK_TELLER_DATABASE_HOST", raising=False)
    ask = FakeAsk()
    client = TestClient(make_app(settings=SETTINGS, ask=ask))

    started = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)
    read = client.get("/runs/1", headers=RIGHT_KEY)

    assert started.status_code == 503
    assert read.status_code == 503
    assert ask.asked == []


def test_a_database_that_cannot_be_reached_is_a_503_without_its_address() -> None:
    # An address that does not exist. Making the engine opens no connection;
    # the first statement fails.
    nowhere = make_engine(
        DatabaseSettings(host="no-such-host.invalid", name="x", user="y")
    )
    ask = FakeAsk()
    client = TestClient(make_app(settings=SETTINGS, engine=nowhere, ask=ask))

    try:
        started = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)
        read = client.get("/runs/1", headers=RIGHT_KEY)
    finally:
        nowhere.dispose()

    for response in (started, read):
        assert response.status_code == 503
        assert response.json() == {"detail": "The database gave an error."}
        # The words of the library hold the address. They stay inside.
        assert "no-such-host" not in response.text
    assert ask.asked == []


def test_the_app_starts_and_shows_its_page_with_nothing_set_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The image alone, with no setting: part 1 of the smoke test.
    for name in (
        "BOOK_TELLER_OWNER_KEY",
        "BOOK_TELLER_DATABASE_HOST",
        "BOOK_TELLER_MODEL_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    client = TestClient(make_app())

    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
    assert client.post("/runs", json={"chapter": CHAPTER}).status_code == 503


# ---- Reading a run. ----


def test_a_number_that_no_run_has_answers_404(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.get("/runs/999", headers=RIGHT_KEY)

    assert response.status_code == 404


def test_a_number_that_is_no_number_answers_422(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.get("/runs/seventeen", headers=RIGHT_KEY)

    assert response.status_code == 422


def test_a_run_that_waits_is_read_with_no_script_yet(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)
    client = client_for(database, FakeAsk())

    run = client.get(f"/runs/{run_id}", headers=RIGHT_KEY).json()

    assert run["status"] == "waiting"
    assert run["script"] is None
    assert run["faults"] == []
    assert run["failure"] is None


def test_a_run_whose_checker_fails_is_read_as_failed_with_its_reason(
    database: Engine,
) -> None:
    # "no permission" gets no second try, so the test does not wait.
    error = ModelCallError(Reason.NO_PERMISSION, "the long words of the library")
    client = client_for(database, FakeAsk(fail_always={Flags: error}))

    started = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)
    response = client.get(f"/runs/{started.json()['id']}", headers=RIGHT_KEY)

    # The start was accepted: the failure came after the answer.
    assert started.status_code == 202
    run = response.json()
    assert run["status"] == "failed"
    assert run["failure"] == "no permission"
    # The writer had answered, and its cost is kept.
    assert run["tokens_in"] == 100
    assert run["tokens_out"] == 50
    # The reason alone. The words of the library can be very long.
    assert "the long words of the library" not in response.text
    saved = read_run(database, started.json()["id"])
    assert saved is not None
    assert saved.status is Status.FAILED


# ---- What the review of this task found. ----


@pytest.mark.parametrize("empty", ["", "   "])
@pytest.mark.parametrize("sent", [None, "Bearer", "Bearer ", "Bearer    "])
def test_the_check_of_the_key_never_takes_an_empty_key_of_the_app(
    empty: str, sent: str | None
) -> None:
    # read_run_settings turns an empty key into "no key". The check must be
    # safe without that, too: an empty key is "right" for an empty one.
    with pytest.raises(HTTPException) as refused:
        check_the_key(RunSettings(owner_key=empty), sent)

    assert refused.value.status_code == 503


@pytest.mark.parametrize(
    "body",
    [
        {"chapter": ""},
        {"chapter": "word " * 5001},
        {"text": "no chapter at all"},
        {"chapter": 17},
    ],
)
def test_the_key_is_checked_before_the_body_is_looked_at(
    database: Engine, body: dict[str, object]
) -> None:
    # A stranger learns "401", and nothing about what a good request holds.
    client = client_for(database, FakeAsk())

    for headers in ({}, WRONG_KEY):
        response = client.post("/runs", json=body, headers=headers)

        assert response.status_code == 401
        # FastAPI's own answer to a wrong body repeats the body. Not here.
        assert "chapter" not in response.text


def test_the_key_is_checked_before_the_cap_of_the_day(database: Engine) -> None:
    client = client_for(database, FakeAsk(), RunSettings(owner_key=KEY, runs_a_day=0))

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=WRONG_KEY)

    # 401, not 429: a stranger does not learn that the cap is reached.
    assert response.status_code == 401


def test_the_key_is_checked_before_the_number_of_the_run_is_looked_at(
    database: Engine,
) -> None:
    client = client_for(database, FakeAsk())

    assert client.get("/runs/seventeen", headers=WRONG_KEY).status_code == 401
    assert client.get("/runs/seventeen").status_code == 401


def test_an_app_with_no_key_set_up_says_so_whatever_the_request_holds(
    database: Engine,
) -> None:
    client = client_for(database, FakeAsk(), RunSettings(owner_key=None))

    assert client.post("/runs", json={"text": "x"}).status_code == 503
    assert client.get("/runs/seventeen").status_code == 503


def test_a_wrong_key_is_not_repeated_in_the_answer(database: Engine) -> None:
    client = client_for(database, FakeAsk())

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=WRONG_KEY)

    assert "not-the-key" not in response.text
    assert "not-the-key" not in str(response.headers)


def test_a_chapter_with_a_nul_character_starts_no_run(database: Engine) -> None:
    # PostgreSQL takes this character in no text. Without the check, the
    # database would raise an error in the middle of the request.
    ask = FakeAsk()
    client = client_for(database, ask)

    response = client.post(
        "/runs", json={"chapter": "A chapter.\x00"}, headers=RIGHT_KEY
    )

    assert response.status_code == 422
    assert count_of_runs(database) == 0
    assert ask.asked == []


def test_a_wrong_setting_is_named_in_the_log_and_not_in_the_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # No settings are handed in, so the app reads them from the environment.
    monkeypatch.setenv("BOOK_TELLER_OWNER_KEY", KEY)
    monkeypatch.setenv("BOOK_TELLER_RUNS_A_DAY", "twenty")
    client = TestClient(make_app(ask=FakeAsk()))

    response = client.post("/runs", json={"chapter": CHAPTER}, headers=RIGHT_KEY)

    assert response.status_code == 503
    assert response.json() == {"detail": "The app is not set up."}
    # Whoever runs the app finds the cause in the log.
    assert "BOOK_TELLER_RUNS_A_DAY" in caplog.text
    assert KEY not in caplog.text


def test_an_error_of_the_database_leaves_a_line_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    nowhere = make_engine(
        DatabaseSettings(host="no-such-host.invalid", name="x", user="y")
    )
    client = TestClient(make_app(settings=SETTINGS, engine=nowhere, ask=FakeAsk()))

    try:
        response = client.get("/runs/1", headers=RIGHT_KEY)
    finally:
        nowhere.dispose()

    assert response.status_code == 503
    assert "The database gave an error" in caplog.text
