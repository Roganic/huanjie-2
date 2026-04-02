"""Mapping and validation helpers for narration hard constraints.

This module implements the AI Narrative Constraint System that ensures:
1. Numeric Authority: AI cannot declare or modify numeric values (HP, damage, etc.)
2. Plot Control: AI cannot force story progression beyond rule-engine results
3. Combat Integrity: AI cannot contradict combat outcomes (hit/miss, defeat, etc.)

Constraint violations are logged and trigger fallback to safe narrative templates.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from ..models.action import ActionRequest, Effect, Outcome
from ..models.state import Actor, NarrativeHistoryEntry, Scene

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

# Patterns for detecting unauthorized plot advancement / story forcing
# These patterns indicate AI trying to bypass rule engine by auto-resolving events
UNAUTHORIZED_PLOT_ADVANCE_PATTERNS = [
    # Chinese plot forcing patterns - auto-resolution without checks
    re.compile(r"(?:你|你们)\s*(?:成功|顺利|轻松)\s*(?:地)?\s*(?:通过|穿过|越过|解开|解决|击败|说服)"),
    re.compile(r"(?:敌人|怪物|对手)\s*(?:被击败|被消灭|被杀死|投降|逃跑|撤退)"),
    re.compile(r"(?:谜题|陷阱|门|锁)\s*(?:自动|自己|轻易)\s*(?:解开|打开|破解|解除)"),
    re.compile(r"(?:场景|剧情|故事)\s*(?:直接|立刻|马上)\s*(?:进入|跳转到|转换到)"),
    re.compile(r"(?:无需|不用)\s*(?:检定|判定|投骰|检查)"),
    # English plot forcing patterns
    re.compile(r"(?:you|the\s+party)\s+(?:automatically|easily|successfully)\s+(?:defeat|kill|persuade|unlock|solve)", re.IGNORECASE),
    re.compile(r"(?:the\s+enemy|monster|boss)\s+(?:is\s+defeated|dies|surrenders|flees|retreats)", re.IGNORECASE),
    re.compile(r"(?:puzzle|trap|door|lock)\s+(?:unlocks|opens|disarms|solves)\s+(?:automatically|itself|easily)", re.IGNORECASE),
    re.compile(r"(?:scene|story|plot)\s+(?:jumps|skips|advances|moves)\s+(?:directly|immediately|to)", re.IGNORECASE),
    re.compile(r"(?:no\s+(?:check|roll)|without\s+(?:checking|rolling)|skip\s+the\s+check)", re.IGNORECASE),
]

# Patterns for detecting unauthorized state changes not from rule engine
UNAUTHORIZED_STATE_CHANGE_PATTERNS = [
    # Chinese unauthorized state changes
    re.compile(r"(?:获得|得到|失去)\s*(?:状态|condition|buff|debuff)", re.IGNORECASE),
    re.compile(r"(?:状态|condition)\s*(?:变为|改成|设置为)", re.IGNORECASE),
    # English unauthorized state changes
    re.compile(r"(?:gain|lose|receive)\s+(?:the\s+)?(?:\w+)\s+(?:condition|status|state)", re.IGNORECASE),
    re.compile(r"(?:condition|status|state)\s+(?:becomes?|changes?\s+to|is\s+set\s+to)", re.IGNORECASE),
]

ALL_UNAUTHORIZED_PATTERNS = (
    UNAUTHORIZED_HP_PATTERNS
    + UNAUTHORIZED_RESOURCE_GAIN_PATTERNS
    + UNAUTHORIZED_RESOURCE_LOSS_PATTERNS
    + UNAUTHORIZED_DAMAGE_ANNOUNCEMENT_PATTERNS
    + UNAUTHORIZED_HEALING_ANNOUNCEMENT_PATTERNS
    + UNAUTHORIZED_AC_PATTERNS
    + UNAUTHORIZED_PLOT_ADVANCE_PATTERNS
    + UNAUTHORIZED_STATE_CHANGE_PATTERNS
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
    
    # Check numeric-related unauthorized patterns
    numeric_patterns = (
        UNAUTHORIZED_HP_PATTERNS
        + UNAUTHORIZED_RESOURCE_GAIN_PATTERNS
        + UNAUTHORIZED_RESOURCE_LOSS_PATTERNS
        + UNAUTHORIZED_DAMAGE_ANNOUNCEMENT_PATTERNS
        + UNAUTHORIZED_HEALING_ANNOUNCEMENT_PATTERNS
        + UNAUTHORIZED_AC_PATTERNS
    )
    
    for pattern in numeric_patterns:
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


def detect_unauthorized_plot_advancement(text: str) -> list[dict]:
    """Detect unauthorized plot advancement / story forcing in narrative text.
    
    This function scans for patterns where the AI attempts to bypass the rule
    engine by auto-resolving challenges, skipping required checks, or forcing
    story progression without proper resolution.
    
    Args:
        text: The narrative text to scan
        
    Returns:
        List of violation dictionaries with pattern type and matched text
    """
    violations: list[dict] = []
    text_lower = text.lower()
    
    # Check plot advancement patterns
    for pattern in UNAUTHORIZED_PLOT_ADVANCE_PATTERNS:
        for match in pattern.finditer(text):
            violations.append({
                "type": "unauthorized_plot_advancement",
                "pattern": pattern.pattern[:50] + "..." if len(pattern.pattern) > 50 else pattern.pattern,
                "matched_text": match.group(0),
                "position": match.start(),
            })
    
    # Additional contextual checks for story forcing
    plot_forcing_indicators = [
        # Chinese indicators
        ("任务完成", "quest_auto_complete"),
        ("自动成功", "auto_success_claim"),
        ("直接胜利", "direct_victory_claim"),
        ("剧情跳过", "story_skip"),
        ("直接进入", "direct_entry_without_resolution"),
        ("无需战斗", "combat_avoidance_without_rules"),
        # English indicators
        ("quest completes", "quest_auto_complete"),
        ("mission accomplished", "mission_auto_complete"),
        ("instant success", "auto_success_claim"),
        ("automatic victory", "direct_victory_claim"),
        ("skip to", "story_skip"),
        ("bypass the", "mechanic_bypass"),
    ]
    
    for indicator, violation_type in plot_forcing_indicators:
        if indicator in text_lower:
            idx = text_lower.find(indicator)
            violations.append({
                "type": violation_type,
                "pattern": indicator,
                "matched_text": text[idx:idx + len(indicator)],
                "position": idx,
            })
    
    return violations


def detect_unauthorized_state_changes(text: str) -> list[dict]:
    """Detect unauthorized state changes declared in narrative text.
    
    This function scans for patterns where the AI attempts to declare state
    changes (conditions, buffs, debuffs) that should only come from the rule engine.
    
    Args:
        text: The narrative text to scan
        
    Returns:
        List of violation dictionaries with pattern type and matched text
    """
    violations: list[dict] = []
    
    for pattern in UNAUTHORIZED_STATE_CHANGE_PATTERNS:
        for match in pattern.finditer(text):
            violations.append({
                "type": "unauthorized_state_change",
                "pattern": pattern.pattern[:50] + "..." if len(pattern.pattern) > 50 else pattern.pattern,
                "matched_text": match.group(0),
                "position": match.start(),
            })
    
    return violations


def validate_narrative_for_overreach(
    action_result: str,
    scene_progression: str,
    gm_prompt: str,
    context: NarrationConstraintContext | None = None,
) -> ValidationResult:
    """Validate narrative text for AI overreach across all constraint categories.
    
    This is the main post-processing validation function that implements
    the three-tier constraint system:
    1. Numeric Authority: AI cannot declare/modify numeric values (HP, damage, etc.)
    2. Plot Control: AI cannot force story progression beyond rule engine results
    3. Combat Integrity: AI cannot contradict combat outcomes (hit/miss, defeat, etc.)
    
    When violations are detected, they are logged and the narrative is marked
    for fallback to safe templates.
    
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
    
    # Category 1: Numeric Authority Violations
    numeric_violations = detect_unauthorized_numeric_declarations(combined_text)
    for v in numeric_violations:
        all_violations.append(f"numeric_overreach[{v['type']}]: '{v['matched_text']}'")
    
    # Category 2: Plot Advancement / Story Forcing Violations
    plot_violations = detect_unauthorized_plot_advancement(combined_text)
    for v in plot_violations:
        all_violations.append(f"plot_forcing[{v['type']}]: '{v['matched_text']}'")
    
    # Category 3: Unauthorized State Changes
    state_violations = detect_unauthorized_state_changes(combined_text)
    for v in state_violations:
        all_violations.append(f"state_overreach[{v['type']}]: '{v['matched_text']}'")
    
    # Category 4: Combat Result / Outcome Contradictions
    if context:
        contradictions = find_contradictions(action_result, scene_progression, context)
        all_violations.extend(contradictions)
    
    is_valid = len(all_violations) == 0
    
    # Log warnings for any violations
    if not is_valid:
        logger.warning(
            "Narrative constraint validation detected %d violations: %s",
            len(all_violations),
            "; ".join(all_violations),
            extra={
                "violations": all_violations,
                "action_result_preview": action_result[:100] if action_result else "",
                "scene_progression_preview": scene_progression[:100] if scene_progression else "",
            },
        )
    
    # Create marked narrative if there are violations
    marked_narrative = None
    if not is_valid:
        violation_marker = "\n\n[VALIDATION WARNING - 校验警告]\n"
        violation_marker += "以下叙事内容违反约束规则，已被标记：\n"
        violation_marker += "违规类型说明：\n"
        violation_marker += "- numeric_overreach: 数值越权（AI试图声明HP/伤害等数值）\n"
        violation_marker += "- plot_forcing: 剧情强推（AI试图绕过规则引擎推进剧情）\n"
        violation_marker += "- state_overreach: 状态越权（AI试图声明状态变化）\n"
        violation_marker += "- contradiction: 结果矛盾（叙事与裁定结果矛盾）\n\n"
        for i, v in enumerate(all_violations, 1):
            violation_marker += f"{i}. {v}\n"
        marked_narrative = combined_text + violation_marker
    
    return ValidationResult(
        is_valid=is_valid,
        violations=all_violations,
        marked_narrative=marked_narrative,
    )
