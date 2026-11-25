r"""Tell one chapter: run the two steps, write and check, with the real model.

Started by hand. It makes REAL calls, which cost money: two for one run, and
more when a step is tried again. From the folder "backend":

    PYTHONPATH=src uv run --env-file .env \
        python -m book_teller.tell CHAPTER_FILE

It prints the script, the faults that the checker flagged, and what each
step cost. The login is the one of the Azure CLI; no key is used.

With "--picture" it asks no model: it prints the graph as a diagram.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel

from book_teller.check_step import numbered_script
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

    out.write(f"\nTHE FLAGS: {len(state['flags'])}\n\n")
    for flag in state["flags"]:
        where = f"S{flag.sentence}" if flag.sentence else "no sentence"
        out.write(f"- {where}, {flag.kind.value}: {flag.reason}\n")
        out.write(f'  the book, P{flag.paragraph}: "{flag.quote}"\n')

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
        settings = read_model_settings()
    except SettingsError as error:
        sys.stdout.write(f"ERROR: {error}\n")
        return 1

    model = make_model(settings, azure_login())

    def ask[Shape: BaseModel](
        instructions: str, text: str, shape: type[Shape]
    ) -> ModelAnswer[Shape]:
        """ask_model of model_call.py, with the model already inside."""
        return ask_model(model, instructions, text, shape)

    return tell(args.chapter.read_text(encoding="utf-8"), ask, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
