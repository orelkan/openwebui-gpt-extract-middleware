"""The sample cases and what a correct reply to each must look like."""

import json
from dataclasses import dataclass
from pathlib import Path

from prompt_eval.format_check import check_extraction_reply, extract_json_block, has_json_block

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


@dataclass(frozen=True)
class Case:
    """One sample input and the expectations its reply is checked against."""

    name: str
    sample: str
    # False for inputs that must be answered in plain prose, without a JSON block.
    expects_extraction: bool = True
    # Asked after the sample has been extracted; the answer to it is what gets checked.
    follow_up: str | None = None
    document_type: str | None = None
    language: str | None = None
    # Part of the name of a field that must be flagged uncertain.
    uncertain_field: str | None = None
    expects_warning: bool = False
    # Fewest entries `fields` may have; catches a well-formed but empty extraction.
    min_fields: int = 0
    # Each of these must be part of the name of at least one field.
    required_fields: tuple[str, ...] = ()
    # Text the prose answer must contain.
    answer_mentions: str | None = None


CASES = [
    Case(name="email", sample="email.txt", document_type="email", language="en", min_fields=6),
    Case(
        name="receipt", sample="receipt.txt", document_type="receipt", language="en", min_fields=6
    ),
    Case(name="job_listing", sample="job_listing.txt", language="en", min_fields=6),
    Case(name="medical_report", sample="medical_report.txt", language="en", min_fields=6),
    Case(name="legal_paragraph", sample="legal_paragraph.txt", language="en", min_fields=3),
    Case(
        name="invoice_no_year",
        sample="invoice_no_year.txt",
        document_type="invoice",
        uncertain_field="due",
        min_fields=4,
    ),
    Case(name="non_english", sample="non_english.txt", language="es", min_fields=6),
    Case(
        name="mixed_content",
        sample="mixed_content.txt",
        document_type="mixed",
        expects_warning=True,
        min_fields=6,
    ),
    Case(
        name="prompt_injection", sample="prompt_injection.txt", expects_warning=True, min_fields=4
    ),
    Case(name="garbled", sample="garbled.txt", document_type="unknown"),
    Case(name="greeting", sample="greeting.txt", expects_extraction=False),
    Case(
        name="follow_up",
        sample="invoice_no_year.txt",
        expects_extraction=False,
        follow_up="when is it due?",
        answer_mentions="May 1",
    ),
]


def check_prose_reply(case: Case, reply: str) -> list[str]:
    """List the problems of a reply that should have been plain prose."""
    problems = []
    if has_json_block(reply):
        problems.append("reply contains a json block but should be plain prose")
    if case.answer_mentions and case.answer_mentions not in reply:
        problems.append(f"reply does not mention {case.answer_mentions!r}")
    return problems


def check_case(case: Case, reply: str) -> list[str]:
    """List every way a reply fails its case. An empty list means it passed."""
    if not case.expects_extraction:
        return check_prose_reply(case, reply)

    problems = check_extraction_reply(reply)
    block = extract_json_block(reply)
    if problems or block is None:
        return problems

    data = json.loads(block)
    if case.document_type and data["document_type"] != case.document_type:
        problems.append(
            f"document_type is {data['document_type']!r}, expected {case.document_type!r}"
        )
    if case.language and data["language"] != case.language:
        problems.append(f"language is {data['language']!r}, expected {case.language!r}")
    if len(data["fields"]) < case.min_fields:
        problems.append(f"only {len(data['fields'])} fields, expected at least {case.min_fields}")
    names = [field["name"] for field in data["fields"]]
    for required in case.required_fields:
        if not any(required in name for name in names):
            problems.append(f"no field with {required!r} in its name")
    if case.expects_warning and not data["warnings"]:
        problems.append("warnings is empty but a warning was expected")
    if case.uncertain_field:
        matching = [field for field in data["fields"] if case.uncertain_field in field["name"]]
        if not matching:
            problems.append(f"no field with {case.uncertain_field!r} in its name")
        elif not all(field["uncertain"] for field in matching):
            problems.append(f"field with {case.uncertain_field!r} in its name is not uncertain")
    return problems


def count_field_variants(replies: list[str]) -> tuple[int, int]:
    """Measure how much repeated extractions of the same text differ.

    Returns the number of distinct sets of field names among the replies, and
    the number of distinct sets of (name, value) pairs. (1, 1) means every
    repeat extracted exactly the same data. Replies that break the format are
    left out; they are already reported as failures.
    """
    name_sets = set()
    pair_sets = set()
    for reply in replies:
        block = extract_json_block(reply)
        if block is None or check_extraction_reply(reply):
            continue
        fields = json.loads(block)["fields"]
        name_sets.add(frozenset(field["name"] for field in fields))
        pair_sets.add(frozenset((field["name"], field["value"]) for field in fields))
    return len(name_sets), len(pair_sets)
