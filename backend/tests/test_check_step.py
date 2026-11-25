"""Tests of the check step: its shape, its instructions, and the numbering."""

import json
import re

import pytest

from book_teller.check_step import (
    INSTRUCTIONS,
    Flag,
    Flags,
    Kind,
    numbered_texts,
    paragraphs,
)
from book_teller.model_call import ModelCallError, Reason, ask_model, make_model
from book_teller.settings import ModelSettings
from book_teller.write_step import Script
from fake_model_service import FakeModelService, text_answer

SETTINGS = ModelSettings(
    endpoint="https://example.invalid/openai/v1/", deployment="my-deployment"
)


def fake_token() -> str:
    return "a-fake-token"


def test_every_field_of_a_flag_has_a_description() -> None:
    fields = Flag.model_json_schema()["properties"]

    assert set(fields) == {"sentence", "kind", "paragraph", "quote", "reason"}
    for name, field in fields.items():
        assert field.get("description"), f"the field {name} has no description"
    # A fault of the kind "left_out" has no sentence. The model must be told
    # which number to give then.
    assert "0" in fields["sentence"]["description"]
    assert Kind.LEFT_OUT.value in fields["sentence"]["description"]


def test_the_lists_of_both_shapes_have_a_description() -> None:
    assert Flags.model_json_schema()["properties"]["flags"].get("description")
    assert Script.model_json_schema()["properties"]["sentences"].get("description")


def test_the_descriptions_and_the_names_of_the_kinds_reach_the_model() -> None:
    # Through the fake model service: this is the request as the library
    # really sends it, after LangChain and OpenAI's library have reworked
    # the schema.
    service = FakeModelService(text_answer('{"flags": []}'))
    model = make_model(SETTINGS, fake_token, http_client=service.client())

    ask_model(model, INSTRUCTIONS, "THE TEXT", Flags)

    sent = json.dumps(service.body()["text"]["format"]["schema"])
    for name, field in Flag.model_fields.items():
        assert field.description, name
        assert json.dumps(field.description)[1:-1] in sent, name
    for kind in Kind:
        assert f'"{kind.value}"' in sent


def test_the_instructions_explain_exactly_the_kinds_of_the_code() -> None:
    # In the instructions each kind has its own line: "- wrong_fact: ...".
    explained = re.findall(r"^- (\w+): \S", INSTRUCTIONS, flags=re.MULTILINE)

    assert explained == [kind.value for kind in Kind]
    assert len(explained) == 6


def test_the_paragraphs_and_the_sentences_are_numbered_from_one() -> None:
    chapter = "First\nparagraph.\n\n\nSecond paragraph.\n"
    script = ["One sentence.", "Another sentence."]

    text = numbered_texts(chapter, script)

    assert "[P1] First paragraph.\n\n[P2] Second paragraph." in text
    assert "[S1] One sentence.\n[S2] Another sentence." in text
    assert text.index("THE CHAPTER") < text.index("THE SCRIPT")


def test_a_line_that_holds_only_spaces_ends_a_paragraph_too() -> None:
    # A text pasted from a browser often has such lines.
    text = numbered_texts("One.\n \t\nTwo.", [])

    assert "[P1] One.\n\n[P2] Two." in text


def test_the_split_gives_the_paragraphs_that_the_numbering_shows() -> None:
    # The guard searches a quote in these paragraphs, and the checker reads
    # the numbered text. "P2" must be the same paragraph for both.
    chapter = "First\nparagraph.\n\n\nSecond paragraph.\n \t\nThird."

    split = paragraphs(chapter)

    assert split == ["First paragraph.", "Second paragraph.", "Third."]
    numbered = numbered_texts(chapter, [])
    for number, paragraph in enumerate(split, 1):
        assert f"[P{number}] {paragraph}" in numbered


@pytest.mark.parametrize(
    "one_flag",
    [
        # A kind that is not one of the six names.
        {
            "sentence": 1,
            "kind": "wrong_colour",
            "paragraph": 1,
            "quote": "Habit is a second nature.",
            "reason": "The script says third.",
        },
        # No quote.
        {
            "sentence": 1,
            "kind": "wrong_fact",
            "paragraph": 1,
            "reason": "The script says third.",
        },
        # A sentence number that is not a whole number.
        {
            "sentence": "the first",
            "kind": "wrong_fact",
            "paragraph": 1,
            "quote": "Habit is a second nature.",
            "reason": "The script says third.",
        },
    ],
)
def test_an_answer_that_is_not_in_the_shape_of_a_flag_is_a_wrong_shape(
    one_flag: dict[str, object],
) -> None:
    # The shape check: Pydantic compares the answer with the class Flag,
    # inside ask_model. The real service forces the shape, so such an answer
    # is rare. The check must not lean on that.
    service = FakeModelService(text_answer(json.dumps({"flags": [one_flag]})))
    model = make_model(SETTINGS, fake_token, http_client=service.client())

    with pytest.raises(ModelCallError) as caught:
        ask_model(model, INSTRUCTIONS, "THE TEXT", Flags)

    assert caught.value.reason == Reason.WRONG_SHAPE


def test_the_instructions_say_how_the_texts_are_numbered() -> None:
    assert "[S7]" in INSTRUCTIONS
    assert "[P3]" in INSTRUCTIONS
