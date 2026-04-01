"""Player action endpoint with streamed narration output."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agent.orchestrator import resolve_action_with_agent
from ..models.action import ActionRequest, ActionResponse
from ..state import has_character

router = APIRouter(tags=["game"])


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 12) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


async def _stream_action_response(response: ActionResponse) -> AsyncIterator[str]:
    yield _sse_event(
        "start",
        {
            "action_summary": response.action_summary,
            "resolution_type": response.resolution_type.value,
            "outcome": response.outcome.value,
        },
    )

    for field_name in ("narration", "scene_progression"):
        full_text = getattr(response, field_name)
        for chunk in _chunk_text(full_text):
            yield _sse_event(
                "chunk",
                {
                    "field": field_name,
                    "delta": chunk,
                },
            )
            await asyncio.sleep(0.02)

    yield _sse_event("complete", response.model_dump(mode="json"))


@router.post("/action")
async def submit_action(req: ActionRequest, request: Request):
    """Submit a player action and optionally stream the generated narration."""
    if not has_character():
        raise HTTPException(status_code=409, detail="Create a character before taking actions.")

    try:
        result = await asyncio.to_thread(resolve_action_with_agent, req)
    except Exception as exc:  # pragma: no cover - surfaced to client as SSE error
        error_message = str(exc)

        async def error_stream() -> AsyncIterator[str]:
            yield _sse_event("error", {"message": error_message})

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    accepts_stream = "text/event-stream" in request.headers.get("accept", "")
    if not accepts_stream:
        return result

    return StreamingResponse(
        _stream_action_response(result),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
