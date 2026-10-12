"""Chat completions, proxied to upstream with the system prompt injected."""

from typing import Any

import httpx
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from app.prompt import inject_system_prompt
from app.upstream import passthrough_response

router = APIRouter()


class ChatCompletionRequest(BaseModel):
    """The fields the middleware needs to know about.

    Every other field the client sends (temperature, tools, stream_options...)
    is accepted as an extra and forwarded unchanged.
    """

    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[dict[str, Any]]
    stream: bool = False


def build_upstream_payload(chat_request: ChatCompletionRequest, prompt: str) -> dict[str, Any]:
    """Return the body to send upstream: the client's body with our prompt prepended.

    Only fields the client actually sent are included, so the proxy adds nothing
    besides the system message.
    """
    payload = chat_request.model_dump(exclude_unset=True)
    payload["messages"] = inject_system_prompt(chat_request.messages, prompt)
    return payload


@router.post("/v1/chat/completions")
async def chat_completions(chat_request: ChatCompletionRequest, request: Request) -> Response:
    """Forward a chat completion request to upstream and return its answer."""
    upstream_client: httpx.AsyncClient = request.app.state.upstream_client
    payload = build_upstream_payload(chat_request, request.app.state.system_prompt)
    upstream_response = await upstream_client.post("/chat/completions", json=payload)
    return passthrough_response(upstream_response)
