"""游戏状态管理模块 - 提供角色状态查询接口。

本模块提供 get_character_rest_status 等状态查询函数，
供 routers/state.py 的 GET /state 端点使用。
"""

from __future__ import annotations

from typing import Optional


def get_character_rest_status(session_id: str) -> Optional[dict]:
    """获取角色的休息状态，包括生命骰和法术槽信息。

    Args:
        session_id: 会话 ID

    Returns:
        包含以下字段的字典：
        - hit_dice_remaining: 剩余生命骰数量
        - hit_dice_total: 生命骰总数
        - spell_slots: 当前法术槽列表 [{level, current, max}, ...]
        - spell_slots_max: 最大法术槽列表 [{level, max}, ...]
        如果没有角色则返回 None
    """
    try:
        from ..state import get_actor
        actor = get_actor(session_id=session_id)
    except Exception:
        return None

    if actor is None:
        return None

    hit_dice_total = actor.hit_dice_total
    hit_dice_remaining = actor.hit_dice_remaining

    # 法术槽信息
    spell_slots = [
        {"level": slot.level, "current": slot.current, "max": slot.max}
        for slot in actor.spell_slots
    ]
    spell_slots_max = [
        {"level": slot.level, "max": slot.max}
        for slot in actor.spell_slots
    ]

    return {
        "hit_dice_remaining": hit_dice_remaining,
        "hit_dice_total": hit_dice_total,
        "spell_slots": spell_slots,
        "spell_slots_max": spell_slots_max,
    }


def restore_all_spell_slots(session_id: str) -> bool:
    """恢复角色所有法术槽到最大值（长休使用）。

    Args:
        session_id: 会话 ID

    Returns:
        True 如果有法术槽被恢复，False 否则
    """
    try:
        from ..state import _get_session, _resolve_session_id, _save_session
        resolved_id = _resolve_session_id(session_id)
        session = _get_session(resolved_id, create_if_missing=False)
    except (KeyError, Exception):
        return False

    if session.actor is None or not session.actor.spell_slots:
        return False

    restored = False
    new_slots = []
    for slot in session.actor.spell_slots:
        if slot.current < slot.max:
            restored = True
            new_slots.append(slot.model_copy(update={"current": slot.max}))
        else:
            new_slots.append(slot)

    if restored:
        session.actor = session.actor.model_copy(update={"spell_slots": new_slots})
        _save_session(session)

    return restored
