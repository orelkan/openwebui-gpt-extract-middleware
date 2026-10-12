"""Check that a model reply follows the extraction output format.

The format is described to the model in prompts/system_prompt.md. This module
states the same rules as code, so replies can be checked mechanically.
"""

import json
import re
from typing import Any

TOP_LEVEL_KEYS = [
    "document_type",
    "document_type_confidence",
    "language",
    "summary",
    "fields",
    "warnings",
]
FIELD_KEYS = ["name", "value", "confidence", "uncertain", "note"]
# A field is flagged uncertain exactly when its confidence is below this.
UNCERTAIN_BELOW = 0.8

SNAKE_CASE = re.compile(r"[a-z][a-z0-9_]*")


def has_json_block(reply: str) -> bool:
    """Tell whether a reply contains a fenced json block anywhere."""
    return "```json" in reply


def extract_json_block(reply: str) -> str | None:
    """Return the content of the block if the reply is one fenced json block and nothing else."""
    match = re.fullmatch(r"```json\n(.*)\n```", reply.strip(), re.DOTALL)
    return match.group(1) if match else None


def is_confidence(value: Any) -> bool:
    """Tell whether a value is a number from 0 to 1 (booleans do not count as numbers)."""
    return isinstance(value, int | float) and not isinstance(value, bool) and 0 <= value <= 1


def check_field(field: Any, index: int) -> list[str]:
    """List the format problems of one entry of `fields`."""
    where = f"fields[{index}]"
    if not isinstance(field, dict):
        return [f"{where} is not an object"]
    if list(field) != FIELD_KEYS:
        return [f"{where} has keys {list(field)}, expected {FIELD_KEYS}"]

    problems = []
    if not isinstance(field["name"], str) or not SNAKE_CASE.fullmatch(field["name"]):
        problems.append(f"{where}.name is not snake_case: {field['name']!r}")
    if not isinstance(field["value"], str):
        problems.append(f"{where}.value is not a string: {field['value']!r}")
    if not is_confidence(field["confidence"]):
        problems.append(f"{where}.confidence is not a number from 0 to 1")
        return problems
    should_be_uncertain = field["confidence"] < UNCERTAIN_BELOW
    if field["uncertain"] is not should_be_uncertain:
        problems.append(
            f"{where}.uncertain is {field['uncertain']!r} but confidence is {field['confidence']}"
        )
    if should_be_uncertain and not (isinstance(field["note"], str) and field["note"].strip()):
        problems.append(f"{where} is uncertain but has no note")
    if not should_be_uncertain and field["note"] is not None:
        problems.append(f"{where} is not uncertain but note is not null")
    return problems


def check_extraction_reply(reply: str) -> list[str]:
    """List every way a reply breaks the extraction format. An empty list means it is valid."""
    block = extract_json_block(reply)
    if block is None:
        return ["reply is not exactly one fenced json block"]
    try:
        data = json.loads(block)
    except ValueError as error:
        return [f"block is not valid JSON: {error}"]
    if not isinstance(data, dict):
        return ["JSON is not an object"]
    if list(data) != TOP_LEVEL_KEYS:
        return [f"top-level keys are {list(data)}, expected {TOP_LEVEL_KEYS}"]

    problems = []
    for key in ("document_type", "language", "summary"):
        if not isinstance(data[key], str) or not data[key].strip():
            problems.append(f"{key} is not a non-empty string")
    if isinstance(data["document_type"], str) and not SNAKE_CASE.fullmatch(data["document_type"]):
        problems.append(f"document_type is not snake_case: {data['document_type']!r}")
    if not is_confidence(data["document_type_confidence"]):
        problems.append("document_type_confidence is not a number from 0 to 1")
    if not isinstance(data["warnings"], list) or not all(
        isinstance(warning, str) for warning in data["warnings"]
    ):
        problems.append("warnings is not a list of strings")
    if not isinstance(data["fields"], list):
        problems.append("fields is not a list")
        return problems
    for index, field in enumerate(data["fields"]):
        problems.extend(check_field(field, index))
    return problems
