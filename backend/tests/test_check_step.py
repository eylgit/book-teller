"""Tests of the check step: its shape, its instructions, and the numbering."""

import json
import re

from book_teller.check_step import INSTRUCTIONS, Flag, Flags, Kind, numbered_texts
from book_teller.model_call import ask_model, make_model
from book_teller.settings import ModelSettings
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
