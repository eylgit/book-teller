"""The write step: what the writer is told, and the shape of its answer.

The writer is the first step of an episode. It gets one chapter
and tells it as the script of a podcast episode. The graph that runs the
step is in episode.py.
"""

from pydantic import BaseModel, Field

# About 1,300 words are under ten minutes of sound.
INSTRUCTIONS = """You write the script of one podcast episode. The episode \
tells one chapter of a book to a listener who has not read the book.

Say what the author said, in the order of the chapter. Add nothing: no fact, \
no example, no opinion and no conclusion that is not in the chapter. Keep the \
strength of the author's words: do not turn "may" into "will". It is a short \
telling, so leave out details, but keep every important point.

Write for the ear: short, plain sentences that are easy to follow when they \
are heard once. A sentence holds one idea and has at most about 25 words. \
Make clear at the start that the episode tells what the author says. After \
that, name the author only now and then: do not start sentence after sentence \
with "the author says" or "he says".

The script is about a quarter to a third as long as the chapter, and never \
longer than 1,300 words."""


class Script(BaseModel):
    """The shape of the writer's answer: the script, sentence by sentence."""

    # A list, not one long text: the checker points at a sentence by its
    # number, so the writer itself says where each sentence ends.
    sentences: list[str] = Field(
        description="The script, in order. Each item is exactly one sentence."
    )
