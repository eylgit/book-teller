"""Tests of the settings of a run: the owner's key and the cap of the day.

They need nothing: the settings are read from a dictionary that stands for
the environment variables.
"""

import pytest

from book_teller.settings import RunSettings, SettingsError, read_run_settings


def test_with_nothing_set_there_is_no_key_and_the_cap_is_20() -> None:
    settings = read_run_settings({})

    # No key: the app then starts no run and lets nobody read.
    assert settings.owner_key is None
    assert settings.runs_a_day == 20


def test_the_key_and_the_cap_are_read_from_the_environment_variables() -> None:
    settings = read_run_settings(
        {"BOOK_TELLER_OWNER_KEY": "a-key", "BOOK_TELLER_RUNS_A_DAY": "5"}
    )

    assert settings == RunSettings(owner_key="a-key", runs_a_day=5)


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_a_key_of_only_spaces_counts_as_no_key(empty: str) -> None:
    # An empty key would be "right" for a request that sends an empty key.
    assert read_run_settings({"BOOK_TELLER_OWNER_KEY": empty}).owner_key is None


def test_spaces_around_the_key_are_not_a_part_of_it() -> None:
    # A value that was copied with a line break at its end.
    assert read_run_settings({"BOOK_TELLER_OWNER_KEY": " a-key\n"}).owner_key == "a-key"


def test_a_cap_of_0_is_allowed() -> None:
    # It switches the start of runs off.
    assert read_run_settings({"BOOK_TELLER_RUNS_A_DAY": "0"}).runs_a_day == 0


@pytest.mark.parametrize("wrong", ["many", "2.5", "-1"])
def test_a_cap_that_is_no_whole_number_from_0_up_is_an_error(wrong: str) -> None:
    with pytest.raises(SettingsError, match="BOOK_TELLER_RUNS_A_DAY"):
        read_run_settings({"BOOK_TELLER_RUNS_A_DAY": wrong})


def test_printing_the_settings_does_not_show_the_key() -> None:
    # A line in a log, or the text of an error, must not hold the key.
    settings = RunSettings(owner_key="a-key-that-is-secret")

    assert "a-key-that-is-secret" not in repr(settings)
    assert "a-key-that-is-secret" not in str(settings)
