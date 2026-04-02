"""Mapping and validation helpers for narration hard constraints."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..models.action import ActionRequest, Effect, Outcome
from ..models.state import Actor, NarrativeHistoryEntry, Scene
from ..state import get_combat_state

logger = logging.getLogger(__name__)

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

# Patterns for detecting unauthorized numeric declarations in narrative
# These patterns indicate AI trying to override rule engine authority
UNAUTHORIZED_HP_PATTERNS = [
    # Chinese HP change patterns
    re.compile(r"HP\s*变为\s*\d+"),
    re.compile(r"生命值\s*变为\s*\d+"),
    re.compile(r"血量\s*变为\s*\d+"),
    re.compile(r"生命\s*变为\s*\d+"),
    re.compile(r"HP\s*变成\s*\d+"),
    re.compile(r"生命值\s*变成\s*\d+"),
    re.compile(r"现在\s*(?:有|剩|余)\s*\d+\s*(?:点)?\s*(?:HP|生命|血量)"),
    re.compile(r"(?:HP|生命|血量)\s*(?:现在|目前)\s*(?:是|为|有)\s*\d+"),
    # English HP change patterns
    re.compile(r"HP\s*(?:becomes?|is\s*now|drops?\s*to|falls?\s*to)\s*\d+"),
    re.compile(r"(?:has|have)\s*\d+\s*(?:HP|hit\s*points?|health)\s*(?:left|remaining)?"),
    re.compile(r"(?:now\s*)?(?:has|have|with)\s*\d+\s*(?:HP|hit\s*points?)"),
]

UNAUTHORIZED_RESOURCE_GAIN_PATTERNS = [
    # Chinese gain patterns
    re.compile(r"你\s*(?:获得|得到|增加)\s*\d+\s*(?:点)?"),
    re.compile(r"(?:获得|得到|增加)\s*\d+\s*(?:点)?\s*(?:HP|生命|血量|伤害|攻击)"),
    # English gain patterns
    re.compile(r"(?:you\s*)?(?:gain|get|receive|obtain|acquire)\s*\d+\s*(?:HP|hit\s*points?|health|damage|attack)"),
]

UNAUTHORIZED_RESOURCE_LOSS_PATTERNS = [
    # Chinese loss patterns  
    re.compile(r"你\s*(?:失去|损失|减少)\s*\d+\s*(?:点)?"),
    re.compile(r"(?:失去|损失|减少)\s*\d+\s*(?:点)?\s*(?:HP|生命|血量)"),
    # English loss patterns
    re.compile(r"(?:you\s*)?(?:lose|take)\s*\d+\s*(?:HP|hit\s*points?|damage|health)"),
]

UNAUTHORIZED_DAMAGE_ANNOUNCEMENT_PATTERNS = [
    # Chinese damage announcement patterns
    re.compile(r"(?:造成|受到|受到|承受)\s*\d+\s*(?:点)?\s*(?:伤害|damage)"),
    re.compile(r"\d+\s*(?:点)?\s*(?:伤害|damage)\s*(?:点数)?"),
    # English damage announcement patterns
    re.compile(r"(?:deals?|takes?|took|suffers?|inflicts?)\s*\d+\s*(?:points?\s*of\s*)?damage"),
    re.compile(r"\d+\s*(?:points?\s*of\s*)?damage"),
]

UNAUTHORIZED_HEALING_ANNOUNCEMENT_PATTERNS = [
    # Chinese healing patterns
    re.compile(r"(?:恢复|回复|治疗)\s*\d+\s*(?:点)?\s*(?:HP|生命|血量|health)"),
    re.compile(r"\d+\s*(?:点)?\s*(?:HP|生命|血量)\s*(?:恢复|回复|治疗)"),
    # English healing patterns
    re.compile(r"(?:heals?|restores?|recovers?)\s*\d+\s*(?:HP|hit\s*points?|health)"),
    re.compile(r"\d+\s*(?:HP|hit\s*points?)\s*(?:healed|restored|recovered)"),
]

UNAUTHORIZED_AC_PATTERNS = [
    # Chinese AC patterns
    re.compile(r"AC\s*变为\s*\d+"),
    re.compile(r"护甲值\s*变为\s*\d+"),
    re.compile(r"AC\s*变成\s*\d+"),
    # English AC patterns
    re.compile(r"AC\s*(?:becomes?|is\s*now)\s*\d+"),
    re.compile(r"armor\s*class\s*(?:becomes?|is\s*now)\s*\d+"),
]

ALL_UNAUTHORIZED_PATTERNS = (
    UNAUTHORIZED_HP_PATTERNS
    + UNAUTHORIZED_RESOURCE_GAIN_PATTERNS
    + UNAUTHORIZED_RESOURCE_LOSS_PATTERNS
    + UNAUTHORIZED_DAMAGE_ANNOUNCEMENT_PATTERNS
    + UNAUTHORIZED_HEALING_ANNOUNCEMENT_PATTERNS
    + UNAUTHORIZED_AC_PATTERNS
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
    # Combat-specific context
    combat_round: Optional[int] = None
    is_combat_ended: Optional[bool] = None
    combat_outcome: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of post-processing validation."""
    is_valid: bool
    violations: list[str]
    marked_narrative: Optional[str] = None


def build_hard_constraints(context: NarrationConstraintContext) -> list[str]:
    """Render inviolable facts from rule resolution into prompt lines."""
    lines: list[str] = []

    outcome_cn = "成功" if context.outcome == Outcome.SUCCESS else "失败"
    lines.append(f"- 裁定结果 / Outcome: {outcome_cn} ({context.outcome.value})")
    
    # Add combat-specific constraints
    if context.combat_round is not None:
        lines.append(f"- 战斗回合 / Combat Round: 第 {context.combat_round} 回合")
    
    if context.is_combat_ended:
        outcome_str = context.combat_outcome or "ended"
        lines.append(f"- 战斗结束 / Combat Ended: {outcome_str}")

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
    lines.append(f"角色等级 / Level: {actor.level} (熟练加值 / Proficiency: +{actor.proficiency_bonus})")
    lines.append(f"角色状态 / Character Status: HP {actor.hp}/{actor.hp_max}, AC {actor.ac}")
    lines.append(
        f"关键属性 / Key Abilities: "
        f"STR {actor.abilities.str_} ({actor.abilities.modifier('str'):+d}), "
        f"DEX {actor.abilities.dex} ({actor.abilities.modifier('dex'):+d}), "
        f"CON {actor.abilities.con} ({actor.abilities.modifier('con'):+d}), "
        f"INT {actor.abilities.int_} ({actor.abilities.modifier('int'):+d}), "
        f"WIS {actor.abilities.wis} ({actor.abilities.modifier('wis'):+d}), "
        f"CHA {actor.abilities.cha} ({actor.abilities.modifier('cha'):+d})"
    )
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
        hit = context.attack_result.get("hit")
        damage = context.attack_result.get("damage")
        
        lines.append("")
        lines.append("战斗裁定 / COMBAT RESOLUTION:")
        lines.append(f"- 攻击方 / Attacker: {context.actor.name if context.actor else 'unknown'}")
        lines.append(f"- 防御方 / Defender: {target_name}")
        lines.append(f"- 命中结果 / Hit Result: {'命中 / HIT' if hit else '未命中 / MISS'}")
        if damage and hit:
            damage_total = damage.get("total", 0) if isinstance(damage, dict) else 0
            lines.append(f"- 伤害数值 / Damage Value: {damage_total}")
        else:
            lines.append("- 伤害数值 / Damage Value: 0")
        if context.target:
            lines.append(f"- 攻击方当前HP / Attacker Current HP: {context.actor.hp if context.actor else 'unknown'}")
            lines.append(f"- 防御方当前HP / Defender Current HP: {context.target.hp}")
            if context.target.hp == 0:
                lines.append("- 战斗结果 / Combat Result: 敌方被击败 / ENEMY DEFEATED")
        
        # Add combat round info if available
        if context.combat_round is not None:
            lines.append(f"- 当前回合 / Current Round: 第 {context.combat_round} 回合")
        
        # Add initiative order from combat state
        try:
            combat_state = get_combat_state()
            if combat_state.turn_order:
                turn_order_names = []
                for idx, cid in enumerate(combat_state.turn_order):
                    name = combat_state.combatant_names.get(cid, cid)
                    if cid == (context.actor.id if context.actor else None):
                        name = f"{name} (当前行动 / CURRENT)"
                    turn_order_names.append(name)
                lines.append(f"- 先攻顺序 / Initiative Order: {' -> '.join(turn_order_names)}")
            if combat_state.combatant_hp:
                hp_lines = []
                for cid, hp in combat_state.combatant_hp.items():
                    name = combat_state.combatant_names.get(cid, cid)
                    hp_lines.append(f"{name}: {hp} HP")
                lines.append(f"- 战场HP / Battlefield HP: {', '.join(hp_lines)}")
        except Exception:
            pass

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
    
    # Add combat-specific narrative guidance
    if context.attack_result:
        lines.append("")
        lines.append("【战斗叙事专项要求 / COMBAT NARRATIVE REQUIREMENTS】")
        lines.append("- 必须根据命中/未命中结果描述相应的战斗场景")
        lines.append("- 命中时：描述武器击中的感官细节（碰撞、伤口、冲击感），但不得宣布具体伤害数字")
        lines.append("- 未命中时：描述闪避、格挡、或攻击落空的动态，不得描述造成伤害")
        lines.append("- 参考双方HP比例描述战斗的紧张程度")
        lines.append("- 连续战斗回合中，要引用之前的战斗事件保持连贯性")
        if context.is_combat_ended:
            lines.append("- 这是战斗结束回合：必须生成战斗终结叙事，描述敌人倒下的场景")
            lines.append("- 不要提出战斗中的选择，而是转向战后的场景描写")
        elif context.combat_round and context.combat_round > 1:
            lines.append(f"- 这是第 {context.combat_round} 回合，叙事应体现战斗的持续节奏和累积的疲劳")
    
    lines.append('')
    lines.append('仅返回 JSON，例如 {"action_result": "...", "scene_progression": "...", "gm_prompt": "..."}')

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


def detect_unauthorized_numeric_declarations(text: str) -> list[dict]:
    """Detect unauthorized numeric declarations in narrative text.
    
    This function scans the narrative for patterns that indicate the AI is trying
    to override rule engine authority by declaring numerical values directly.
    
    Args:
        text: The narrative text to scan
        
    Returns:
        List of violation dictionaries with pattern type and matched text
    """
    violations: list[dict] = []
    text_normalized = text.lower().replace("", "").replace("", "")
    
    # Check all unauthorized patterns
    for pattern in ALL_UNAUTHORIZED_PATTERNS:
        for match in pattern.finditer(text):
            violations.append({
                "type": "unauthorized_numeric_declaration",
                "pattern": pattern.pattern[:50] + "..." if len(pattern.pattern) > 50 else pattern.pattern,
                "matched_text": match.group(0),
                "position": match.start(),
            })
    
    # Additional manual checks for common patterns not easily captured by regex
    unauthorized_phrases = [
        ("HP 变为", "hp_change"),
        ("hp 变为", "hp_change"),
        ("生命值变为", "hp_change"),
        ("血量变为", "hp_change"),
        ("你获得", "resource_gain"),
        ("你失去", "resource_loss"),
        ("造成", "damage_announcement"),
        ("点伤害", "damage_announcement"),
        ("恢复", "healing_announcement"),
        ("点生命", "healing_announcement"),
    ]
    
    for phrase, violation_type in unauthorized_phrases:
        if phrase in text:
            # Check if it's followed by a number (basic heuristic)
            idx = text.find(phrase)
            if idx >= 0:
                after_phrase = text[idx + len(phrase):idx + len(phrase) + 10]
                if any(c.isdigit() for c in after_phrase):
                    violations.append({
                        "type": violation_type,
                        "pattern": f"{phrase} + number",
                        "matched_text": phrase,
                        "position": idx,
                    })
    
    return violations


def validate_narrative_for_overreach(
    action_result: str,
    scene_progression: str,
    gm_prompt: str,
    context: NarrationConstraintContext | None = None,
) -> ValidationResult:
    """Validate narrative text for AI overreach on numeric authority.
    
    This is the main post-processing validation function that checks if the AI
    has attempted to declare numerical values without authorization from the
    rule engine.
    
    Args:
        action_result: The action_result field from narration
        scene_progression: The scene_progression field from narration
        gm_prompt: The gm_prompt field from narration
        context: Optional constraint context for additional validation
        
    Returns:
        ValidationResult with is_valid flag, violations list, and marked narrative
    """
    all_violations: list[str] = []
    combined_text = f"{action_result} {scene_progression} {gm_prompt}"
    
    # Check for unauthorized numeric declarations
    numeric_violations = detect_unauthorized_numeric_declarations(combined_text)
    for v in numeric_violations:
        all_violations.append(f"{v['type']}: '{v['matched_text']}' at position {v['position']}")
    
    # Also run the contradiction checks if context is provided
    if context:
        contradictions = find_contradictions(action_result, scene_progression, context)
        all_violations.extend(contradictions)
    
    is_valid = len(all_violations) == 0
    
    # Log warnings for any violations
    if not is_valid:
        logger.warning(
            "Narrative validation detected %d violations: %s",
            len(all_violations),
            "; ".join(all_violations),
            extra={
                "violations": all_violations,
                "action_result_preview": action_result[:100] if action_result else "",
            },
        )
    
    # Create marked narrative if there are violations
    marked_narrative = None
    if not is_valid:
        violation_marker = "\n\n[VALIDATION WARNING - 校验警告]\n"
        violation_marker += "以下叙事内容违反数值约束规则，已被标记：\n"
        for i, v in enumerate(all_violations, 1):
            violation_marker += f"{i}. {v}\n"
        marked_narrative = combined_text + violation_marker
    
    return ValidationResult(
        is_valid=is_valid,
        violations=all_violations,
        marked_narrative=marked_narrative,
    )
