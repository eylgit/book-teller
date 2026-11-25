"""The check step: what the checker is told, and the shape of its answer.

The checker is the second of the two steps of an episode. It gets the
chapter and the script, both numbered, and lists every fault that it finds
in the script. The graph that runs the step is in episode.py.
"""

import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field


class Kind(StrEnum):
    """The six kinds of fault. The model answers with the name, as text."""

    WRONG_FACT = "wrong_fact"
    WRONG_CONCEPT = "wrong_concept"
    WRONG_EXAMPLE = "wrong_example"
    WRONG_CONCLUSION = "wrong_conclusion"
    WRONG_STRENGTH = "wrong_strength"
    LEFT_OUT = "left_out"


# What each kind means. The instructions below are built from this table, so
# the model is never told of a kind that the code does not have.
MEANING = {
    Kind.WRONG_FACT: "a wrong fact",
    Kind.WRONG_CONCEPT: "a concept explained wrongly",
    Kind.WRONG_EXAMPLE: "an example that does not match the idea",
    Kind.WRONG_CONCLUSION: "a conclusion the author did not draw",
    Kind.WRONG_STRENGTH: (
        'a word that is too strong or too weak, such as "may" turned into "will"'
    ),
    Kind.LEFT_OUT: "an important point of the author left out",
}

_KINDS = "\n".join(f"- {kind.value}: {MEANING[kind]};" for kind in Kind)

INSTRUCTIONS = f"""You check the script of a podcast episode against the chapter \
of the book that it tells.
The script must say what the author said. It is a short telling, so it may \
leave out details.

Find every fault in the script. There are six kinds of fault:
{_KINDS}

Every sentence of the script starts with its number, such as [S7].
Every paragraph of the chapter starts with its number, such as [P3].

Flag only real faults. If the script has no fault, give an empty list."""


class Flag(BaseModel):
    """One fault that the checker found in the script.

    Each description travels to the model inside the request, as a part of
    the JSON schema. So the meaning of a field stands beside the field.
    """

    sentence: int = Field(
        description=(
            "The number of the sentence of the script that holds the fault. "
            "Give 0 for a fault of the kind left_out."
        )
    )
    kind: Kind = Field(description="The kind of the fault.")
    paragraph: int = Field(
        description="The number of the paragraph of the chapter that proves the fault."
    )
    quote: str = Field(
        description=(
            "The words of that paragraph that prove the fault, copied word for word."
        )
    )
    reason: str = Field(description="One short sentence that says what is wrong.")


class Flags(BaseModel):
    """The shape of the checker's answer: a list of faults."""

    flags: list[Flag] = Field(
        description="Every fault in the script. Empty when there is none."
    )


def paragraphs(chapter: str) -> list[str]:
    """The paragraphs of the chapter, in order. Paragraph 1 is the first item.

    A blank line ends a paragraph. A line that holds only spaces counts as
    blank. Inside a paragraph, a line break becomes a space.

    The numbering below and the guard both use this function, so "P7" is the
    same paragraph for the checker and for the guard.
    """
    return [
        " ".join(block.split())
        for block in re.split(r"\n\s*\n", chapter)
        if block.strip()
    ]


def numbered_texts(chapter: str, sentences: Sequence[str]) -> str:
    """The chapter and the script as one text, with every part numbered."""
    chapter_text = "\n\n".join(
        f"[P{number}] {paragraph}"
        for number, paragraph in enumerate(paragraphs(chapter), 1)
    )
    script_text = numbered_script(sentences)
    return f"THE CHAPTER\n\n{chapter_text}\n\nTHE SCRIPT\n\n{script_text}"


def numbered_script(sentences: Sequence[str]) -> str:
    """The script, one sentence on a line, each with its number."""
    return "\n".join(
        f"[S{number}] {sentence}" for number, sentence in enumerate(sentences, 1)
    )
