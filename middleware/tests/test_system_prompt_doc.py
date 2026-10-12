import re
from pathlib import Path

import pytest

from app.config import DEFAULT_SYSTEM_PROMPT_PATH
from app.prompt import load_system_prompt
from prompt_eval.format_check import FIELD_KEYS, TOP_LEVEL_KEYS, check_extraction_reply

SYSTEM_PROMPT_DOC = Path(__file__).resolve().parents[2] / "SYSTEM_PROMPT.md"


def prompt_in_doc(doc: str) -> str:
    """Return the prompt copied into SYSTEM_PROMPT.md, between its two markers."""
    match = re.search(
        r"<!-- PROMPT:START -->\n````markdown\n(.*)\n````\n<!-- PROMPT:END -->", doc, re.DOTALL
    )
    if match is None:
        raise ValueError("SYSTEM_PROMPT.md has no prompt between the PROMPT markers")
    return match.group(1)


def test_system_prompt_doc_contains_exactly_the_prompt_the_middleware_loads() -> None:
    doc = SYSTEM_PROMPT_DOC.read_text(encoding="utf-8")

    assert prompt_in_doc(doc) == load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)


def test_prompt_in_doc_fails_clearly_when_the_markers_are_missing() -> None:
    with pytest.raises(ValueError, match="PROMPT markers"):
        prompt_in_doc("# System prompt\n\nNo markers here.")


def test_every_example_in_the_prompt_follows_the_format_it_teaches() -> None:
    prompt = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)

    examples = re.findall(r"```json\n.*?\n```", prompt, re.DOTALL)

    assert len(examples) == 3
    for example in examples:
        assert check_extraction_reply(example) == []


def test_prompt_names_every_key_the_format_checker_requires() -> None:
    prompt = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)

    for key in TOP_LEVEL_KEYS + FIELD_KEYS:
        assert f"`{key}`" in prompt
