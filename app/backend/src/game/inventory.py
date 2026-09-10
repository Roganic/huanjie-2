"""Inventory commands shared by text input and direct controls."""
from fastapi import HTTPException
from .. import state
from ..content.store import for_session
from ..items.usage import resolve_item_use
from ..scene import get_scene_by_id


from .lifecycle import require_exploration


def _inventory(session):
    actor = session.actor
    stacks = {}
    for item in actor.inventory:
        if item.id not in stacks:
            stacks[item.id] = {**item.model_dump(mode="json"), "quantity": 0}
        stacks[item.id]["quantity"] += 1
    scene = get_scene_by_id(session.scene.id, for_session(session))
    collected = session.collected_items.get(session.scene.id, [])
    return {
        "items": list(stacks.values()),
        "equipped": actor.equipped.model_dump(mode="json"),
        "available_items": [item.model_dump(mode="json") for item in (scene.loot_items if scene else [])
                            if item.id not in collected],
    }


def _finish(session, message, **details):
    state._save_session(session)
    state.append_action_history({"action": message, "result": "success", "narrative_summary": message},
                                session_id=session.session_id)
    return {"success": True, "message": message, **details}


def pickup_item(session, item_id):
    require_exploration(session)
    scene = get_scene_by_id(session.scene.id, for_session(session))
    item = next((item for item in (scene.loot_items if scene else []) if item.id == item_id), None)
    if item is None:
        raise HTTPException(404, "当前位置没有这件物品。")
    collected = session.collected_items.setdefault(session.scene.id, [])
    if item.id in collected:
        raise HTTPException(409, "这件物品已经拾取。")
    session.actor.inventory.append(item.model_copy(deep=True))
    collected.append(item.id)
    return _finish(session, f"拾取了{item.name}。", inventory_update={"picked_up": item.model_dump(mode="json")})

def equip_item(session, item_id):
    require_exploration(session)
    item = next((item for item in session.actor.inventory if item.id == item_id), None)
    if item is None:
        raise HTTPException(404, "背包中没有这件物品。")
    result = state.equip_item_for_actor(item.id, session.session_id)
    if not result["success"]:
        raise HTTPException(400, result["error"])
    return _finish(session, f"已装备{item.name}。", inventory_update={"equipped": {"slot": "weapon" if item.type == "weapon" else "armor", "item": item.model_dump(mode="json")}})

def unequip_item(session, slot):
    require_exploration(session)
    result = state.unequip_item_from_actor(slot, session.session_id)
    if not result["success"]:
        raise HTTPException(400, result["error"])
    return _finish(session, "已卸下武器。" if slot == "weapon" else "已卸下护甲。")

def use_item(session, item_id):
    require_exploration(session)
    item = next((item for item in session.actor.inventory if item.id == item_id), None)
    if item is None:
        raise HTTPException(404, "背包中没有这件物品。")
    if item.effect_type != "cure_poison" and session.actor.hp >= session.actor.hp_max:
        raise HTTPException(409, "生命值已满，无需消耗药水。")
    result = resolve_item_use(session.actor, item.id)
    if not result.success:
        raise HTTPException(400, result.error_message)
    state.apply_effects(result.effects or [], session.session_id)
    from src.game.conditions import advance_time
    advance_time(session)
    return _finish(session, result.narration, effects=[e.model_dump(mode="json") for e in result.effects], item_use=result.item_use.model_dump(mode="json"))
