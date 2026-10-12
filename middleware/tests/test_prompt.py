from pathlib import Path

import pytest

from app.config import DEFAULT_SYSTEM_PROMPT_PATH
from app.prompt import PromptLoadError, load_system_prompt


def test_load_system_prompt_returns_file_content_without_surrounding_whitespace(
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("\n  You extract data.\nAlways.  \n\n", encoding="utf-8")

    prompt = load_system_prompt(prompt_file)

    assert prompt == "You extract data.\nAlways."


def test_load_system_prompt_fails_when_file_is_missing(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.md"

    with pytest.raises(PromptLoadError, match="missing.md"):
        load_system_prompt(missing_file)


@pytest.mark.parametrize("content", ["", "  \n\t\n"])
def test_load_system_prompt_fails_when_file_is_blank(tmp_path: Path, content: str) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(content, encoding="utf-8")

    with pytest.raises(PromptLoadError, match="is empty"):
        load_system_prompt(prompt_file)


def test_load_system_prompt_loads_the_shipped_default_prompt() -> None:
    prompt = load_system_prompt(DEFAULT_SYSTEM_PROMPT_PATH)

    assert prompt
