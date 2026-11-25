"""Tests of the graph: write, then check, then the guard. No model and no HTTP."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from book_teller.check_step import INSTRUCTIONS as CHECK_INSTRUCTIONS
from book_teller.check_step import Flag, Flags, Kind
from book_teller.episode import RETRY, Cost, EpisodeState, picture, run_episode
from book_teller.guard import CheckedFlag, Problem
from book_teller.model_call import ModelAnswer, ModelCallError, Reason
from book_teller.write_step import INSTRUCTIONS as WRITE_INSTRUCTIONS
from book_teller.write_step import Script
from fake_ask import FLAGS, SCRIPT, FakeAsk

CHAPTER = "Habit is a\nsecond nature.\n\nIn most cases people mean a bad habit."

# The real retry rule of the graph, with one change: no wait before the
# second try, so the tests stay fast.
NO_WAIT = RETRY._replace(initial_interval=0.0, jitter=False)


def run(ask: FakeAsk) -> EpisodeState:
    """One run of the graph, from the chapter to the last state."""
    return run_episode(CHAPTER, ask, NO_WAIT)


def failure(reason: Reason) -> ModelCallError:
    return ModelCallError(reason, "the library's words")


def test_one_run_asks_the_writer_and_then_the_checker() -> None:
    ask = FakeAsk()
    run(ask)

    assert ask.shapes() == [Script, Flags]


def test_the_writer_gets_the_chapter() -> None:
    ask = FakeAsk()
    run(ask)

    writer = ask.asked[0]
    assert writer.instructions == WRITE_INSTRUCTIONS
    assert writer.text == CHAPTER


def test_the_checker_gets_the_numbered_chapter_and_the_script_of_the_writer() -> None:
    ask = FakeAsk()
    run(ask)

    checker = ask.asked[1]
    assert checker.instructions == CHECK_INSTRUCTIONS
    assert "[P1] Habit is a second nature." in checker.text
    assert "[P2] In most cases people mean a bad habit." in checker.text
    assert "[S1] James starts with the word habit." in checker.text
    assert "[S2] Habits can be good." in checker.text


def test_the_last_state_holds_the_chapter_the_script_and_the_flags() -> None:
    state = run(FakeAsk())

    assert state["chapter"] == CHAPTER
    assert state["script"] == SCRIPT.sentences
    assert state["flags"] == FLAGS.flags


def test_the_last_state_holds_the_cost_of_both_calls() -> None:
    state = run(FakeAsk())

    # The second step adds its line. It does not replace the first one's.
    assert state["costs"] == [
        Cost(
            step="write", tokens_in=100, tokens_out=50, thinking_tokens=10, seconds=1.5
        ),
        Cost(
            step="check", tokens_in=200, tokens_out=80, thinking_tokens=60, seconds=2.5
        ),
    ]


def test_a_checker_that_fails_once_is_tried_again_and_the_writer_is_not() -> None:
    ask = FakeAsk(fail_once={Flags: failure(Reason.TIMEOUT)})
    state = run(ask)

    assert ask.shapes() == [Script, Flags, Flags]
    assert state["flags"] == FLAGS.flags


def test_a_writer_that_always_fails_ends_the_run_after_two_tries() -> None:
    error = failure(Reason.SERVICE_ERROR)
    ask = FakeAsk(fail_always={Script: error})

    with pytest.raises(ModelCallError) as caught:
        run(ask)

    # The error of the step leaves the graph as it is. The checker never ran.
    assert caught.value is error
    assert ask.shapes() == [Script, Script]


def test_too_many_requests_gets_a_second_try() -> None:
    ask = FakeAsk(fail_once={Script: failure(Reason.TOO_MANY_REQUESTS)})
    run(ask)

    assert ask.shapes() == [Script, Script, Flags]


@pytest.mark.parametrize(
    "reason", [Reason.NO_PERMISSION, Reason.REFUSED, Reason.WRONG_SHAPE]
)
def test_a_failure_that_a_second_try_cannot_mend_gets_none(reason: Reason) -> None:
    ask = FakeAsk(fail_once={Flags: failure(reason)})

    with pytest.raises(ModelCallError) as caught:
        run(ask)

    assert caught.value.reason == reason
    assert ask.shapes() == [Script, Flags]


def test_a_failed_try_leaves_no_line_in_the_costs() -> None:
    state = run(FakeAsk(fail_once={Flags: failure(Reason.TIMEOUT)}))

    assert [cost.step for cost in state["costs"]] == ["write", "check"]


def test_the_retry_rule_gives_two_tries() -> None:
    # The model call makes up to three requests by itself. Two tries of a
    # node: up to six requests for one step.
    assert RETRY.max_attempts == 2


def test_the_picture_of_the_graph_shows_write_then_check_then_guard() -> None:
    drawn = picture()

    assert "__start__ --> write;" in drawn
    assert "write --> check;" in drawn
    assert "check --> guard;" in drawn
    assert "guard --> __end__;" in drawn


def test_the_last_state_holds_the_result_of_the_guard_beside_the_flags() -> None:
    state = run(FakeAsk())

    # The quote of the fake checker, "in most cases", is in paragraph 2 of
    # the chapter. The guard got the chapter of this run, and found it there.
    assert state["checked"] == [
        CheckedFlag(flag=FLAGS.flags[0], found_in=2, problems=())
    ]
    # The checker's own list is still there, as it came.
    assert state["flags"] == FLAGS.flags


def test_a_flag_with_a_made_up_quote_is_marked_and_the_run_ends_well() -> None:
    made_up = Flag(
        sentence=1,
        kind=Kind.WRONG_FACT,
        paragraph=1,
        quote="Habit is a third nature.",
        reason="The script says second.",
    )
    state = run(FakeAsk(flags=Flags(flags=[made_up, *FLAGS.flags])))

    # No error, and nothing is dropped: both flags are in the result.
    assert [checked.flag for checked in state["checked"]] == [made_up, *FLAGS.flags]
    assert state["checked"][0].problems == (Problem.QUOTE_NOT_FOUND,)
    assert state["checked"][1].proven


def test_the_guard_counts_the_sentences_of_the_writers_script() -> None:
    # The script of the fake writer has two sentences. A flag on sentence 3
    # points at nothing.
    third = FLAGS.flags[0].model_copy(update={"sentence": 3})
    state = run(FakeAsk(flags=Flags(flags=[third])))

    assert state["checked"][0].problems == (Problem.NO_SUCH_SENTENCE,)


def test_the_guard_asks_no_model_and_adds_no_line_of_cost() -> None:
    ask = FakeAsk()
    state = run(ask)

    assert ask.shapes() == [Script, Flags]
    assert [cost.step for cost in state["costs"]] == ["write", "check"]


def test_without_a_rule_handed_in_the_graph_uses_its_own_retry_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The other tests hand in a copy of the rule that does not wait. This one
    # hands in nothing, as the real code does. Only the waiting is switched off.
    waits: list[float] = []
    monkeypatch.setattr("time.sleep", waits.append)
    ask = FakeAsk(fail_always={Script: failure(Reason.NO_PERMISSION)})

    with pytest.raises(ModelCallError):
        run_episode(CHAPTER, ask)
    # Our rule gives "no permission" no second try. LangGraph's own would.
    assert ask.shapes() == [Script]

    ask = FakeAsk(fail_always={Script: failure(Reason.TIMEOUT)})
    with pytest.raises(ModelCallError):
        run_episode(CHAPTER, ask)
    # Two tries, with one wait between them.
    assert ask.shapes() == [Script, Script]
    assert len(waits) == 1


def test_an_error_that_is_not_of_the_model_call_gets_no_second_try() -> None:
    asked: list[type[BaseModel]] = []

    def broken[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        asked.append(shape)
        raise ConnectionError("not a ModelCallError")

    with pytest.raises(ConnectionError):
        run_episode(CHAPTER, broken, NO_WAIT)
    assert asked == [Script]


def test_the_picture_in_the_readme_is_the_one_that_the_library_prints() -> None:
    readme = Path(__file__).parents[2] / "README.md"

    assert picture().strip() in readme.read_text(encoding="utf-8")
