"""Player action endpoint with streamed narration output."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..actions.scene_interaction import (
    find_interactive_element,
    handle_scene_interaction,
    is_scene_interaction_action,
)
from ..agent.orchestrator import resolve_action_with_agent
from ..items import resolve_item_use
from ..models.action import ActionRequest, ActionResponse, Effect, Outcome, ResolutionType
from ..models.state import AdventurePhase
from ..scene import get_scene_transition, build_scene_context_for_prompt, get_scene_by_id
from ..scenes import (
    is_movement_action,
    handle_movement,
    get_available_exits,
)
from ..state import (
    apply_effects,
    append_action_history,
    get_actor,
    has_character,
    require_bootstrap_state,
    reset_current_session,
    set_combat_scene,
    set_current_session,
    switch_scene,
    update_combatant_hp,
    use_action_surge,
    use_second_wind,
    _get_session,
    _resolve_session_id,
    _save_session,
)

router = APIRouter(tags=["game"])

# Combat trigger keywords - if these appear in action intent, auto-trigger combat
_COMBAT_TRIGGER_KEYWORDS = [
    "attack", "fight", "combat", "hit", "strike", "stab", "slash", "shoot",
    "kill", "defeat", "engage", "ambush", "assault", "battle",
    "攻击", "战斗", "打", "杀", "砍", "刺", "射击", "开战",
]


def _should_trigger_combat(intent: str, approach: str) -> bool:
    """Check if an action should trigger combat based on keywords."""
    text = f"{intent} {approach}".lower()
    # Don't trigger combat for movement actions
    if is_movement_action(intent, approach):
        return False
    return any(keyword in text for keyword in _COMBAT_TRIGGER_KEYWORDS)


# Item use keywords
_ITEM_USE_PREFIXES = [
    "使用", "用", "use", "consume", "drink", "喝",
]


def _is_item_use_action(intent: str, approach: str) -> bool:
    """Check if an action is an item use action."""
    text = f"{intent} {approach}".lower().strip()
    for prefix in _ITEM_USE_PREFIXES:
        if prefix.isascii():
            # English prefixes: only match at start of text
            if text.startswith(prefix.lower() + " ") or text == prefix.lower():
                return True
        else:
            # Chinese prefixes: only match at start of text
            if text.startswith(prefix) or text.startswith(f"{prefix}"):
                return True
    return False


def _parse_item_name(intent: str, approach: str) -> str:
    """Parse item name from an item use action text."""
    text = f"{intent} {approach}".strip()
    
    # Try Chinese "使用X"
    if text.startswith("使用"):
        return text[2:].strip()
    if text.startswith("用"):
        return text[1:].strip()
    if text.startswith("喝"):
        return text[1:].strip()
    
    # Try English "use X", "consume X", "drink X"
    lower = text.lower()
    for prefix in ("use ", "consume ", "drink "):
        if lower.startswith(prefix):
            return text[len(prefix):].strip()
    
    # Fallback: remove the first word/prefix and return the rest
    parts = text.split(None, 1)
    if len(parts) > 1:
        return parts[1].strip()
    return text


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

        # Check for class feature actions before routing to agent
        intent_lower = req.intent.strip().lower()
        if intent_lower == "second_wind":
            sw_result = use_second_wind(session_id=session_id)
            if not sw_result["success"]:
                raise HTTPException(status_code=400, detail=sw_result["error"])
            
            actor = get_actor(session_id=session_id) or actor
            effects = []
            if actor is not None:
                effects.append(Effect(
                    target=actor.id,
                    field="hp",
                    delta=sw_result["hp_healed"],
                    description=f"Second Wind 恢复 {sw_result['hp_healed']} 点生命值",
                ))
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                if session.game_phase == AdventurePhase.COMBAT:
                    update_combatant_hp(actor.id, actor.hp)
            
            result = ActionResponse(
                action_summary="使用 Second Wind",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=effects,
                narration=f"你集中精神，调动体内的战斗本能，恢复了 {sw_result['hp_healed']} 点生命值。",
                scene_progression="",
                gm_prompt="",
            )
            append_action_history(
                {
                    "action": result.action_summary,
                    "result": result.outcome.value,
                    "narrative_summary": result.narration,
                },
                session_id=session_id,
            )
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
        
        if intent_lower == "action_surge":
            as_result = use_action_surge(session_id=session_id)
            if not as_result["success"]:
                raise HTTPException(status_code=400, detail=as_result["error"])
            
            actor = get_actor(session_id=session_id)
            effects = []
            if actor is not None:
                effects.append(Effect(
                    target=actor.id,
                    field="class_features",
                    delta="action_surge_used",
                    description="Action Surge 已使用",
                ))
            
            result = ActionResponse(
                action_summary="使用 Action Surge",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=effects,
                narration="肾上腺素涌动，你获得了一次额外的行动机会！",
                scene_progression="",
                gm_prompt="",
            )
            # Inject extra_action_available into the raw response for non-streaming
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            if not accepts_stream:
                raw = result.model_dump(mode="json")
                raw["extra_action_available"] = True
                append_action_history(
                    {
                        "action": result.action_summary,
                        "result": result.outcome.value,
                        "narrative_summary": result.narration,
                    },
                    session_id=session_id,
                )
                return raw
            append_action_history(
                {
                    "action": result.action_summary,
                    "result": result.outcome.value,
                    "narrative_summary": result.narration,
                },
                session_id=session_id,
            )
            return StreamingResponse(
                _stream_action_response(result),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Check for item use actions before routing to agent
        if _is_item_use_action(req.intent, req.approach):
            actor = get_actor(session_id=session_id)
            if actor is None:
                raise HTTPException(status_code=400, detail="No character found.")
            
            item_name = _parse_item_name(req.intent, req.approach)
            item_result = resolve_item_use(actor, item_name)
            
            if not item_result.success:
                raise HTTPException(status_code=400, detail=item_result.error_message)
            
            # Apply effects (HP change and inventory removal)
            apply_effects(item_result.effects or [], session_id=session_id)
            
            # Refresh actor to get updated HP
            actor = get_actor(session_id=session_id) or actor
            
            # Update combat state HP if in combat
            session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
            if session.game_phase == AdventurePhase.COMBAT:
                update_combatant_hp(actor.id, actor.hp)
            
            result = ActionResponse(
                action_summary=item_result.action_summary,
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=item_result.effects or [],
                item_use=item_result.item_use,
                narration=item_result.narration,
                scene_progression=item_result.scene_progression,
                gm_prompt=item_result.gm_prompt,
            )
            
            append_action_history(
                {
                    "action": result.action_summary,
                    "result": result.outcome.value,
                    "narrative_summary": (result.narration or "")[:400],
                },
                session_id=session_id,
            )
            
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

        try:
            # Check if this is a scene interaction action
            session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
            element = find_interactive_element(req.intent, session.scene.id)
            
            if element is not None:
                # Handle scene interaction with skill check
                result, _ = handle_scene_interaction(req, element)
            else:
                # Use agent orchestrator for non-scene interactions
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
            # Check if this is a movement action
            if is_movement_action(req.intent, req.approach):
                # Use the new movement handler
                movement_result = handle_movement(req.intent, req.approach, session_id)
                
                if movement_result.success:
                    # Movement successful - refresh session state
                    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                    
                    # Append movement to action history
                    append_action_history(
                        {
                            "action": f"移动: {req.intent}",
                            "result": "success",
                            "narrative_summary": movement_result.message,
                        },
                        session_id=session_id,
                    )
                else:
                    # Movement failed - still record it
                    append_action_history(
                        {
                            "action": f"尝试移动: {req.intent}",
                            "result": "failure",
                            "narrative_summary": movement_result.message,
                        },
                        session_id=session_id,
                    )
                    # Don't return error - let the agent provide narrative context
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
