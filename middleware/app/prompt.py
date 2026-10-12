"""System prompt loading and injection."""

from pathlib import Path
from typing import Any


class PromptLoadError(Exception):
    """The system prompt file is missing or has no content."""


def load_system_prompt(path: Path) -> str:
    """Read the system prompt from a file, without surrounding whitespace.

    Raises PromptLoadError when the file is missing or blank, so the app
    refuses to start instead of proxying requests without a prompt.
    """
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise PromptLoadError(f"Cannot read system prompt file {path}: {error}") from error
    if not prompt:
        raise PromptLoadError(f"System prompt file {path} is empty")
    return prompt


def inject_system_prompt(messages: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    """Return a new message list with our system prompt as the first message.

    Incoming messages, including any system messages the client sent, are kept
    unchanged and in order after ours. The input list is not modified.
    """
    return [{"role": "system", "content": prompt}, *messages]
