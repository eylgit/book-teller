"""Tests of the guard: plain code that checks every flag of the checker.

No model and no HTTP. The guard gets the chapter, the script and the flags,
and says for each flag whether it is proven.
"""

import pytest

from book_teller.check_step import Flag, Kind
from book_teller.guard import CheckedFlag, Problem, check_flags

# Three paragraphs. The first marks italics with underscores, the second has
# curly quote marks and a line break in the middle of a sentence.
CHAPTER = (
    "Habit is a _second_ nature.\n"
    "\n"
    "In most cases people mean a “bad habit”,\n"
    "when they use the word.\n"
    "\n"
    "The nervous system grows to the modes in which it has been exercised."
)

SCRIPT = ["The first sentence.", "The second sentence.", "The third sentence."]


def flag(
    quote: str,
    sentence: int = 1,
    kind: Kind = Kind.WRONG_FACT,
    paragraph: int = 1,
) -> Flag:
    """A flag as the checker gives it. Only the quote must be named."""
    return Flag(
        sentence=sentence,
        kind=kind,
        paragraph=paragraph,
        quote=quote,
        reason="The script says something else.",
    )


def check(one_flag: Flag) -> CheckedFlag:
    """The guard's line for one flag."""
    (checked,) = check_flags(CHAPTER, SCRIPT, [one_flag])
    return checked


def test_a_quote_that_is_in_the_chapter_word_for_word_is_proven() -> None:
    checked = check(flag("The nervous system grows to the modes", paragraph=3))

    assert checked.proven
    assert checked.problems == ()
    assert checked.found_in == 3


@pytest.mark.parametrize(
    ("quote", "paragraph"),
    [
        # Capital letters, and the underscores of italics.
        ("habit is a SECOND nature", 1),
        # Plain quote marks where the chapter has curly ones.
        ('people mean a "bad habit"', 2),
        # A space where the chapter has a line break.
        ("habit”, when they use the word", 2),
        # Several spaces where the chapter has one.
        ("In   most  cases", 2),
    ],
)
def test_a_quote_that_differs_only_in_small_things_is_proven(
    quote: str, paragraph: int
) -> None:
    checked = check(flag(quote, paragraph=paragraph))

    assert checked.proven
    assert checked.found_in == paragraph


def test_a_quote_with_one_word_changed_is_not_proven() -> None:
    checked = check(flag("The nervous system shrinks to the modes", paragraph=3))

    assert not checked.proven
    assert checked.problems == (Problem.QUOTE_NOT_FOUND,)
    assert checked.found_in == 0


@pytest.mark.parametrize("quote", ["", "  \n ", "_"])
def test_a_quote_with_nothing_in_it_is_not_found(quote: str) -> None:
    # An empty text is "in" every text. It must not count as a proof. The
    # third quote is empty after the clean-up, which takes underscores out.
    checked = check(flag(quote))

    assert checked.problems == (Problem.QUOTE_NOT_FOUND,)
    assert checked.found_in == 0


def test_a_quote_in_another_paragraph_than_the_checker_named_is_proven() -> None:
    # The guard searches every paragraph. It keeps the number of the one
    # that really holds the quote, and the checker's number stays in the flag.
    checked = check(flag("The nervous system grows", paragraph=1))

    assert checked.proven
    assert checked.found_in == 3
    assert checked.flag.paragraph == 1


def test_when_two_paragraphs_hold_the_quote_the_named_one_is_kept() -> None:
    # "habit" is in paragraphs 1 and 2.
    assert check(flag("habit", paragraph=2)).found_in == 2
    # When the named paragraph does not hold it, the first one that does.
    assert check(flag("habit", paragraph=3)).found_in == 1


def test_a_quote_that_runs_from_one_paragraph_into_the_next_is_not_found() -> None:
    checked = check(flag("a second nature. In most cases"))

    assert checked.problems == (Problem.QUOTE_NOT_FOUND,)


@pytest.mark.parametrize("sentence", [1, 3])
def test_the_first_and_the_last_sentence_of_the_script_exist(sentence: int) -> None:
    assert check(flag("Habit is a", sentence=sentence)).proven


@pytest.mark.parametrize("sentence", [4, 99, -1])
def test_a_sentence_number_outside_the_script_is_a_problem(sentence: int) -> None:
    # The script has three sentences. The quote is a real one.
    checked = check(flag("Habit is a", sentence=sentence))

    assert not checked.proven
    assert checked.problems == (Problem.NO_SUCH_SENTENCE,)
    # The quote was still looked for, and found.
    assert checked.found_in == 1


def test_sentence_0_is_right_only_for_a_point_that_was_left_out() -> None:
    left_out = check(flag("Habit is a", sentence=0, kind=Kind.LEFT_OUT))
    wrong_fact = check(flag("Habit is a", sentence=0, kind=Kind.WRONG_FACT))

    assert left_out.proven
    assert wrong_fact.problems == (Problem.NO_SUCH_SENTENCE,)


def test_a_point_that_was_left_out_may_also_name_a_sentence() -> None:
    # The checker may name the sentence beside the gap.
    assert check(flag("Habit is a", sentence=2, kind=Kind.LEFT_OUT)).proven


def test_a_flag_with_both_problems_names_both() -> None:
    checked = check(flag("These words are made up.", sentence=4))

    assert checked.problems == (Problem.NO_SUCH_SENTENCE, Problem.QUOTE_NOT_FOUND)


def test_no_flags_give_an_empty_result() -> None:
    assert check_flags(CHAPTER, SCRIPT, []) == []


def test_the_result_has_one_line_for_each_flag_in_order_and_unchanged() -> None:
    flags = [
        flag("Habit is a", sentence=1),
        flag("These words are made up.", sentence=2),
        flag("The nervous system", sentence=3, paragraph=3),
    ]
    before = [one.model_copy() for one in flags]

    result = check_flags(CHAPTER, SCRIPT, flags)

    # A flag that is not proven stays in the list. Nothing is dropped.
    assert [checked.flag for checked in result] == before
    assert flags == before
    assert [checked.proven for checked in result] == [True, False, True]
