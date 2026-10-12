import copy
import json
from typing import Any

import pytest

from prompt_eval.format_check import check_extraction_reply, has_json_block

VALID: dict[str, Any] = {
    "document_type": "invoice",
    "document_type_confidence": 0.97,
    "language": "en",
    "summary": "Invoice 42 from ACME Ltd.",
    "fields": [
        {
            "name": "invoice_number",
            "value": "42",
            "confidence": 0.99,
            "uncertain": False,
            "note": None,
        },
        {
            "name": "due_date",
            "value": "May 1",
            "confidence": 0.6,
            "uncertain": True,
            "note": "Year not stated",
        },
    ],
    "warnings": [],
}


def as_reply(data: Any) -> str:
    return f"```json\n{json.dumps(data, indent=2)}\n```"


def changed(**top_level_changes: Any) -> dict[str, Any]:
    """A copy of the valid extraction with some top-level values replaced."""
    return copy.deepcopy(VALID) | top_level_changes


def with_first_field(**field_changes: Any) -> dict[str, Any]:
    """A copy of the valid extraction with some values of its first field replaced."""
    data = copy.deepcopy(VALID)
    data["fields"][0] |= field_changes
    return data


def test_valid_reply_has_no_problems() -> None:
    assert check_extraction_reply(as_reply(VALID)) == []


def test_reply_with_surrounding_whitespace_is_valid() -> None:
    assert check_extraction_reply(f"\n{as_reply(VALID)}\n\n") == []


def test_reply_with_empty_fields_and_warnings_text_is_valid() -> None:
    data = changed(document_type="unknown", fields=[], warnings=["No readable content"])

    assert check_extraction_reply(as_reply(data)) == []


def test_confidence_of_exactly_the_threshold_counts_as_uncertain() -> None:
    data = with_first_field(confidence=0.8, uncertain=True, note="Label was abbreviated")

    assert check_extraction_reply(as_reply(data)) == []


def test_confidence_just_above_the_threshold_counts_as_certain() -> None:
    data = with_first_field(confidence=0.85, uncertain=False, note=None)

    assert check_extraction_reply(as_reply(data)) == []


@pytest.mark.parametrize(
    "reply",
    [
        json.dumps(VALID),
        f"Here is the data:\n{as_reply(VALID)}",
        f"{as_reply(VALID)}\nLet me know if you need more.",
        "It is due on May 1.",
    ],
)
def test_reply_that_is_not_exactly_one_json_block_is_reported(reply: str) -> None:
    assert check_extraction_reply(reply) == ["reply is not exactly one fenced json block"]


def test_invalid_json_is_reported() -> None:
    problems = check_extraction_reply('```json\n{"document_type": \n```')

    assert len(problems) == 1
    assert problems[0].startswith("block is not valid JSON")


def test_json_that_is_not_an_object_is_reported() -> None:
    assert check_extraction_reply(as_reply([VALID])) == ["JSON is not an object"]


def test_missing_top_level_key_is_reported() -> None:
    data = changed()
    del data["warnings"]

    problems = check_extraction_reply(as_reply(data))

    assert len(problems) == 1
    assert problems[0].startswith("top-level keys are")


def test_extra_top_level_key_is_reported() -> None:
    problems = check_extraction_reply(as_reply(changed(extra="x")))

    assert len(problems) == 1
    assert problems[0].startswith("top-level keys are")


@pytest.mark.parametrize(
    ("data", "expected_problem"),
    [
        (changed(document_type=""), "document_type is not a non-empty string"),
        (changed(document_type="Invoice Document"), "document_type is not snake_case"),
        (changed(document_type_confidence=1.5), "document_type_confidence is not a number"),
        (changed(document_type_confidence="high"), "document_type_confidence is not a number"),
        (changed(warnings="none"), "warnings is not a list of strings"),
        (changed(warnings=[1]), "warnings is not a list of strings"),
        (changed(fields={}), "fields is not a list"),
        (changed(fields=["invoice_number"]), "fields[0] is not an object"),
        (changed(fields=[{"name": "a", "value": "b"}]), "fields[0] has keys"),
        (with_first_field(name="Invoice Number"), "fields[0].name is not snake_case"),
        (with_first_field(value=42), "fields[0].value is not a string"),
        (with_first_field(confidence=True), "fields[0].confidence is not a number"),
        (with_first_field(confidence=-0.1), "fields[0].confidence is not a number"),
        (with_first_field(uncertain=True), "fields[0].uncertain is True but confidence is 0.99"),
        (with_first_field(confidence=0.5), "fields[0].uncertain is False but confidence is 0.5"),
        (
            with_first_field(confidence=0.5, uncertain=True),
            "fields[0] is uncertain but has no note",
        ),
        (with_first_field(note="Looks fine"), "fields[0] is not uncertain but note is not null"),
    ],
)
def test_format_problem_is_reported(data: dict[str, Any], expected_problem: str) -> None:
    problems = check_extraction_reply(as_reply(data))

    assert any(problem.startswith(expected_problem) for problem in problems), problems


def test_has_json_block_detects_a_block_inside_prose() -> None:
    assert has_json_block(f"Sure:\n{as_reply(VALID)}")
    assert not has_json_block("It is due on May 1.")
