"""Tests of runs.py: a run is saved and read back.

They need the database of the tests: see conftest.py.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine

from book_teller.check_step import Flag, Kind
from book_teller.episode import Cost
from book_teller.guard import CheckedFlag, Problem
from book_teller.runs import (
    NoSuchRun,
    SavedFault,
    mark_failed,
    new_run,
    read_run,
    save_result,
    set_status,
)
from book_teller.tables import Status

CHAPTER = "Habit is a second nature.\n\nIn most cases people mean a bad habit."
SCRIPT = ["James starts with the word habit.", "Habits can be good."]

# A flag that the guard found proven: its quote is in paragraph 2, though the
# checker named paragraph 1.
PROVEN = CheckedFlag(
    flag=Flag(
        sentence=2,
        kind=Kind.WRONG_STRENGTH,
        paragraph=1,
        quote="in most cases",
        reason="The script says always.",
    ),
    found_in=2,
    problems=(),
)
# A flag with both problems: no such sentence, and a quote that is nowhere.
MADE_UP = CheckedFlag(
    flag=Flag(
        sentence=7,
        kind=Kind.WRONG_FACT,
        paragraph=1,
        quote="in the year 1890",
        reason="The script names the wrong year.",
    ),
    found_in=0,
    problems=(Problem.NO_SUCH_SENTENCE, Problem.QUOTE_NOT_FOUND),
)
# A real quote beside a sentence number that does not exist.
NO_SENTENCE = CheckedFlag(
    flag=Flag(
        sentence=9,
        kind=Kind.LEFT_OUT,
        paragraph=1,
        quote="a second nature",
        reason="The script leaves this out.",
    ),
    found_in=1,
    problems=(Problem.NO_SUCH_SENTENCE,),
)

COSTS = [
    Cost(step="write", tokens_in=100, tokens_out=50, thinking_tokens=10, seconds=1.5),
    Cost(step="check", tokens_in=200, tokens_out=80, thinking_tokens=60, seconds=2.5),
]


def test_a_new_run_waits_and_holds_only_the_chapter(database: Engine) -> None:
    before = datetime.now(UTC) - timedelta(minutes=1)

    run_id = new_run(database, CHAPTER)

    run = read_run(database, run_id)
    assert run is not None
    assert run.id == run_id
    assert run.status is Status.WAITING
    assert run.chapter == CHAPTER
    assert run.script is None
    assert run.failure is None
    assert run.faults == []
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (0, 0, 0)
    assert run.model_seconds == 0
    assert run.created_at > before
    assert run.finished_at is None


def test_each_new_run_gets_a_number_of_its_own(database: Engine) -> None:
    first = new_run(database, CHAPTER)
    second = new_run(database, "Another chapter.")

    assert first != second
    other = read_run(database, second)
    assert other is not None
    assert other.chapter == "Another chapter."


def test_the_status_of_a_run_can_be_set(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)

    for status in (Status.WRITING, Status.CHECKING):
        set_status(database, run_id, status)

        run = read_run(database, run_id)
        assert run is not None
        assert run.status is status
        assert run.finished_at is None


def test_a_saved_result_is_read_back_as_it_went_in(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)

    save_result(database, run_id, SCRIPT, [MADE_UP, PROVEN, NO_SENTENCE], COSTS)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.DONE
    assert run.failure is None
    assert run.chapter == CHAPTER
    # The sentences, in their order.
    assert run.script == SCRIPT
    # The faults, in the order of the checker, each with what the checker
    # said and what the guard said.
    assert run.faults == [
        SavedFault(
            position=1,
            sentence=7,
            kind=Kind.WRONG_FACT,
            paragraph=1,
            quote="in the year 1890",
            reason="The script names the wrong year.",
            found_in=0,
            sentence_exists=False,
        ),
        SavedFault(
            position=2,
            sentence=2,
            kind=Kind.WRONG_STRENGTH,
            paragraph=1,
            quote="in most cases",
            reason="The script says always.",
            found_in=2,
            sentence_exists=True,
        ),
        SavedFault(
            position=3,
            sentence=9,
            kind=Kind.LEFT_OUT,
            paragraph=1,
            quote="a second nature",
            reason="The script leaves this out.",
            found_in=1,
            sentence_exists=False,
        ),
    ]
    # "proven" is not stored. It follows from the two answers of the guard.
    assert [fault.proven for fault in run.faults] == [False, True, False]
    # The sums over the two model calls.
    assert run.tokens_in == 300
    assert run.tokens_out == 130
    assert run.thinking_tokens == 70
    assert run.model_seconds == pytest.approx(4.0)
    assert run.finished_at is not None
    assert run.finished_at >= run.created_at


def test_letters_of_every_kind_come_back_unchanged(database: Engine) -> None:
    chapter = "“Don’t,” she said — naïvely.\n\n習慣は第二の天性である。"
    script = ["She said “don’t”.", "Habit is a second nature: 習慣."]
    curly = CheckedFlag(
        flag=Flag(
            sentence=1,
            kind=Kind.WRONG_FACT,
            paragraph=1,
            quote="“Don’t,” she said — naïvely.",
            reason="It’s the wrong speaker.",
        ),
        found_in=1,
        problems=(),
    )
    run_id = new_run(database, chapter)

    save_result(database, run_id, script, [curly], COSTS)

    run = read_run(database, run_id)
    assert run is not None
    assert run.chapter == chapter
    assert run.script == script
    assert run.faults[0].quote == "“Don’t,” she said — naïvely."
    assert run.faults[0].reason == "It’s the wrong speaker."


def test_a_result_with_no_fault_is_saved_with_an_empty_list(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)

    save_result(database, run_id, SCRIPT, [], COSTS)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.DONE
    assert run.script == SCRIPT
    assert run.faults == []


def test_a_failed_run_holds_its_reason_and_what_it_cost_so_far(
    database: Engine,
) -> None:
    run_id = new_run(database, CHAPTER)
    set_status(database, run_id, Status.CHECKING)

    # The writer answered, and the checker failed.
    mark_failed(database, run_id, "timeout", COSTS[:1])

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.FAILED
    assert run.failure == "timeout"
    assert run.script is None
    assert run.faults == []
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (100, 50, 10)
    assert run.model_seconds == pytest.approx(1.5)
    assert run.finished_at is not None


def test_a_run_can_fail_before_any_model_call_answered(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)

    mark_failed(database, run_id, "no permission")

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.FAILED
    assert run.failure == "no permission"
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (0, 0, 0)


def test_one_run_does_not_show_the_faults_of_another(database: Engine) -> None:
    first = new_run(database, CHAPTER)
    second = new_run(database, CHAPTER)
    save_result(database, first, SCRIPT, [PROVEN], COSTS)
    save_result(database, second, SCRIPT, [MADE_UP, NO_SENTENCE], COSTS)

    run = read_run(database, first)

    assert run is not None
    assert [fault.quote for fault in run.faults] == ["in most cases"]


def test_reading_a_run_that_does_not_exist_gives_nothing(database: Engine) -> None:
    assert read_run(database, 999) is None


def test_writing_to_a_run_that_does_not_exist_is_an_error(database: Engine) -> None:
    # Without an error, a result would be lost with no word.
    with pytest.raises(NoSuchRun):
        set_status(database, 999, Status.WRITING)
    with pytest.raises(NoSuchRun):
        save_result(database, 999, SCRIPT, [PROVEN], COSTS)
    with pytest.raises(NoSuchRun):
        mark_failed(database, 999, "timeout")
