"""The two tables of the database, each written as a class.

SQLAlchemy, the ORM, maps a table to a class and a row to an object. The
words of this file:

- Mapped[str]: a column that holds text and is NOT NULL.
  Mapped[str | None]: the column may be NULL.
- mapped_column(...): what the type alone cannot say, such as the SQL type,
  a default or a foreign key.
- server_default: the database fills the value in, like DEFAULT in SQL.

These classes do not make the tables. The migrations do, in the folder
"migrations", as plain SQL. A test compares the two, so that they cannot
drift apart.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from book_teller.check_step import Kind


class Status(StrEnum):
    """How far a run is."""

    WAITING = "waiting"
    WRITING = "writing"
    CHECKING = "checking"
    DONE = "done"
    FAILED = "failed"


def _one_of(column: str, values: type[StrEnum]) -> str:
    """The text of a CHECK: the column holds one of the values of the enum."""
    listed = ", ".join(f"'{value.value}'" for value in values)
    return f"{column} IN ({listed})"


class Base(DeclarativeBase):
    """SQLAlchemy's base class. Every class of a table is built on it."""


class Run(Base):
    """One run: a chapter, and what became of it."""

    __tablename__ = "runs"
    __table_args__ = (CheckConstraint(_one_of("status", Status), "runs_status_check"),)

    # The database counts the id up by itself, and refuses one that is
    # handed in.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, server_default=Status.WAITING.value)
    chapter: Mapped[str] = mapped_column(Text)
    # The script, as a JSON list of its sentences. NULL until the writer has
    # answered. "none_as_null": a missing script is NULL in SQL, not the
    # JSON word "null".
    script: Mapped[list[str] | None] = mapped_column(JSONB(none_as_null=True))
    # Why a failed run failed, in the words of the model call, such as
    # "timeout". NULL for every other status.
    failure: Mapped[str | None] = mapped_column(Text)
    # The sums over the model calls of the run that answered.
    tokens_in: Mapped[int] = mapped_column(Integer, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, server_default="0")
    thinking_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    model_seconds: Mapped[float] = mapped_column(Double, server_default="0")
    # "timezone=True" makes the type timestamptz: one moment, whatever the
    # time zone of the reader is.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # When the run became "done" or "failed".
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fault(Base):
    """One fault that the checker reported in a run, with the guard's answer."""

    __tablename__ = "faults"
    __table_args__ = (
        CheckConstraint(_one_of("kind", Kind), "faults_kind_check"),
        # Also the index for "the faults of this run": PostgreSQL makes no
        # index for a foreign key by itself.
        UniqueConstraint("run_id", "position", name="faults_run_id_position_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("runs.id", ondelete="CASCADE", name="faults_run_id_fkey"),
    )
    # The place in the checker's list, from 1.
    position: Mapped[int] = mapped_column(Integer)
    # What the checker said. Sentence 0: no sentence holds the fault.
    sentence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    paragraph: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    # What the guard said. found_in: the paragraph that holds the quote, or 0
    # for none.
    found_in: Mapped[int] = mapped_column(Integer)
    sentence_exists: Mapped[bool] = mapped_column(Boolean)
