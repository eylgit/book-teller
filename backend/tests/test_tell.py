"""Tests of the script that runs the steps of an episode by hand. No real call."""

import io
import re
from pathlib import Path

import pytest
from sqlalchemy import Engine

from book_teller.check_step import Flag, Flags, Kind
from book_teller.model_call import ModelCallError, Reason, make_model
from book_teller.runs import SavedRun, read_run
from book_teller.settings import ModelSettings
from book_teller.tables import Status
from book_teller.tell import ask_with, main, tell
from book_teller.write_step import Script
from fake_ask import FLAGS, SCRIPT, FakeAsk
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
    # The paragraph is the one where the guard found the quote, 2. The
    # checker had named 1.
    assert "THE FLAGS: 1, of them not proven: 0" in printed
    assert "- S2, wrong_strength: The script says always." in printed
    assert '  the book, P2: "in most cases"' in printed
    assert "NOT PROVEN" not in printed
    # One line of cost for each step: tokens in, tokens out, thinking, seconds.
    lines = printed.splitlines()
    write_line = next(line for line in lines if line.startswith("write"))
    check_line = next(line for line in lines if line.startswith("check"))
    assert write_line.split() == ["write", "100", "50", "10", "1.5"]
    assert check_line.split() == ["check", "200", "80", "60", "2.5"]


def test_a_flag_that_is_not_proven_is_printed_apart_with_its_problems() -> None:
    made_up = Flag(
        sentence=7,
        kind=Kind.WRONG_FACT,
        paragraph=1,
        quote="in the year 1890",
        reason="The script names the wrong year.",
    )
    out = io.StringIO()

    assert tell(CHAPTER, FakeAsk(flags=Flags(flags=[made_up, *FLAGS.flags])), out) == 0

    printed = out.getvalue()
    assert "THE FLAGS: 2, of them not proven: 1" in printed
    # The proven flag comes first, then the heading, then the other one:
    # with the quote as the checker gave it, and what the guard found wrong.
    proven = printed.index("- S2, wrong_strength: The script says always.")
    heading = printed.index("\nNOT PROVEN\n")
    not_proven = printed.index("- S7, wrong_fact: The script names the wrong year.")
    assert proven < heading < not_proven
    assert '  the checker\'s quote, P1: "in the year 1890"' in printed
    assert "  the problem: no_such_sentence, quote_not_found" in printed


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


# ---- With "--save": the run is also written to the database. ----
# These tests need the database of the tests: see conftest.py. The tests
# above hand in no engine, so they show that a run without "--save" never
# asks a database.


def _the_saved_run(printed: str, engine: Engine) -> SavedRun:
    """The run whose number the script printed, read from the database."""
    line = re.search(r"^THE RUN: saved as run (\d+)$", printed, re.MULTILINE)
    assert line is not None, printed
    run = read_run(engine, int(line.group(1)))
    assert run is not None
    return run


def test_with_an_engine_the_run_is_saved_and_its_number_is_printed(
    database: Engine,
) -> None:
    out = io.StringIO()

    assert tell(CHAPTER, FakeAsk(), out, engine=database) == 0

    printed = out.getvalue()
    # What is printed without an engine is still printed.
    assert "[S2] Habits can be good." in printed
    run = _the_saved_run(printed, database)
    assert run.status is Status.DONE
    assert run.chapter == CHAPTER
    assert run.script == SCRIPT.sentences
    # The one flag of the fake checker, with the answer of the guard.
    [fault] = run.faults
    assert fault.quote == "in most cases"
    assert fault.found_in == 2
    assert fault.proven
    # The sums of the two fake calls.
    assert (run.tokens_in, run.tokens_out, run.thinking_tokens) == (300, 130, 70)


def test_with_an_engine_a_run_that_fails_is_saved_as_failed(database: Engine) -> None:
    out = io.StringIO()
    ask = FakeAsk(
        fail_always={Flags: ModelCallError(Reason.NO_PERMISSION, "status 403")}
    )

    assert tell(CHAPTER, ask, out, engine=database) == 1

    printed = out.getvalue()
    assert "FAILED: no permission: status 403" in printed
    run = _the_saved_run(printed, database)
    assert run.status is Status.FAILED
    # The reason alone, not the long words of the library.
    assert run.failure == "no permission"
    assert run.script is None
    assert run.faults == []


def test_with_save_and_without_the_settings_of_the_database_nothing_is_asked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    chapter = tmp_path / "chapter.txt"
    chapter.write_text(CHAPTER, encoding="utf-8")
    monkeypatch.setenv("BOOK_TELLER_MODEL_ENDPOINT", "https://example.invalid/")
    monkeypatch.setenv("BOOK_TELLER_MODEL_DEPLOYMENT", "my-deployment")
    monkeypatch.delenv("BOOK_TELLER_DATABASE_HOST", raising=False)

    # It ends before any model is asked: a paid run that cannot be saved
    # would be money for nothing.
    assert main(["--save", str(chapter)]) == 1

    printed = capsys.readouterr().out
    assert printed.startswith("ERROR: ")
    assert "BOOK_TELLER_DATABASE_HOST" in printed
    assert len(printed.splitlines()) == 1
