"""Tests of the measuring script. The fake model service answers: no real call."""

import io
from pathlib import Path

import pytest

from book_teller.measure import main, measure, numbered_texts, showing_client
from book_teller.settings import ModelSettings
from fake_model_service import FakeModelService, error, text_answer

SETTINGS = ModelSettings(
    endpoint="https://example.invalid/openai/v1/", deployment="my-deployment"
)

ONE_FAULT = text_answer(
    '{"flags": [{"sentence": 3, "kind": "wrong_fact", "paragraph": 2,'
    ' "quote": "in 1851", "reason": "The script says 1852."}]}'
)


def fake_token() -> str:
    return "a-fake-token"


def test_one_call_and_one_line_for_each_thinking_setting() -> None:
    service = FakeModelService(ONE_FAULT)
    out = io.StringIO()

    measure(SETTINGS, fake_token, "THE TEXT", ["low", "medium"], out, service.client())

    efforts = [service.body(number)["reasoning"]["effort"] for number in (0, 1)]
    assert efforts == ["low", "medium"]
    lines = out.getvalue().splitlines()
    assert len(lines) == 3
    assert lines[0].split()[0] == "thinking"
    # The counts of the fake answer: 1200 in, 800 out, 650 thinking. One fault.
    assert lines[1].split()[:4] == ["low", "1200", "800", "650"]
    assert lines[1].split()[-1] == "1"
    assert lines[2].split()[0] == "medium"


def test_a_setting_that_fails_is_reported_and_the_next_one_still_runs() -> None:
    service = FakeModelService(error(400, "Unsupported value: 'minimal'"), ONE_FAULT)
    out = io.StringIO()

    measure(SETTINGS, fake_token, "THE TEXT", ["minimal", "low"], out, service.client())

    lines = out.getvalue().splitlines()
    assert lines[1].startswith("minimal   FAILED: service error")
    assert "Unsupported value" in lines[1]
    assert lines[2].split()[0] == "low"


def test_the_texts_are_numbered(tmp_path: Path) -> None:
    chapter = tmp_path / "chapter.txt"
    script = tmp_path / "script.txt"
    chapter.write_text("First\nparagraph.\n\nSecond paragraph.\n", encoding="utf-8")
    script.write_text("One sentence.\n\nAnother sentence.\n", encoding="utf-8")

    text = numbered_texts(chapter, script)

    assert "[P1] First paragraph.\n\n[P2] Second paragraph." in text
    assert "[S1] One sentence.\n[S2] Another sentence." in text


def test_showing_never_prints_the_address_or_the_token() -> None:
    out = io.StringIO()
    shown = showing_client(out)
    service = FakeModelService(ONE_FAULT)
    # The showing client keeps its two printers; the fake answers in its place.
    client = service.client()
    client.event_hooks = shown.event_hooks

    measure(SETTINGS, fake_token, "T" * 500, ["low"], io.StringIO(), client)

    printed = out.getvalue()
    assert "--- THE REQUEST: POST" in printed
    assert "--- THE ANSWER: status 200" in printed
    assert '"strict": true' in printed
    assert "example.invalid" not in printed
    assert "a-fake-token" not in printed
    # A long text is cut short.
    assert "T" * 61 not in printed
    assert "(500 characters)" in printed


def test_without_the_settings_the_script_names_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("BOOK_TELLER_MODEL_ENDPOINT", raising=False)

    assert main([]) == 1
    assert "BOOK_TELLER_MODEL_ENDPOINT" in capsys.readouterr().out
