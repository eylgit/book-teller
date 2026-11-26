"""Save a run in the database, and read it back.

Every function here is one transaction: all of its statements happen, or
none. A function gets the engine (see database.py) and opens a session,
SQLAlchemy's word for one piece of work with the database.

What is read back is a plain object, SavedRun. It holds no connection, so
the caller can keep it as long as it likes.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from book_teller.check_step import Kind
from book_teller.episode import Cost
from book_teller.guard import CheckedFlag, Problem
from book_teller.tables import Fault, Run, Status


class NoSuchRun(LookupError):
    """No run has this number."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"There is no run {run_id}.")


@dataclass(frozen=True)
class SavedFault:
    """One fault of a saved run: what the checker said, and what the guard said."""

    # The place in the checker's list, from 1.
    position: int
    sentence: int
    kind: Kind
    paragraph: int
    quote: str
    reason: str
    # The paragraph where the guard found the quote. 0: nowhere.
    found_in: int
    sentence_exists: bool

    @property
    def proven(self) -> bool:
        # Not stored: it follows from the two answers of the guard.
        return self.found_in > 0 and self.sentence_exists


@dataclass(frozen=True)
class SavedRun:
    """A run as the database holds it, with its faults in the checker's order."""

    id: int
    status: Status
    chapter: str
    # None until the writer has answered.
    script: list[str] | None
    # Why a failed run failed. None for every other status.
    failure: str | None
    tokens_in: int
    tokens_out: int
    thinking_tokens: int
    model_seconds: float
    created_at: datetime
    finished_at: datetime | None
    faults: list[SavedFault]


def new_run(engine: Engine, chapter: str) -> int:
    """Save a new run, which waits. Returns its number."""
    with Session(engine) as session, session.begin():
        run = Run(chapter=chapter)
        session.add(run)
        # "flush" sends the INSERT now, so that the database gives the id.
        # The transaction ends when this block ends.
        session.flush()
        return run.id


def set_status(engine: Engine, run_id: int, status: Status) -> None:
    """Say how far the run is."""
    with Session(engine) as session, session.begin():
        _update(session, run_id, status=status.value)


def save_result(
    engine: Engine,
    run_id: int,
    script: Sequence[str],
    checked: Sequence[CheckedFlag],
    costs: Sequence[Cost],
) -> None:
    """Save what a finished run made. The run is then done."""
    with Session(engine) as session, session.begin():
        _update(
            session,
            run_id,
            status=Status.DONE.value,
            script=list(script),
            # The clock of the database, as for created_at.
            finished_at=func.now(),
            **_sums(costs),
        )
        session.add_all(
            Fault(
                run_id=run_id,
                position=position,
                sentence=each.flag.sentence,
                kind=each.flag.kind.value,
                paragraph=each.flag.paragraph,
                quote=each.flag.quote,
                reason=each.flag.reason,
                found_in=each.found_in,
                sentence_exists=Problem.NO_SUCH_SENTENCE not in each.problems,
            )
            for position, each in enumerate(checked, 1)
        )


def mark_failed(
    engine: Engine, run_id: int, reason: str, costs: Sequence[Cost] = ()
) -> None:
    """Save that the run failed, why, and what it cost up to there."""
    with Session(engine) as session, session.begin():
        _update(
            session,
            run_id,
            status=Status.FAILED.value,
            failure=reason,
            finished_at=func.now(),
            **_sums(costs),
        )


def read_run(engine: Engine, run_id: int) -> SavedRun | None:
    """The run with its faults, or None when no run has this number."""
    with Session(engine) as session:
        run = session.get(Run, run_id)
        if run is None:
            return None
        faults = session.scalars(
            select(Fault).where(Fault.run_id == run_id).order_by(Fault.position)
        ).all()
        return SavedRun(
            id=run.id,
            status=Status(run.status),
            chapter=run.chapter,
            script=run.script,
            failure=run.failure,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            thinking_tokens=run.thinking_tokens,
            model_seconds=run.model_seconds,
            created_at=run.created_at,
            finished_at=run.finished_at,
            faults=[
                SavedFault(
                    position=fault.position,
                    sentence=fault.sentence,
                    kind=Kind(fault.kind),
                    paragraph=fault.paragraph,
                    quote=fault.quote,
                    reason=fault.reason,
                    found_in=fault.found_in,
                    sentence_exists=fault.sentence_exists,
                )
                for fault in faults
            ],
        )


def _update(session: Session, run_id: int, **values: object) -> None:
    """One UPDATE of one run. Raises NoSuchRun when the run is not there."""
    # "RETURNING id" gives the id of each changed row back: none means that
    # no row has this id.
    changed = session.scalar(
        update(Run).where(Run.id == run_id).values(**values).returning(Run.id)
    )
    if changed is None:
        raise NoSuchRun(run_id)


def _sums(costs: Sequence[Cost]) -> dict[str, object]:
    return {
        "tokens_in": sum(cost.tokens_in for cost in costs),
        "tokens_out": sum(cost.tokens_out for cost in costs),
        "thinking_tokens": sum(cost.thinking_tokens for cost in costs),
        "model_seconds": sum(cost.seconds for cost in costs),
    }
