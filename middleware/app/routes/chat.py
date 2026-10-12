"""Chat completions, proxied to upstream with the system prompt injected."""

from collections.abc import AsyncGenerator
from typing import Any

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
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


async def stream_upstream_body(upstream_response: httpx.Response) -> AsyncGenerator[bytes, None]:
    """Yield the upstream body chunk by chunk, then release the upstream connection.

    The finally block also runs when our client disconnects mid-stream, so an
    abandoned request does not keep its upstream connection open.
    """
    try:
        async for chunk in upstream_response.aiter_bytes():
            yield chunk
    finally:
        await upstream_response.aclose()


async def forward_streaming(
    upstream_client: httpx.AsyncClient, payload: dict[str, Any]
) -> Response:
    """Send a streaming request upstream and relay the SSE stream as it arrives."""
    upstream_request = upstream_client.build_request("POST", "/chat/completions", json=payload)
    upstream_response = await upstream_client.send(upstream_request, stream=True)
    if upstream_response.status_code != httpx.codes.OK:
        # An error answer is a small JSON document, not a stream: read it whole
        # (which also closes it) and return it like a non-streaming response.
        await upstream_response.aread()
        return passthrough_response(upstream_response)
    return StreamingResponse(
        stream_upstream_body(upstream_response),
        media_type="text/event-stream",
    )


@router.post("/v1/chat/completions")
async def chat_completions(chat_request: ChatCompletionRequest, request: Request) -> Response:
    """Forward a chat completion request to upstream and return its answer."""
    upstream_client: httpx.AsyncClient = request.app.state.upstream_client
    payload = build_upstream_payload(chat_request, request.app.state.system_prompt)
    if chat_request.stream:
        return await forward_streaming(upstream_client, payload)
    upstream_response = await upstream_client.post("/chat/completions", json=payload)
    return passthrough_response(upstream_response)
