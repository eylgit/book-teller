"""Tests of the script that runs the two steps by hand. No real call."""

import io
from pathlib import Path

import pytest

from book_teller.check_step import Flags
from book_teller.model_call import ModelCallError, Reason, make_model
from book_teller.settings import ModelSettings
from book_teller.tell import ask_with, main, tell
from book_teller.write_step import Script
from fake_ask import FakeAsk
from fake_model_service import FakeModelService, text_answer

CHAPTER = "Habit is a second nature.\n\nIn most cases people mean a bad habit."


def test_a_run_prints_the_script_the_flags_and_the_cost_of_each_step() -> None:
    out = io.StringIO()

    assert tell(CHAPTER, FakeAsk(), out) == 0

    printed = out.getvalue()
    # The script of the fake writer, numbered as the checker saw it.
    assert "[S1] James starts with the word habit." in printed
    assert "[S2] Habits can be good." in printed
    # The one flag of the fake checker: its sentence, kind, reason and proof.
    assert "THE FLAGS: 1" in printed
    assert "- S2, wrong_strength: The script says always." in printed
    assert '  the book, P1: "in most cases"' in printed
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


def test_the_real_ask_hands_the_instructions_and_the_text_to_the_model() -> None:
    # Through the fake model service: the one function that joins the graph
    # to the real model call.
    service = FakeModelService(text_answer('{"sentences": ["One sentence."]}'))
    settings = ModelSettings(
        endpoint="https://example.invalid/openai/v1/", deployment="my-deployment"
    )
    model = make_model(settings, lambda: "a-fake-token", service.client())

    answer = ask_with(model)("THE INSTRUCTIONS", "THE TEXT", Script)

    assert answer.parsed == Script(sentences=["One sentence."])
    sent = service.body()["input"]
    assert [(part["role"], part["content"]) for part in sent] == [
        ("system", "THE INSTRUCTIONS"),
        ("user", "THE TEXT"),
    ]


def test_with_picture_the_script_prints_the_graph_and_asks_no_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--picture"]) == 0
    assert "write --> check;" in capsys.readouterr().out


def test_a_chapter_file_that_is_not_there_is_named_in_one_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "no-such-file.txt")]) == 1

    printed = capsys.readouterr().out
    assert printed.startswith("ERROR: ")
    assert "no-such-file.txt" in printed
    assert len(printed.splitlines()) == 1


def test_without_a_file_and_without_picture_the_script_stops() -> None:
    with pytest.raises(SystemExit):
        main([])
