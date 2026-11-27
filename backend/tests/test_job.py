"""Tests of job.py: "do run number N".

do_run reads the chapter of a saved run, runs the graph, and saves how far
the run is, and then the result or the failure. It knows nothing of the web.

They need the database of the tests: see conftest.py. The model is a fake.
"""

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine

from book_teller.check_step import Flags
from book_teller.episode import RETRY
from book_teller.job import UNEXPECTED, do_run
from book_teller.model_call import ModelAnswer, ModelCallError, Reason
from book_teller.runs import NoSuchRun, new_run, read_run
from book_teller.tables import Status
from book_teller.write_step import Script
from fake_ask import FLAGS, SCRIPT, FakeAsk

CHAPTER = "Habit is a second nature.\n\nIn most cases people mean a bad habit."

# The real retry rule of the graph, with no wait before the second try.
NO_WAIT = RETRY._replace(initial_interval=0.0, jitter=False)


class WatchingAsk:
    """A fake "ask the model" that looks into the database when it is asked.

    So a test can see which status the run had at the moment the writer was
    asked, and at the moment the checker was asked.
    """

    def __init__(self, engine: Engine, run_id: int) -> None:
        self.seen: list[tuple[type[BaseModel], Status]] = []
        self._engine = engine
        self._run_id = run_id
        self._answer = FakeAsk()

    def __call__[Shape: BaseModel](
        self, instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        run = read_run(self._engine, self._run_id)
        assert run is not None
        self.seen.append((shape, run.status))
        return self._answer(instructions, text, shape)


def test_the_status_says_which_step_is_at_work(database: Engine) -> None:
    run_id = new_run(database, CHAPTER)
    ask = WatchingAsk(database, run_id)

    do_run(database, run_id, ask, NO_WAIT)

    assert ask.seen == [(Script, Status.WRITING), (Flags, Status.CHECKING)]
    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.DONE


def test_the_model_gets_the_chapter_of_the_saved_run(database: Engine) -> None:
    new_run(database, "Another chapter.")
    run_id = new_run(database, CHAPTER)
    ask = FakeAsk()

    do_run(database, run_id, ask, NO_WAIT)

    assert ask.asked[0].text == CHAPTER


def test_a_finished_run_is_saved_with_its_script_its_faults_and_its_sums(
    database: Engine,
) -> None:
    run_id = new_run(database, CHAPTER)

    do_run(database, run_id, FakeAsk(), NO_WAIT)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.DONE
    assert run.failure is None
    assert run.script == SCRIPT.sentences
    # The one flag of the fake checker, with the guard's answer: its quote
    # is in paragraph 2 of the chapter.
    assert [(fault.quote, fault.found_in, fault.proven) for fault in run.faults] == [
        (FLAGS.flags[0].quote, 2, True)
    ]
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (300, 130, 70)
    assert run.model_seconds == pytest.approx(4.0)
    assert run.finished_at is not None


def test_a_checker_that_fails_for_good_leaves_a_failed_run_with_the_writers_cost(
    database: Engine,
) -> None:
    run_id = new_run(database, CHAPTER)
    error = ModelCallError(Reason.TIMEOUT, "the library's words")

    # No error leaves do_run: a failed model call is a result, and it is saved.
    do_run(database, run_id, FakeAsk(fail_always={Flags: error}), NO_WAIT)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.FAILED
    # The reason alone, not the words of the library.
    assert run.failure == "timeout"
    assert run.script is None
    assert run.faults == []
    # The writer answered before the checker failed. Its cost is kept.
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (100, 50, 10)
    assert run.finished_at is not None


def test_a_writer_that_fails_for_good_leaves_a_failed_run_with_no_cost(
    database: Engine,
) -> None:
    run_id = new_run(database, CHAPTER)
    ask = FakeAsk(
        fail_always={Script: ModelCallError(Reason.NO_PERMISSION, "the words")}
    )

    do_run(database, run_id, ask, NO_WAIT)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.FAILED
    assert run.failure == "no permission"
    assert (run.tokens_in, run.tokens_out) == (0, 0)
    # The checker never ran.
    assert ask.shapes() == [Script]


def test_a_step_that_fails_once_and_then_answers_ends_in_a_done_run(
    database: Engine,
) -> None:
    run_id = new_run(database, CHAPTER)
    ask = FakeAsk(
        fail_once={Flags: ModelCallError(Reason.TOO_MANY_REQUESTS, "the words")}
    )

    do_run(database, run_id, ask, NO_WAIT)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.DONE
    assert ask.shapes() == [Script, Flags, Flags]


def test_a_bug_in_our_own_code_marks_the_run_as_failed(database: Engine) -> None:
    # Not a failed model call: something that nobody planned for. The run
    # must not stay "checking" for ever, and the error must not be hidden.
    run_id = new_run(database, CHAPTER)
    answers = FakeAsk()

    def broken[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        if shape is Flags:
            raise RuntimeError("a bug")
        return answers(instructions, text, shape)

    with pytest.raises(RuntimeError, match="a bug"):
        do_run(database, run_id, broken, NO_WAIT)

    run = read_run(database, run_id)
    assert run is not None
    assert run.status is Status.FAILED
    assert run.failure == UNEXPECTED
    assert run.finished_at is not None
    # The writer had answered.
    assert run.tokens_in == 100


def test_a_run_that_does_not_exist_is_an_error_and_asks_no_model(
    database: Engine,
) -> None:
    ask = FakeAsk()

    with pytest.raises(NoSuchRun):
        do_run(database, 999, ask, NO_WAIT)

    assert ask.asked == []
