"""Mapping and validation helpers for narration hard constraints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from ..models.action import ActionRequest, Effect, Outcome
from ..models.state import Actor, NarrativeHistoryEntry, Scene


FAILURE_HIT_INDICATORS = (
    " hits ",
    " hit ",
    " strikes ",
    " strike ",
    " struck ",
    " connected ",
    " lands cleanly",
    " landed cleanly",
    " wounds ",
    " wounded ",
    " slashes ",
    " pierces ",
    " succeeds ",
    " successful ",
    " easily ",
)

FAILURE_HEAL_INDICATORS = (
    " recovers ",
    " recovered ",
    " restored ",
    " restoration ",
    " closes the wound",
    " closes her wound",
    " closes his wound",
    " healing washes over",
)

FAILURE_CONDITION_REMOVE_INDICATORS = (
    " shakes off ",
    " throws off ",
    " recovers from ",
    " free of ",
    " no longer ",
    " breaks free ",
)

DEFEAT_INDICATORS = (
    " defeated",
    " defeat ",
    " slain",
    " kills ",
    " killed ",
    " dead",
    " collapses lifeless",
)


@dataclass(frozen=True)
class NarrationConstraintContext:
    """Single object describing rule-engine facts for narration."""

    outcome: Outcome
    check_result: Optional[dict] = None
    attack_result: Optional[dict] = None
    saving_throw_result: Optional[dict] = None
    effects: Optional[list[Effect]] = None
    actor: Optional[Actor] = None
    target: Optional[Actor] = None


def build_hard_constraints(context: NarrationConstraintContext) -> list[str]:
    """Render inviolable facts from rule resolution into prompt lines."""
    lines: list[str] = []

    outcome_cn = "成功" if context.outcome == Outcome.SUCCESS else "失败"
    lines.append(f"- 裁定结果 / Outcome: {outcome_cn} ({context.outcome.value})")

    if context.check_result:
        ability = context.check_result.get("ability", "")
        roll = context.check_result.get("roll", 0)
        total = context.check_result.get("total", 0)
        dc = context.check_result.get("dc", 0)
        modifier = context.check_result.get("modifier", 0)
        lines.append(
            f"- 检定详情 / Check: {ability.upper()}, 掷骰={roll}, 调整值={modifier}, 总计={total}, DC={dc}"
        )

    if context.attack_result:
        damage = context.attack_result.get("damage")

        if context.outcome == Outcome.SUCCESS:
            if damage:
                damage_total = int(damage.get("total", 0) or 0)
                lines.append("- 命中结果 / Attack: 命中 (HIT)")
                lines.append(f"- 伤害数值 / Damage: {damage_total} 点")
                if context.target:
                    new_hp = max(0, context.target.hp - damage_total)
                    lines.append(
                        f"- 目标状态 / Target State: {context.target.name} HP 从 {context.target.hp} 变为 {new_hp}"
                    )
            else:
                lines.append("- 命中结果 / Attack: 命中 (HIT)，但未造成伤害")
        else:
            lines.append("- 命中结果 / Attack: 未命中 (MISS)")
            lines.append("- 伤害数值 / Damage: 0 (攻击未命中，无伤害)")

    if context.saving_throw_result:
        ability = context.saving_throw_result.get("ability", "")
        roll = context.saving_throw_result.get("roll", 0)
        modifier = context.saving_throw_result.get("modifier", 0)
        total = context.saving_throw_result.get("total", 0)
        dc = context.saving_throw_result.get("dc", 0)
        outcome = context.saving_throw_result.get("outcome", "")
        lines.append(
            f"- 豁免详情 / Saving Throw: {ability.upper()}, 掷骰={roll}, 调整值={modifier}, 总计={total}, DC={dc}, 结果={outcome}"
        )

    for effect in context.effects or []:
        if effect.field == "hp" and isinstance(effect.delta, int):
            delta_str = f"+{effect.delta}" if effect.delta > 0 else str(effect.delta)
            lines.append(f"- 状态变更 / State Change: {effect.target} HP {delta_str}")
        elif effect.field == "conditions_add" and isinstance(effect.delta, str):
            lines.append(f"- 状态变更 / State Change: {effect.target} 获得状态 [{effect.delta}]")
        elif effect.field == "conditions_remove" and isinstance(effect.delta, str):
            lines.append(f"- 状态变更 / State Change: {effect.target} 移除状态 [{effect.delta}]")

    return lines


def build_narrative_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    context: NarrationConstraintContext,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> str:
    """Build the prompt with explicit hard-constraint and narrative sections."""
    lines: list[str] = []

    lines.append("【硬约束区 / HARD CONSTRAINTS】")
    lines.append("以下是由规则引擎裁定的确定事实，叙事必须与此完全一致，不可更改：")
    lines.append("")
    lines.extend(build_hard_constraints(context))
    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    lines.append("【叙事空间 / NARRATIVE SPACE】")
    lines.append("以下信息供叙事参考，你可以自由发挥：")
    lines.append("")
    lines.append(f"场景 / Scene: {scene.name}")
    lines.append(f"场景描述 / Scene Description: {scene.description}")
    lines.append("")
    lines.append(f"角色 / Character: {actor.name}")
    lines.append(f"角色描述 / Character Description: {actor.description}")
    character_class_str = actor.character_class.value if actor.character_class else "adventurer"
    lines.append(f"角色职业 / Character Class: {character_class_str}")
    lines.append(f"角色等级 / Level: 1 (熟练加值 / Proficiency: +{actor.proficiency_bonus})")
    lines.append(f"角色状态 / Character Status: HP {actor.hp}/{actor.hp_max}, AC {actor.ac}")
    lines.append("")

    if context.target:
        lines.append(f"目标 / Target: {context.target.name}")
        lines.append(
            f"目标状态 / Target Status: HP {context.target.hp}/{context.target.hp_max}, Conditions={context.target.conditions or []}"
        )
        lines.append("")

    lines.append("会话历史 / Session Narrative History:")
    if narrative_history:
        for idx, entry in enumerate(narrative_history, start=1):
            resolution_json = json.dumps(
                entry.resolution_summary,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            lines.append(f"{idx}. 行动: {entry.action_summary}")
            lines.append(f"   裁定: {resolution_json}")
            lines.append(f"   摘要: {entry.narration_summary}")
    else:
        lines.append("无。当前是本次会话中最早需要参考的动作。")
    lines.append("")

    lines.append(f"行动意图 / Action Intent: {req.intent}")
    lines.append(f"行动方式 / Action Approach: {req.approach}")

    if context.check_result:
        ability = context.check_result.get("ability", "")
        ability_desc = {
            "str": "力量与体格 / strength and physical power",
            "dex": "敏捷与灵巧 / agility and finesse",
            "con": "体质与耐力 / endurance and resilience",
            "int": "智力与学识 / intellect and knowledge",
            "wis": "感知与洞察 / perception and insight",
            "cha": "魅力与个性 / force of personality",
        }.get(ability, ability)
        lines.append(f"相关属性 / Relevant Ability: {ability_desc}")

    if context.attack_result:
        weapon = context.attack_result.get("weapon", "weapon")
        target_name = context.attack_result.get("target", "enemy")
        lines.append("")
        lines.append("战斗信息 / Combat Info:")
        lines.append(f"- 武器 / Weapon: {weapon}")
        lines.append(f"- 目标 / Target: {target_name}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("")
    lines.append("【写作指示 / WRITING INSTRUCTION】")
    lines.append("基于以上硬约束和叙事空间，返回一个 JSON 对象，包含 action_result、scene_progression、gm_prompt 三个字段。")
    lines.append("要求：")
    lines.append("1. 严格遵守硬约束区的事实，不得与之矛盾")
    lines.append("2. 如果结果是失败，绝对不能描述为成功或命中")
    lines.append("3. 如果伤害是0，绝对不能描述为造成伤害")
    lines.append("4. 使用生动的感官细节，避免系统术语")
    lines.append("5. scene_progression 负责描述动作结算后立刻发生的场景变化")
    lines.append("6. gm_prompt 必须像 GM 主动抛出的下一拍，包含明确暗示、压力或可响应事件")
    lines.append("7. gm_prompt 要尽量引用会话历史里的已发生事件，让场景呈现连续演进")
    lines.append('8. 仅返回 JSON，例如 {"action_result": "...", "scene_progression": "...", "gm_prompt": "..."}')

    return "\n".join(lines)


def find_contradictions(
    action_result: str,
    scene_progression: str,
    context: NarrationConstraintContext,
) -> list[str]:
    """Return explicit contradiction reasons for post-generation validation."""
    combined = f" {action_result.lower()} {scene_progression.lower()} "
    reasons: list[str] = []

    if context.outcome == Outcome.FAILURE:
        if any(indicator in combined for indicator in FAILURE_HIT_INDICATORS):
            reasons.append("failure_narrated_as_success_or_hit")

        if any(
            effect.field == "hp" and isinstance(effect.delta, int) and effect.delta > 0
            for effect in context.effects or []
        ) and any(indicator in combined for indicator in FAILURE_HEAL_INDICATORS):
            reasons.append("failed_healing_narrated_as_recovery")

        if any(
            effect.field == "conditions_remove" and isinstance(effect.delta, str)
            for effect in context.effects or []
        ) and any(indicator in combined for indicator in FAILURE_CONDITION_REMOVE_INDICATORS):
            reasons.append("failed_condition_removal_narrated_as_success")

    if context.attack_result:
        damage = context.attack_result.get("damage") or {}
        damage_total = int(damage.get("total", 0) or 0)

        if (context.outcome == Outcome.FAILURE or damage_total <= 0) and any(
            indicator in combined for indicator in FAILURE_HIT_INDICATORS
        ):
            reasons.append("zero_damage_or_miss_narrated_as_hit")

        if context.target and damage_total > 0:
            new_hp = max(0, context.target.hp - damage_total)
            if new_hp > 0 and any(indicator in combined for indicator in DEFEAT_INDICATORS):
                reasons.append("target_described_as_defeated_before_zero_hp")

    for effect in context.effects or []:
        if effect.field == "hp" and isinstance(effect.delta, int):
            if effect.delta > 0 and context.outcome == Outcome.SUCCESS:
                if "bleed" in combined or "worsens" in combined:
                    reasons.append("healing_narrated_as_damage")
            if effect.delta < 0 and context.outcome == Outcome.SUCCESS:
                if "restored" in combined or "healed" in combined:
                    reasons.append("damage_narrated_as_healing")
        if effect.field == "conditions_add" and isinstance(effect.delta, str):
            if f"free of {effect.delta.lower()}" in combined:
                reasons.append("condition_applied_but_narrated_as_removed")

    return list(dict.fromkeys(reasons))
