r"""Measure the model call: what does each thinking setting cost, in tokens and seconds?

Started by hand. It makes REAL calls, which cost money: one call for each
thinking setting that is named. From the folder "backend":

    PYTHONPATH=src uv run --env-file .env \
        python -m book_teller.measure --thinking low medium

It asks the model to check the script of the probe against its chapter, with
the instructions and the shape of the product's own check step. The login
is the one of the Azure CLI; no key is used.
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, TextIO

import httpx2

from book_teller import check_step
from book_teller.model_call import (
    ModelCallError,
    ask_model,
    azure_login,
    make_model,
)
from book_teller.settings import ModelSettings, SettingsError, read_model_settings

PROBE = Path(__file__).parents[3] / "experiments" / "2026-11-13-probe_planted_faults"


def numbered_texts(chapter_file: Path, script_file: Path) -> str:
    """The chapter and the script of two files as one text, every part numbered.

    The script file holds one sentence on a line.
    """
    sentences = [
        line.strip()
        for line in script_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return check_step.numbered_texts(
        chapter_file.read_text(encoding="utf-8"), sentences
    )


def measure(
    settings: ModelSettings,
    token_function: Callable[[], str],
    text: str,
    thinking_settings: Sequence[str],
    out: TextIO,
    http_client: httpx2.Client | None = None,
) -> None:
    """Make one call for each thinking setting, and print one line for each."""
    out.write(
        f"{'thinking':<10}{'tokens in':>10}{'tokens out':>12}"
        f"{'of them thinking':>18}{'seconds':>9}{'faults':>8}\n"
    )
    for thinking in thinking_settings:
        model = make_model(
            replace(settings, thinking=thinking), token_function, http_client
        )
        try:
            answer = ask_model(model, check_step.INSTRUCTIONS, text, check_step.Flags)
        except ModelCallError as error:
            out.write(f"{thinking:<10}FAILED: {error}\n")
            continue
        out.write(
            f"{thinking:<10}{answer.tokens_in:>10}{answer.tokens_out:>12}"
            f"{answer.thinking_tokens:>18}{answer.seconds:>9.1f}"
            f"{len(answer.parsed.flags):>8}\n"
        )


def showing_client(out: TextIO) -> httpx2.Client:
    """An HTTP client that prints each request and each answer, made short.

    It prints no header and no host: only the last part of the address, and
    the two bodies. The bodies are printed as the service sent them, so read
    the output before you paste it anywhere.
    """

    def show_request(request: httpx2.Request) -> None:
        out.write(f"\n--- THE REQUEST: {request.method} ...{request.url.path}\n")
        out.write(_short_json(request.content) + "\n")

    def show_answer(response: httpx2.Response) -> None:
        response.read()
        out.write(f"\n--- THE ANSWER: status {response.status_code}\n")
        out.write(_short_json(response.content) + "\n\n")

    return httpx2.Client(
        event_hooks={"request": [show_request], "response": [show_answer]}
    )


def _short_json(content: bytes) -> str:
    try:
        data = json.loads(content)
    except ValueError:
        return content.decode("utf-8", "replace")[:500]
    return json.dumps(_shortened(data), indent=2, ensure_ascii=False)


def _shortened(value: Any) -> Any:
    """The same data, with every long text cut to its first 60 characters."""
    if isinstance(value, str) and len(value) > 60:
        return f"{value[:60]}... ({len(value)} characters)"
    if isinstance(value, list):
        return [_shortened(item) for item in value]
    if isinstance(value, dict):
        return {key: _shortened(item) for key, item in value.items()}
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--thinking",
        nargs="+",
        default=["low"],
        metavar="SETTING",
        help="one or more thinking settings, such as: low medium",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="print each request and each answer, made short",
    )
    args = parser.parse_args(arguments)

    try:
        settings = read_model_settings()
    except SettingsError as error:
        sys.stdout.write(f"ERROR: {error}\n")
        return 1

    measure(
        settings,
        azure_login(),
        numbered_texts(PROBE / "chapter.txt", PROBE / "script.txt"),
        args.thinking,
        sys.stdout,
        showing_client(sys.stdout) if args.show else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
