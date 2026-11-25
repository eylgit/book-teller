"""Tests of the script that runs the two steps by hand. No real call."""

import io
from pathlib import Path

import pytest

from book_teller.check_step import Flags
from book_teller.model_call import ModelCallError, Reason
from book_teller.tell import main, tell
from fake_ask import FakeAsk

CHAPTER = "Habit is a second nature.\n\nIn most cases people mean a bad habit."


def test_a_run_prints_the_script_the_flags_and_the_cost_of_each_step() -> None:
    out = io.StringIO()

    assert tell(CHAPTER, FakeAsk(), out) == 0

    printed = out.getvalue()
    # The script of the fake writer, numbered as the checker saw it.
    assert "[S1] James starts with the word habit." in printed
    assert "[S2] Habits can be good." in printed
    # The one flag of the fake checker.
    assert "wrong_strength" in printed
    assert "in most cases" in printed
    assert "The script says always." in printed
    # One line of cost for each step: tokens in, tokens out, thinking, seconds.
    lines = printed.splitlines()
    write_line = next(line for line in lines if line.startswith("write"))
    check_line = next(line for line in lines if line.startswith("check"))
    assert write_line.split() == ["write", "100", "50", "10", "1.5"]
    assert check_line.split() == ["check", "200", "80", "60", "2.5"]


def test_a_call_that_fails_prints_one_line_and_ends_with_1() -> None:
    out = io.StringIO()
    ask = FakeAsk(
        fail_always={Flags: ModelCallError(Reason.NO_PERMISSION, "status 403")}
    )

    assert tell(CHAPTER, ask, out) == 1

    assert out.getvalue().splitlines() == ["FAILED: no permission: status 403"]


def test_without_the_settings_the_script_names_what_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chapter = tmp_path / "chapter.txt"
    chapter.write_text(CHAPTER, encoding="utf-8")
    monkeypatch.delenv("BOOK_TELLER_MODEL_ENDPOINT", raising=False)

    assert main([str(chapter)]) == 1
    assert "BOOK_TELLER_MODEL_ENDPOINT" in capsys.readouterr().out
