import json
from typing import Any

import pytest

from prompt_eval.cases import CASES, SAMPLES_DIR, Case, check_case


def extraction_reply(**changes: Any) -> str:
    """A well-formed extraction reply, with some top-level values replaced."""
    data = {
        "document_type": "invoice",
        "document_type_confidence": 0.97,
        "language": "en",
        "summary": "Invoice 42 from ACME Ltd.",
        "fields": [
            {
                "name": "due_date",
                "value": "May 1",
                "uncertain": True,
                "confidence": 0.6,
                "note": "Year not stated",
            },
        ],
        "warnings": [],
    } | changes
    return f"```json\n{json.dumps(data)}\n```"


CERTAIN_DUE_DATE = [
    {"name": "due_date", "value": "May 1", "uncertain": False, "confidence": 0.95, "note": None}
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_case_points_at_an_existing_sample(case: Case) -> None:
    assert (SAMPLES_DIR / case.sample).is_file()


def test_case_names_are_unique() -> None:
    names = [case.name for case in CASES]

    assert len(names) == len(set(names))


def test_extraction_that_meets_all_expectations_passes() -> None:
    case = Case(
        name="c",
        sample="s.txt",
        document_type="invoice",
        language="en",
        uncertain_field="due",
        expects_warning=True,
    )

    assert check_case(case, extraction_reply(warnings=["Something to know"])) == []


def test_format_problems_are_reported_for_an_extraction_case() -> None:
    case = Case(name="c", sample="s.txt")

    assert check_case(case, "It is an invoice.") == ["reply is not exactly one fenced json block"]


@pytest.mark.parametrize(
    ("case", "reply", "expected_problem"),
    [
        (
            Case(name="c", sample="s.txt", document_type="receipt"),
            extraction_reply(),
            "document_type is 'invoice', expected 'receipt'",
        ),
        (
            Case(name="c", sample="s.txt", language="es"),
            extraction_reply(),
            "language is 'en', expected 'es'",
        ),
        (
            Case(name="c", sample="s.txt", expects_warning=True),
            extraction_reply(),
            "warnings is empty but a warning was expected",
        ),
        (
            Case(name="c", sample="s.txt", uncertain_field="total"),
            extraction_reply(),
            "no field with 'total' in its name",
        ),
        (
            Case(name="c", sample="s.txt", uncertain_field="due"),
            extraction_reply(fields=CERTAIN_DUE_DATE),
            "field with 'due' in its name is not uncertain",
        ),
    ],
)
def test_unmet_expectation_is_reported(case: Case, reply: str, expected_problem: str) -> None:
    assert check_case(case, reply) == [expected_problem]


def test_prose_reply_passes_a_prose_case() -> None:
    case = Case(name="c", sample="s.txt", expects_extraction=False, answer_mentions="May 1")

    assert check_case(case, "It is due on May 1 (due_date).") == []


def test_json_block_is_reported_for_a_prose_case() -> None:
    case = Case(name="c", sample="s.txt", expects_extraction=False)

    assert check_case(case, extraction_reply()) == [
        "reply contains a json block but should be plain prose"
    ]


def test_missing_mention_is_reported_for_a_prose_case() -> None:
    case = Case(name="c", sample="s.txt", expects_extraction=False, answer_mentions="May 1")

    assert check_case(case, "It is due soon.") == ["reply does not mention 'May 1'"]
