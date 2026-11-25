r"""Tell one chapter: run the steps of an episode, with the real model.

Started by hand. It makes REAL calls, which cost money: two for one run, and
more when a step is tried again. The cost that it prints leaves out a try
that failed. From the folder "backend":

    PYTHONPATH=src uv run --env-file .env \
        python -m book_teller.tell CHAPTER_FILE

It prints the script, the faults that the checker flagged, and what each
step cost. The faults that the guard could not prove are printed apart, each
with its problem. The login is the one of the Azure CLI; no key is used.

With "--picture" it asks no model: it prints the graph as a diagram.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from book_teller.check_step import Flag, numbered_script
from book_teller.episode import Ask, picture, run_episode
from book_teller.model_call import (
    ModelAnswer,
    ModelCallError,
    ask_model,
    azure_login,
    make_model,
)
from book_teller.settings import SettingsError, read_model_settings


def tell(chapter: str, ask: Ask, out: TextIO) -> int:
    """Run the graph once and print what came out. Returns the exit code."""
    try:
        state = run_episode(chapter, ask)
    except ModelCallError as error:
        out.write(f"FAILED: {error}\n")
        return 1

    out.write("THE SCRIPT\n\n")
    out.write(numbered_script(state["script"]) + "\n")

    # The guard has checked every flag. A flag is proven when its sentence
    # exists and its quote is in the chapter.
    proven = [checked for checked in state["checked"] if checked.proven]
    not_proven = [checked for checked in state["checked"] if not checked.proven]
    out.write(
        f"\nTHE FLAGS: {len(state['checked'])}, "
        f"of them not proven: {len(not_proven)}\n\n"
    )
    for checked in proven:
        out.write(_first_line(checked.flag))
        # The paragraph where the guard found the quote.
        out.write(f'  the book, P{checked.found_in}: "{checked.flag.quote}"\n')
    if not_proven:
        out.write("\nNOT PROVEN\n\n")
    for checked in not_proven:
        flag = checked.flag
        out.write(_first_line(flag))
        # The quote and the paragraph as the checker gave them. A flag that
        # is not proven is printed so, whatever its problem is.
        out.write(f'  the checker\'s quote, P{flag.paragraph}: "{flag.quote}"\n')
        problems = ", ".join(problem.value for problem in checked.problems)
        out.write(f"  the problem: {problems}\n")

    out.write("\nTHE COST\n\n")
    out.write(
        f"{'step':<8}{'tokens in':>10}{'tokens out':>12}"
        f"{'of them thinking':>18}{'seconds':>9}\n"
    )
    for cost in state["costs"]:
        out.write(
            f"{cost.step:<8}{cost.tokens_in:>10}{cost.tokens_out:>12}"
            f"{cost.thinking_tokens:>18}{cost.seconds:>9.1f}\n"
        )
    return 0


def _first_line(flag: Flag) -> str:
    where = f"S{flag.sentence}" if flag.sentence else "no sentence"
    return f"- {where}, {flag.kind.value}: {flag.reason}\n"


def ask_with(model: ChatOpenAI) -> Ask:
    """The real "ask the model": ask_model, with the model already inside."""

    def ask[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        return ask_model(model, instructions, text, shape)

    return ask


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "chapter", nargs="?", type=Path, help="a text file that holds one chapter"
    )
    parser.add_argument(
        "--picture",
        action="store_true",
        help="print the graph as a Mermaid diagram, and ask no model",
    )
    args = parser.parse_args(arguments)

    if args.picture:
        sys.stdout.write(picture())
        return 0
    if args.chapter is None:
        parser.error("name the file that holds the chapter")

    try:
        chapter = args.chapter.read_text(encoding="utf-8")
    except OSError as error:
        sys.stdout.write(f"ERROR: the chapter cannot be read: {error}\n")
        return 1
    try:
        settings = read_model_settings()
    except SettingsError as error:
        sys.stdout.write(f"ERROR: {error}\n")
        return 1

    model = make_model(settings, azure_login())
    return tell(chapter, ask_with(model), sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
