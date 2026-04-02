"""游戏动作处理模块 - 法术施放和长休处理。

本模块提供：
1. handle_spell_cast: 处理法术施放动作，返回包含标准字段的响应
2. handle_long_rest: 处理长休动作，恢复所有法术槽
3. is_spell_cast_intent: 检测意图是否为施法命令
4. is_rest_intent: 检测意图是否为休息命令
"""

from __future__ import annotations

import re
from typing import Optional


# ---------------------------------------------------------------------------
# 意图检测
# ---------------------------------------------------------------------------

_CAST_KEYWORDS = ["施放", "cast", "使用法术"]
_SPELL_NAMES_CN = [
    "魔法飞弹", "火球术", "燃烧之手", "治疗之触", "治疗术", "寒冰射线",
]
_SPELL_NAMES_EN = [
    "magic missile", "fireball", "burning hands", "cure wounds", "ray of frost",
]

# 治疗性法术列表（目标为施法者自身）
_HEALING_SPELL_IDS = {"cure_wounds"}

_LONG_REST_KEYWORDS = ["长休", "long rest"]
_SHORT_REST_KEYWORDS = ["短休", "short rest"]


def is_spell_cast_intent(intent: str) -> bool:
    """检测意图是否为施法命令。"""
    intent_lower = intent.lower()
    has_cast_kw = any(kw in intent_lower for kw in _CAST_KEYWORDS)
    has_spell_name = any(name.lower() in intent_lower for name in _SPELL_NAMES_CN + _SPELL_NAMES_EN)
    return has_cast_kw and has_spell_name


def is_rest_intent(intent: str) -> tuple[bool, str]:
    """检测意图是否为休息命令。

    Returns:
        (is_rest, rest_type) 其中 rest_type 是 "short" 或 "long"
    """
    intent_lower = intent.lower()
    for kw in _SHORT_REST_KEYWORDS:
        if kw in intent_lower:
            return True, "short"
    for kw in _LONG_REST_KEYWORDS:
        if kw in intent_lower:
            return True, "long"
    return False, ""


# ---------------------------------------------------------------------------
# 法术施放处理
# ---------------------------------------------------------------------------

def handle_spell_cast(
    intent: str,
    actor,
    session_id: Optional[str] = None,
) -> Optional[dict]:
    """处理法术施放动作。

    Args:
        intent: 玩家意图字符串
        actor: 施法者 Actor 对象
        session_id: 会话 ID

    Returns:
        包含法术裁定结果的字典，包含以下字段：
        - spell_name: 法术名称
        - spell_level: 法术环级
        - slot_used: 消耗的法术槽环级
        - damage_roll: 每次骰子结果列表
        - damage_total: 总伤害值
        - success: 是否成功
        - error_message: 错误信息（失败时）
        - narration: 叙事文本
        返回 None 如果不是施法命令
    """
    if not is_spell_cast_intent(intent):
        return None

    # 解析法术名
    spell_name = _parse_spell_name(intent)
    if spell_name is None:
        return None

    try:
        from ..spells.spell_registry import get_spell
        from ..spells.spell_resolver import cast_spell, can_cast_spell
        from ..state import get_enemy, apply_effects
        from ..models.action import Effect
    except ImportError as e:
        return {
            "spell_name": spell_name,
            "spell_level": 0,
            "slot_used": 0,
            "damage_roll": [],
            "damage_total": 0,
            "success": False,
            "error_message": f"系统错误: {e}",
            "narration": "施法失败。",
        }

    # 查找法术（优先使用 spell ID 避免别名覆盖问题）
    lookup_name = _SPELL_NAME_TO_ID.get(spell_name, spell_name)
    spell = get_spell(lookup_name)
    if spell is None:
        return {
            "spell_name": spell_name,
            "spell_level": 0,
            "slot_used": 0,
            "damage_roll": [],
            "damage_total": 0,
            "success": False,
            "error_message": f"未知法术: {spell_name}",
            "narration": f"未找到法术 {spell_name}。",
            "effect_type": "none",
            "roll_result": [],
            "damage": 0,
            "heal": 0,
        }

    # 检查是否可以施放
    can_cast, error = can_cast_spell(actor, spell)
    if not can_cast:
        return {
            "spell_name": spell.name_cn,
            "spell_level": spell.level,
            "slot_used": 0,
            "damage_roll": [],
            "damage_total": 0,
            "success": False,
            "error_message": error,
            "narration": error,
        }

    # 判断目标：治疗法术以施法者为目标，伤害法术以敌人为目标
    is_healing_spell = spell.id in _HEALING_SPELL_IDS
    if is_healing_spell:
        target = actor
    else:
        target = get_enemy(session_id=session_id)

    # 施放法术（消耗法术槽）
    result = cast_spell(actor, spell_name, target)

    if not result.success:
        return {
            "spell_name": result.spell_name,
            "spell_level": result.slot_level,
            "slot_used": 0,
            "damage_roll": [],
            "damage_total": 0,
            "success": False,
            "error_message": result.error_message or "施法失败。",
            "narration": result.error_message or "施法失败。",
            # 新验收标准字段
            "effect_type": "none",
            "roll_result": [],
            "damage": 0,
            "heal": 0,
        }

    # 构建效果列表
    effects = []
    if result.slot_level > 0:
        effects.append(Effect(
            target=actor.id,
            field="spell_slot_consumed",
            delta=result.slot_level,
            description=f"消耗 {result.slot_level} 环法术位",
        ))

    damage_total = result.damage or 0
    heal_amount = 0

    if is_healing_spell:
        # 治疗法术：恢复施法者 HP（不超过 hp_max）
        heal_amount = abs(damage_total)
        if heal_amount > 0:
            effects.append(Effect(
                target=actor.id,
                field="hp",
                delta=heal_amount,
                description=f"{actor.name} 恢复 {heal_amount} 点生命值",
            ))
        effect_type = "heal"
    elif damage_total > 0 and target is not None:
        # 伤害法术：对目标造成伤害
        effects.append(Effect(
            target=target.id,
            field="hp",
            delta=-damage_total,
            description=f"{target.name} 受到 {damage_total} 点伤害",
        ))
        effect_type = "damage"
    else:
        effect_type = "none"

    # 持久化效果
    try:
        apply_effects(effects, session_id=session_id)
    except Exception:
        pass

    return {
        "spell_name": result.spell_name,
        "spell_level": result.slot_level,
        "slot_used": result.slot_level,
        "damage_roll": result.damage_rolls,
        "damage_total": damage_total if not is_healing_spell else 0,
        "success": True,
        "error_message": None,
        "narration": result.narrative,
        "effects": [e.model_dump() for e in effects],
        # 新验收标准字段
        "effect_type": effect_type,
        "roll_result": result.damage_rolls,
        "damage": damage_total if not is_healing_spell else 0,
        "heal": heal_amount,
    }


def _parse_spell_name(intent: str) -> Optional[str]:
    """从意图字符串中解析法术名称。"""
    # 中文法术名
    for name in _SPELL_NAMES_CN:
        if name in intent:
            return name

    # 英文法术名（不区分大小写）
    intent_lower = intent.lower()
    for name in _SPELL_NAMES_EN:
        if name.lower() in intent_lower:
            return name

    # 尝试从"施放X"模式提取
    match = re.search(r'施放\s*([\u4e00-\u9fa5]+)', intent)
    if match:
        return match.group(1).strip()

    match = re.search(r'cast\s+(\w+(?:\s+\w+)*)', intent, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


# 法术名称到 spell ID 的映射（用于避免别名覆盖问题）
_SPELL_NAME_TO_ID: dict[str, str] = {
    "治疗术": "cure_wounds",
    "治疗之触": "cure_wounds",
    "cure wounds": "cure_wounds",
}


# ---------------------------------------------------------------------------
# 长休处理
# ---------------------------------------------------------------------------

def handle_long_rest(
    actor,
    session_id: Optional[str] = None,
) -> dict:
    """处理长休动作，恢复所有法术槽和HP。

    Args:
        actor: 执行长休的 Actor 对象
        session_id: 会话 ID

    Returns:
        包含长休结果的字典：
        - success: 是否成功
        - hp_restored: 恢复的HP
        - spell_slots_restored: 是否有法术槽被恢复
        - narration: 叙事文本
        - effects: 效果列表
    """
    try:
        from ..game.state import restore_all_spell_slots
        from ..state import _get_session, _resolve_session_id, _save_session
        from ..models.action import Effect
    except ImportError as e:
        return {
            "success": False,
            "hp_restored": 0,
            "spell_slots_restored": False,
            "narration": f"长休失败: {e}",
            "effects": [],
        }

    effects = []

    # 恢复 HP 到最大值
    hp_restored = actor.hp_max - actor.hp
    if hp_restored > 0:
        effects.append(Effect(
            target=actor.id,
            field="hp",
            delta=hp_restored,
            description=f"长休恢复 {hp_restored} 点生命值",
        ))

    # 恢复法术槽
    spell_slots_restored = restore_all_spell_slots(session_id or "")

    if spell_slots_restored:
        effects.append(Effect(
            target=actor.id,
            field="spell_slots_restored",
            delta=1,
            description="所有法术位已恢复",
        ))

    # 应用 HP 效果
    if hp_restored > 0:
        try:
            from ..state import apply_effects
            apply_effects(effects[:1], session_id=session_id)
        except Exception:
            pass

    # 构建叙事
    parts = [f"{actor.name} 完成长休。"]
    if hp_restored > 0:
        parts.append(f"HP 恢复至满值。")
    if spell_slots_restored:
        parts.append("所有法术位已恢复。")

    narration = " ".join(parts)

    return {
        "success": True,
        "hp_restored": hp_restored,
        "spell_slots_restored": spell_slots_restored,
        "narration": narration,
        "effects": [e.model_dump() for e in effects],
    }


def handle_short_rest(
    actor,
    session_id: Optional[str] = None,
) -> dict:
    """处理短休动作（不恢复法术槽）。

    Args:
        actor: 执行短休的 Actor 对象
        session_id: 会话 ID

    Returns:
        包含短休结果的字典
    """
    return {
        "success": True,
        "hp_restored": 0,
        "spell_slots_restored": False,
        "narration": f"{actor.name} 完成短休。法师的法术位只能通过长休恢复。",
        "effects": [],
    }
