"""The guard: plain code that checks every flag of the checker. No model.

The checker is a model, and a model can make a quote up. For each flag the
guard answers one question: is it proven? A flag is proven when its sentence
number points at a sentence of the script, and its quote is in the chapter.

The same input gives the same answer every time. The guard changes no flag,
drops none and raises no error: a flag that is not proven stays in the
result, with its problems as the mark.

What the guard cannot know: whether a quote that is in the chapter really
shows that the script is wrong.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from book_teller.check_step import Flag, Kind, paragraphs


class Problem(StrEnum):
    """Why a flag is not proven."""

    NO_SUCH_SENTENCE = "no_such_sentence"
    QUOTE_NOT_FOUND = "quote_not_found"


@dataclass(frozen=True)
class CheckedFlag:
    """The guard's line for one flag."""

    # The flag as the checker gave it.
    flag: Flag
    # The number of the paragraph that holds the quote. 0: no paragraph does.
    # It can differ from flag.paragraph: the checker may name a wrong number
    # beside a real quote.
    found_in: int
    problems: tuple[Problem, ...]

    @property
    def proven(self) -> bool:
        return not self.problems


def check_flags(
    chapter: str, sentences: Sequence[str], flags: Sequence[Flag]
) -> list[CheckedFlag]:
    """One line for each flag, in the order of the flags."""
    # Cleaned once, not once for each flag.
    cleaned = [clean(paragraph) for paragraph in paragraphs(chapter)]
    return [_check(flag, len(sentences), cleaned) for flag in flags]


def clean(text: str) -> str:
    """A text made ready for the comparison.

    Small letters, plain quote marks, no underscores (a plain text marks
    italics with them), and one space where there were several or a line
    break. A model often changes these when it copies, and none of them
    changes what the words say.

    Everything else must match letter for letter. So a true quote with
    another kind of dash is not found. That is the price of never passing a
    quote that is only close to the chapter.
    """
    for curly, plain in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(curly, plain)
    return " ".join(text.replace("_", "").lower().split())


def _check(flag: Flag, sentence_count: int, cleaned: Sequence[str]) -> CheckedFlag:
    problems: list[Problem] = []
    if not _sentence_exists(flag, sentence_count):
        problems.append(Problem.NO_SUCH_SENTENCE)
    found_in = _find(flag.quote, flag.paragraph, cleaned)
    if found_in == 0:
        problems.append(Problem.QUOTE_NOT_FOUND)
    return CheckedFlag(flag=flag, found_in=found_in, problems=tuple(problems))


def _sentence_exists(flag: Flag, sentence_count: int) -> bool:
    # 0 stands for "no sentence". Only a point that was left out has none.
    if flag.sentence == 0:
        return flag.kind == Kind.LEFT_OUT
    return 1 <= flag.sentence <= sentence_count


def _find(quote: str, named: int, cleaned: Sequence[str]) -> int:
    """The number of the paragraph that holds the quote, or 0 for none.

    The paragraph that the checker named is looked at first. After it, every
    paragraph from the first on. A quote must lie inside one paragraph.
    """
    wanted = clean(quote)
    # An empty text is "in" every text. It proves nothing.
    if not wanted:
        return 0
    if 1 <= named <= len(cleaned) and wanted in cleaned[named - 1]:
        return named
    for number, paragraph in enumerate(cleaned, 1):
        if wanted in paragraph:
            return number
    return 0
