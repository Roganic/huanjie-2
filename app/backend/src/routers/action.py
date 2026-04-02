"""Player action endpoint with streamed narration output."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..agent.orchestrator import resolve_action_with_agent
from ..models.action import ActionRequest, ActionResponse, InventoryUpdate, Outcome, ResolutionType
from ..models.state import AdventurePhase
from ..scene import get_scene_transition, build_scene_context_for_prompt, get_scene_by_id
from ..state import (
    has_character,
    require_bootstrap_state,
    reset_current_session,
    set_combat_scene,
    set_current_session,
    switch_scene,
    pick_up_item,
    equip_item,
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


def _is_pickup_action(intent: str, approach: str) -> bool:
    """Check if action is a pick-up item action."""
    text = f"{intent} {approach}".lower()
    return "拾取" in text or "pick up" in text


def _is_equip_action(intent: str, approach: str) -> bool:
    """Check if action is an equip item action."""
    text = f"{intent} {approach}".lower()
    return "装备" in text or "equip" in text


def _extract_item_name(intent: str, approach: str) -> str | None:
    """Extract item name from pickup/equip intent.
    
    Supports patterns like:
    - 拾取长剑 -> longsword
    - 装备皮甲 -> leather
    - pick up the dagger -> dagger
    - equip leather armor -> leather
    """
    text = f"{intent} {approach}".lower().strip()
    
    # Chinese patterns
    for prefix in ["拾取", "装备"]:
        if prefix in text:
            idx = text.index(prefix) + len(prefix)
            remainder = text[idx:].strip()
            # Take only up to first space or punctuation
            import re
            match = re.match(r"([^\s，。！？.!?]+)", remainder)
            if match:
                return match.group(1)
    
    # English patterns
    for prefix in ["pick up", "equip"]:
        if prefix in text:
            idx = text.index(prefix) + len(prefix)
            remainder = text[idx:].strip()
            # Remove articles
            for article in ["the ", "a ", "an "]:
                if remainder.startswith(article):
                    remainder = remainder[len(article):]
            # Take first word
            import re
            match = re.match(r"([^\s.,!?]+)", remainder)
            if match:
                return match.group(1)
    
    return None


# Item name to ID mapping
_ITEM_NAME_MAP: dict[str, str] = {
    "长剑": "longsword",
    "短剑": "shortsword",
    "匕首": "dagger",
    "法杖": "quarterstaff",
    "锁甲": "chain_mail",
    "皮甲": "leather",
    "布袍": "robe",
    "longsword": "longsword",
    "shortsword": "shortsword",
    "dagger": "dagger",
    "quarterstaff": "quarterstaff",
    "chain mail": "chain_mail",
    "leather": "leather",
    "leather armor": "leather",
    "robe": "robe",
}


def _resolve_item_id(item_name: str) -> str | None:
    """Resolve an item name (Chinese or English) to an item ID."""
    return _ITEM_NAME_MAP.get(item_name.lower().strip())


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

        try:
            result = await asyncio.to_thread(resolve_action_with_agent, req)
        except Exception as exc:  # pragma: no cover - surfaced to client as SSE error
            error_message = str(exc)

            async def error_stream() -> AsyncIterator[str]:
                yield _sse_event("error", {"message": error_message})

            return StreamingResponse(error_stream(), media_type="text/event-stream")

        # Handle pickup and equip actions directly
        if _is_pickup_action(req.intent, req.approach) or _is_equip_action(req.intent, req.approach):
            item_name = _extract_item_name(req.intent, req.approach)
            item_id = _resolve_item_id(item_name) if item_name else None
            
            if item_id is None:
                return ActionResponse(
                    action_summary=f"{req.actor} attempts to interact with an item",
                    resolution_type=ResolutionType.AUTO_SUCCESS,
                    outcome=Outcome.FAILURE,
                    effects=[],
                    narration=f"你没有找到名为 '{item_name or '未知'}' 的物品。",
                    scene_progression="你可以尝试拾取场景中可见的物品。",
                    gm_prompt="请确认物品名称是否正确。",
                )
            
            is_pickup = _is_pickup_action(req.intent, req.approach)
            inventory_update = None
            
            if is_pickup:
                result = pick_up_item(item_id, session_id)
                if result is None:
                    return ActionResponse(
                        action_summary=f"{req.actor} 尝试拾取 {item_name}",
                        resolution_type=ResolutionType.AUTO_SUCCESS,
                        outcome=Outcome.FAILURE,
                        effects=[],
                        narration=f"你无法拾取 {item_name}（物品不存在或已在背包中）。",
                        scene_progression="检查场景中是否有该物品。",
                        gm_prompt="请确认物品名称。",
                    )
                inventory_update = InventoryUpdate(
                    picked_up=result["picked_up"],
                    inventory=result["inventory"],
                )
                narration = f"你拾起了 {result['picked_up']['name']}，它现在在你的背包中了。"
            else:
                result = equip_item(item_id, session_id)
                if result is None:
                    return ActionResponse(
                        action_summary=f"{req.actor} 尝试装备 {item_name}",
                        resolution_type=ResolutionType.AUTO_SUCCESS,
                        outcome=Outcome.FAILURE,
                        effects=[],
                        narration=f"你无法装备 {item_name}（物品不在背包中或无法装备）。",
                        scene_progression="先拾取物品，再尝试装备。",
                        gm_prompt="请确认该物品已在你的背包中。",
                    )
                inventory_update = InventoryUpdate(
                    equipped=result["equipped"],
                    inventory=result["inventory"],
                )
                slot_name = "武器" if result["equipped"]["slot"] == "weapon" else "护甲"
                narration = f"你装备了 {result['equipped']['item']['name']} 作为{slot_name}。"
            
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            response = ActionResponse(
                action_summary=f"{req.actor} {'拾取' if is_pickup else '装备'}了 {item_name}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=[],
                inventory_update=inventory_update,
                narration=narration,
                scene_progression="你的装备状态已更新。",
                gm_prompt="继续探索或采取下一步行动。",
            )
            
            if not accepts_stream:
                return response
            
            async def pickup_stream() -> AsyncIterator[str]:
                yield _sse_event(
                    "start",
                    {
                        "action_summary": response.action_summary,
                        "resolution_type": response.resolution_type.value,
                        "outcome": response.outcome.value,
                    },
                )
                yield _sse_event("complete", response.model_dump(mode="json"))
            
            return StreamingResponse(pickup_stream(), media_type="text/event-stream")
        
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
