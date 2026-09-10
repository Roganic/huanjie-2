"""Explicit, model-independent controls for the core game systems."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import state
from ..game.commands import GameCommand, execute_command
from ..game.lifecycle import require_exploration, rest as rest_command, restart_adventure, play_status
from ..game.inventory import _inventory, pickup_item, equip_item, unequip_item, use_item
from ..rules.experience import get_next_level_xp, get_xp_progress, SUPPORTED_LEVEL_CAP

router = APIRouter(tags=["gameplay"])


@router.get("/exploration")
def exploration(request: Request):
    from ..game.exploration import guidance
    with state._SESSION_LOCK:
        return guidance(_session(request))


class ItemRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=128)


class UnequipRequest(BaseModel):
    slot: Literal["weapon", "armor"]


class MoveRequest(BaseModel):
    target_scene_id: str = Field(min_length=1, max_length=128)


class RestRequest(BaseModel):
    kind: Literal["short", "long"]


def _session(request: Request, *, mutate: bool = False):
    sid = request.headers.get("X-Session-Id")
    if not sid:
        raise HTTPException(400, "请先创建角色。")
    try:
        session = state._get_session(sid, create_if_missing=False)
    except KeyError as exc:
        raise HTTPException(404, "会话不存在或已失效。") from exc
    if session.actor is None:
        raise HTTPException(409, "请先创建角色。")
    if mutate:
        require_exploration(session)
    return session


@router.get("/inventory")
def inventory(request: Request):
    with state._SESSION_LOCK:
        return _inventory(_session(request))


@router.post("/inventory/pickup")
def pickup(req: ItemRequest, request: Request):
    with state._SESSION_LOCK:
        return execute_command(_session(request).session_id, GameCommand(kind='pickup', target_id=req.item_id))['result']


@router.post("/inventory/equip")
def equip(req: ItemRequest, request: Request):
    with state._SESSION_LOCK:
        return execute_command(_session(request).session_id, GameCommand(kind='equip', target_id=req.item_id))['result']


@router.post("/inventory/unequip")
def unequip(req: UnequipRequest, request: Request):
    with state._SESSION_LOCK:
        return execute_command(_session(request).session_id, GameCommand(kind='unequip', target_id=req.slot))['result']


@router.post("/inventory/use")
def use(req: ItemRequest, request: Request):
    with state._SESSION_LOCK:
        return execute_command(_session(request).session_id, GameCommand(kind='use', target_id=req.item_id))['result']


@router.post("/map/move")
def move(req: MoveRequest, request: Request):
    with state._SESSION_LOCK:
        session = _session(request, mutate=True)
        from ..game.world import move_to
        return execute_command(session.session_id, GameCommand(kind='move', target_id=req.target_scene_id))['result']


@router.post("/character/rest")
def rest(req: RestRequest, request: Request):
    with state._SESSION_LOCK:
        session = _session(request, mutate=True)
        return execute_command(session.session_id, GameCommand(kind='rest', action=req.kind))['result']


@router.post("/session/restart")
def restart(request: Request):
    with state._SESSION_LOCK:
        return restart_adventure(_session(request))

@router.get("/character/progression")
def progression(request: Request):
    with state._SESSION_LOCK:
        session = _session(request)
        actor = session.actor
        from ..game.journey import journey_view
        return {"journey": journey_view(session), "level_cap": SUPPORTED_LEVEL_CAP, "supported_levels": [1, SUPPORTED_LEVEL_CAP],
                "play_status": play_status(session), "level": actor.level, "experience_points": actor.experience_points,
                "next_level_xp": get_next_level_xp(actor.level),
                "progress": get_xp_progress(actor.experience_points, actor.level),
                "skills": [skill.model_dump() for skill in actor.skills],
                "hit_dice_remaining": actor.hit_dice_remaining, "hit_dice_total": actor.hit_dice_total,
                "can_short_rest": (actor.hp < actor.hp_max and actor.hit_dice_remaining > 0)
                    or actor.class_features.second_wind_used or actor.class_features.action_surge_used}


@router.get('/events')
def events(request: Request):
    from ..game.events import event_view
    with state._SESSION_LOCK:
        session = _session(request)
        return {'clock': session.event_clock.model_dump(), 'pending': event_view(session),
            'facts': [e for e in session.event_facts if e.get('visible', True)],
            'resolved': [{'id': e.id, 'title': e.spec.title, 'status': e.status, 'reason': e.reason}
                         for e in session.scheduled_events.values() if e.spec.visible and e.status != 'scheduled']}
