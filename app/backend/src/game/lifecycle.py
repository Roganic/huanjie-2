"""Player-facing lifecycle and shared action eligibility, derived from authoritative state."""
from fastapi import HTTPException
from ..models.state import AdventurePhase, CharacterCreateRequest
from .. import state


def play_status(session):
    actor = session.actor
    snapshot = session.combat_snapshot or {}
    if actor is None:
        mode, label, reason = "creation", "准备冒险", "请先创建角色。"
    elif actor.hp <= 0 or snapshot.get("status") == "defeat":
        mode, label = "defeated", "本次冒险已结束"
        reason = session.defeat_reason or f"{actor.name}在{session.scene.name}生命值耗尽，已经无法继续行动。"
    elif snapshot.get("status") == "active" or session.game_phase == AdventurePhase.COMBAT:
        mode, label, reason = "combat", "战斗中", "请完成当前战斗行动，或选择撤退。"
    elif session.game_phase == AdventurePhase.ENDED:
        mode, label, reason = "aftermath", "战斗已结束", "请先查看战斗结果并返回探索。"
    else:
        mode, label, reason = "exploration", "探索中", ""
    can_explore = mode == "exploration"
    world = session.world_scenes.get(session.scene.id)
    enemies = bool(world and any(e.hp > 0 for e in world.enemies.values()))
    rest_reason = reason if not can_explore else "此处仍有敌人，不能休息。请先离开或击败敌人。" if enemies else ""
    return {"mode": mode, "label": label, "reason": reason,
            "can_explore": can_explore, "can_rest": can_explore and not enemies,
            "rest_reason": rest_reason, "can_restart": actor is not None and mode != "combat"}


def require_exploration(session):
    status = play_status(session)
    if not status["can_explore"]:
        raise HTTPException(409, status["reason"])


def rest(session, kind):
    from .action_handler import handle_long_rest, handle_short_rest
    from .world import world_scene
    from .inventory import _finish
    require_exploration(session)
    if any(e.hp > 0 for e in world_scene(session).enemies.values()):
        raise HTTPException(409, "此处仍有敌人，不能休息。请先离开或击败敌人。")
    resources = rest_resources(session)
    if kind == "long" and not resources["can_long_rest"]:
        raise HTTPException(409, resources["long_rest_reason"])
    result = (handle_long_rest if kind == "long" else handle_short_rest)(session.actor, session.session_id)
    if not result["success"]:
        raise HTTPException(409, result["narration"])
    if kind == "long":
        from .conditions import remove_condition
        remove_condition(session.actor, "poisoned")
        if resources["cost"]:
            item = next(i for i in session.actor.inventory if i.id == resources["supply_item_id"])
            session.actor.inventory.remove(item)
            result["narration"] += " 消耗营地补给 ×1。"
    return _finish(session, result["narration"], effects=result.get("effects", []))


def rest_resources(session):
    from ..content.store import for_session
    pack = for_session(session)
    item_id = pack.supplies.item_id if pack.supplies else None
    quantity = sum(i.id == item_id for i in session.actor.inventory) if session.actor else 0
    safe = pack.scenes[session.scene.id].safe_rest
    cost = 1 if item_id and not safe else 0
    status = play_status(session)
    reason = status["rest_reason"] or ("营地补给不足，请返回酒馆或村庄整备。" if cost and not quantity else "")
    return dict(supply_item_id=item_id, quantity=quantity, safe=safe, cost=cost,
                can_long_rest=not reason, long_rest_reason=reason,
                description="安全地点长休不消耗补给" if safe else "野外长休消耗 1 份营地补给" if item_id else "此内容未启用补给消耗")


def restart_adventure(source):
    """Start a separate level-one run with the same character choices and pinned content."""
    if not play_status(source)["can_restart"]:
        raise HTTPException(409, "请先结束当前战斗，再重新冒险。")
    fresh = state.create_session()
    target = state._get_session(fresh.session_id, False)
    from ..content.store import for_session
    target.content_pack = for_session(source).model_copy(deep=True)
    state.create_character(CharacterCreateRequest(name=source.actor.name,
        character_class=source.actor.character_class, ability_generation="manual",
        abilities=source.actor.abilities.model_copy(deep=True)), target.session_id)
    return state.get_bootstrap_state(target.session_id)
