"""Player action endpoint with streamed narration output."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agent.orchestrator import resolve_action_with_agent
from ..models.action import ActionRequest, ActionResponse
from ..models.state import AdventurePhase
from ..scene import get_scene_transition, build_scene_context_for_prompt, get_scene_by_id
from ..state import (
    append_action_history,
    has_character,
    require_bootstrap_state,
    reset_current_session,
    set_combat_scene,
    set_current_session,
    switch_scene,
    _get_session,
    _resolve_session_id,
    _save_session,
)

router = APIRouter(tags=["game"])

# Movement keywords - if these appear, treat as scene navigation (no combat trigger)
_MOVEMENT_KEYWORDS = [
    "go", "move", "walk", "head", "enter", "leave", "exit", "return", "back",
    "前往", "去", "走", "进入", "离开", "返回", "回", "到", "向",
]

# Combat trigger keywords - if these appear in action intent, auto-trigger combat
_COMBAT_TRIGGER_KEYWORDS = [
    "attack", "fight", "combat", "hit", "strike", "stab", "slash", "shoot",
    "kill", "defeat", "engage", "ambush", "assault", "battle",
    "攻击", "战斗", "打", "杀", "砍", "刺", "射击", "开战",
]

# Rest action keywords
_SHORT_REST_KEYWORDS = ["短休", "short rest", "休息", "休整"]
_LONG_REST_KEYWORDS = ["长休", "long rest", "睡眠", "睡觉", "宿营", "露营"]


def _is_movement_action(intent: str, approach: str) -> bool:
    """Check if an action is a movement/navigation action."""
    text = f"{intent} {approach}".lower()
    # Use word boundary matching to avoid partial matches (e.g., "go" in "goblin")
    import re
    for keyword in _MOVEMENT_KEYWORDS:
        # Create a pattern that matches the keyword as a whole word/phrase
        # For Chinese keywords, we don't need word boundaries
        # For English keywords, we use word boundaries
        if keyword.isascii():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text):
                return True
        else:
            if keyword in text:
                return True
    return False


def _should_trigger_combat(intent: str, approach: str) -> bool:
    """Check if an action should trigger combat based on keywords."""
    text = f"{intent} {approach}".lower()
    # Don't trigger combat for movement actions
    if _is_movement_action(intent, approach):
        return False
    return any(keyword in text for keyword in _COMBAT_TRIGGER_KEYWORDS)


def _is_short_rest_action(intent: str, approach: str) -> bool:
    """Check if action is a short rest."""
    text = f"{intent} {approach}".lower()
    return any(keyword in text for keyword in _SHORT_REST_KEYWORDS)


def _is_long_rest_action(intent: str, approach: str) -> bool:
    """Check if action is a long rest."""
    text = f"{intent} {approach}".lower()
    return any(keyword in text for keyword in _LONG_REST_KEYWORDS)


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

    for field_name in ("narration", "scene_progression", "gm_prompt"):
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
    from ..state import DEFAULT_SESSION_ID, create_character
    from ..models.state import CharacterCreateRequest

    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID

    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    token = set_current_session(session_id)
    try:
        if not has_character(session_id=session_id):
            if explicit_session_id:
                raise HTTPException(status_code=400, detail="No character found. Please create a character before taking actions.")
            # Auto-create a default character for the implicit default session
            # to maintain backward compatibility with legacy tests
            create_character(
                CharacterCreateRequest(name="Aldric", character_class="warrior"),
                session_id=session_id,
            )

        # Check for rest actions first (before agent resolution)
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        
        # Handle short rest
        if _is_short_rest_action(req.intent, req.approach):
            from ..state import perform_short_rest
            success, rest_result = perform_short_rest(session_id)
            
            if not success:
                # Return error response for rest failure
                error_response = ActionResponse(
                    action_summary="短休",
                    resolution_type="auto_success",
                    outcome="failure",
                    narration=rest_result.get("error", rest_result.get("message", "短休失败")),
                    scene_progression="无法在当前状态下短休。",
                    gm_prompt="短休未能执行。",
                )
                return error_response
            
            # Return success response for short rest
            success_response = ActionResponse(
                action_summary="短休",
                resolution_type="auto_success",
                outcome="success",
                narration=rest_result["message"],
                scene_progression=f"角色进行了短休，恢复了 {rest_result.get('hp_gained', 0)} 点HP。",
                gm_prompt="短休完成，角色可以继续探索。",
            )
            
            # Persist to history
            append_action_history(
                {"action": "短休", "result": "success", "narrative_summary": rest_result["message"]},
                session_id=session_id,
            )
            
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            if not accepts_stream:
                return success_response
            return StreamingResponse(
                _stream_action_response(success_response),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        
        # Handle long rest
        if _is_long_rest_action(req.intent, req.approach):
            from ..state import perform_long_rest
            success, rest_result = perform_long_rest(session_id)
            
            if not success:
                error_response = ActionResponse(
                    action_summary="长休",
                    resolution_type="auto_success",
                    outcome="failure",
                    narration=rest_result.get("error", rest_result.get("message", "长休失败")),
                    scene_progression="无法在当前状态下长休。",
                    gm_prompt="长休未能执行。",
                )
                return error_response
            
            success_response = ActionResponse(
                action_summary="长休",
                resolution_type="auto_success",
                outcome="success",
                narration=rest_result["message"],
                scene_progression="角色进行了长休，完全恢复了HP和所有资源。",
                gm_prompt="长休完成，角色已经完全恢复，可以继续冒险。",
            )
            
            append_action_history(
                {"action": "长休", "result": "success", "narrative_summary": rest_result["message"]},
                session_id=session_id,
            )
            
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            if not accepts_stream:
                return success_response
            return StreamingResponse(
                _stream_action_response(success_response),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        try:
            result = await asyncio.to_thread(resolve_action_with_agent, req)
        except Exception as exc:  # pragma: no cover - surfaced to client as SSE error
            error_message = str(exc)

            async def error_stream() -> AsyncIterator[str]:
                yield _sse_event("error", {"message": error_message})

            return StreamingResponse(error_stream(), media_type="text/event-stream")

        # Persist action summary to session memory
        append_action_history(
            {
                "action": result.action_summary,
                "result": result.outcome.value,
                "narrative_summary": (result.narration or "")[:400],
            },
            session_id=session_id,
        )

        # Check for scene transitions based on action intent
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        if session.game_phase == AdventurePhase.EXPLORATION:
            # Check for scene transition keywords first
            target_scene_id = get_scene_transition(req.intent)
            
            # If no transition keyword found but it's a movement action,
            # check against current scene exits
            if not target_scene_id and _is_movement_action(req.intent, req.approach):
                intent_lower = req.intent.lower()
                for exit in session.scene.exits:
                    if exit.direction.lower() in intent_lower:
                        target_scene_id = exit.target_scene_id
                        break
            
            if target_scene_id and target_scene_id != session.scene.id:
                # Switch to new scene (movement doesn't trigger combat)
                switch_scene(target_scene_id, session_id)
                # Re-fetch session to get updated state
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
            # Check if this action should trigger combat (only if not a movement action)
            elif _should_trigger_combat(req.intent, req.approach):
                # Transition to combat
                set_combat_scene(session_id)
                # Re-fetch session to get updated state
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)

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
    finally:
        reset_current_session(token)
