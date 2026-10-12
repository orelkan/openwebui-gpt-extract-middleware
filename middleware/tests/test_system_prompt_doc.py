import re

from app.config import DEFAULT_SYSTEM_PROMPT_PATH
from app.prompt import load_system_prompt
from prompt_eval.format_check import FIELD_KEYS, TOP_LEVEL_KEYS, check_extraction_reply


def test_example_in_the_prompt_follows_the_format_it_teaches() -> None:
    prompt = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)

    examples = re.findall(r"```json\n.*?\n```", prompt, re.DOTALL)

    assert len(examples) == 1
    assert check_extraction_reply(examples[0]) == []


def test_prompt_names_every_key_the_format_checker_requires() -> None:
    prompt = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)

    for key in TOP_LEVEL_KEYS + FIELD_KEYS:
        assert f"`{key}`" in prompt
