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
from ..models.state import Actor, NarrativeHistoryEntry, NPC, Scene
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

# Skill check failure - success semantics that should not appear when check fails
SKILL_FAILURE_SUCCESS_INDICATORS = (
    "成功",
    "做到了",
    "顺利完成",
    "完美达成",
    "出色完成",
    "顺利做到",
    "成功完成",
    "达成目标",
    "如愿以偿",
    "得心应手",
    "顺利完成",
    "顺利完成",
    "succeeded",
    "successfully",
    "managed to",
    "accomplished",
    "achieved",
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
    " killing",
    " kill ",
    " dead",
    " collapses lifeless",
    " dies",
    " dying",
    " lifeless",
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
    re.compile(r"(?:获得|得到|失去)\s*(?:了)?\s*(?:\w+)?\s*(?:状态|condition|buff|debuff)"),
    re.compile(r"(?:状态|condition)\s*(?:变为|改成|设置为)"),
    re.compile(r"(?:获得|得到)\s*(?:了)?\s*(?:中毒|恐惧|麻痹|眩晕|昏迷| restrained|prone|poisoned|frightened)"),
    # English unauthorized state changes
    re.compile(r"(?:gain|lose|receive)\s+(?:the\s+)?\w+\s+(?:condition|status|state)", re.IGNORECASE),
    re.compile(r"(?:condition|status|state)\s+(?:becomes?|changes?\s+to|is\s+set\s+to)", re.IGNORECASE),
    re.compile(r"(?:gain|receive|afflicted\s+by)\s+(?:the\s+)?(?:poisoned|frightened|paralyzed|stunned|restrained|prone)", re.IGNORECASE),
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
    # Combat-specific context
    combat_round: Optional[int] = None
    is_combat_ended: Optional[bool] = None
    combat_outcome: Optional[str] = None
    # NPC interaction context
    npc_target: Optional[NPC] = None


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
        
        # Detect natural 20 (critical success) and natural 1 (critical failure)
        roll_int = roll if isinstance(roll, int) else 0
        if roll_int == 20:
            lines.append(
                f"- 检定详情 / Check: {ability.upper()}, 掷骰={roll}【大成功!/CRITICAL SUCCESS】, 调整值={modifier}, 总计={total}, DC={dc}"
            )
        elif roll_int == 1:
            lines.append(
                f"- 检定详情 / Check: {ability.upper()}, 掷骰={roll}【大失败!/CRITICAL FAILURE】, 调整值={modifier}, 总计={total}, DC={dc}"
            )
        else:
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
    # Log scene context and NPCs being used in prompt
    npc_names = [npc.name for npc in scene.npcs] if scene.npcs else []
    logger.info(
        "Building narrative prompt with scene context",
        extra={
            "scene_name": scene.name,
            "scene_id": scene.id,
            "npcs": npc_names,
            "npc_count": len(npc_names),
            "history_entries": len(narrative_history) if narrative_history else 0,
        },
    )
    
    # Log recent action summaries
    if narrative_history:
        recent_summaries = [
            entry.action_summary 
            for entry in narrative_history[-5:]
            if entry.action_summary
        ]
        logger.info(
            "Recent action summaries in prompt: %d entries",
            len(recent_summaries),
            extra={
                "recent_action_summaries": recent_summaries,
                "total_history": len(narrative_history),
            },
        )
    
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
    if scene.flags:
        lines.append(f"场景状态 / Scene Flags: {', '.join(scene.flags)}")
    # Add NPC information to the prompt
    if scene.npcs:
        lines.append("")
        lines.append("场景中的NPC / NPCs in Scene:")
        for npc in scene.npcs:
            type_label = {
                "friendly": "友好",
                "neutral": "中立", 
                "hostile": "敌对",
            }.get(npc.type.value, npc.type.value)
            lines.append(f"  - {npc.name} [{type_label}]: {npc.description}")
        
        # Add NPC dialogue context for relevant NPCs
        # Check if the action intent involves talking to a specific NPC
        dialogue_context = _build_npc_dialogue_context(req, scene)
        if dialogue_context:
            lines.append("")
            lines.append(dialogue_context)
    lines.append("")
    lines.append(f"角色 / Character: {actor.name}")
    lines.append(f"角色描述 / Character Description: {actor.description}")
    character_class_str = actor.character_class.value if actor.character_class else "adventurer"
    lines.append(f"角色职业 / Character Class: {character_class_str}")
    lines.append(f"角色等级 / Level: 1 (熟练加值 / Proficiency: +{actor.proficiency_bonus})")
    lines.append(
        f"角色属性 / Abilities: "
        f"STR {actor.abilities.str_}({actor.abilities.modifier('str'):+d}), "
        f"DEX {actor.abilities.dex}({actor.abilities.modifier('dex'):+d}), "
        f"CON {actor.abilities.con}({actor.abilities.modifier('con'):+d}), "
        f"INT {actor.abilities.int_}({actor.abilities.modifier('int'):+d}), "
        f"WIS {actor.abilities.wis}({actor.abilities.modifier('wis'):+d}), "
        f"CHA {actor.abilities.cha}({actor.abilities.modifier('cha'):+d})"
    )
    lines.append(f"角色状态 / Character Status: HP {actor.hp}/{actor.hp_max}, AC {actor.ac}")
    if actor.skills:
        proficient_skills = [s.name for s in actor.skills if s.proficient]
        if proficient_skills:
            lines.append(f"熟练技能 / Proficient Skills: {', '.join(proficient_skills)}")
    lines.append("")

    if context.npc_target:
        lines.append(f"互动目标NPC / NPC Target: {context.npc_target.name}")
        if context.npc_target.role:
            lines.append(f"NPC角色类型 / NPC Role: {context.npc_target.role}")
        if context.npc_target.description:
            lines.append(f"NPC描述 / NPC Description: {context.npc_target.description}")
        lines.append("")

    if context.target:
        lines.append(f"战斗目标 / Combat Target: {context.target.name}")
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

        if any(indicator in combined for indicator in SKILL_FAILURE_SUCCESS_INDICATORS):
            reasons.append("skill_failure_narrated_as_success")

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


# Scene context validation patterns
SCENE_CONTRADICTION_PATTERNS = [
    # Pattern to detect mention of wrong location
    re.compile(r"(不在|离开|远离)\s*\w+\s*(场景|地点|地方)"),
]


def validate_scene_context(
    narrative_text: str,
    scene_name: str,
    npcs: list,
    connected_scenes: Optional[list[str]] = None,
) -> list[dict]:
    """Validate that narrative content is consistent with scene context.
    
    This function checks if the narrative contradicts the current scene
    setting (wrong location, NPCs that don't exist, etc.).
    
    Args:
        narrative_text: The narrative text to validate
        scene_name: The current scene name
        npcs: List of NPCs present in the scene
        connected_scenes: Optional list of connected scene names
        
    Returns:
        List of violation dictionaries with type and description
    """
    violations: list[dict] = []
    text = narrative_text.lower()
    
    # Get list of NPC names in the scene
    npc_names = [npc.name.lower() for npc in npcs] if npcs else []
    
    # Check for mentions of NPCs not present in the scene
    # This is a simplified check - we look for references to named characters
    # that aren't in the scene's NPC list
    import re as re_module
    # Pattern to find character names (simplified heuristic)
    name_pattern = re_module.compile(r'[\u4e00-\u9fff]{2,4}|[A-Z][a-z]+')
    found_names = name_pattern.findall(narrative_text)
    
    for name in found_names:
        name_lower = name.lower()
        # Skip common words that might match
        if name_lower in ("you", "your", "the", "a", "an", "gm", "pc", "npc"):
            continue
        # If this looks like a character name but isn't in scene NPCs, flag it
        # Only flag if it's a clear reference (appears multiple times or with titles)
        if name_lower not in npc_names and len(name) >= 2:
            # Check for titles that suggest it's an NPC reference
            titles = ["先生", "女士", "老", "小", "大人", "阁下", "队长", "首领", "村长"]
            has_title = any(title in narrative_text[narrative_text.find(name):narrative_text.find(name)+len(name)+4] 
                          for title in titles)
            if has_title:
                violations.append({
                    "type": "npc_not_in_scene",
                    "description": f"Narrative references '{name}' who is not present in current scene",
                    "scene_name": scene_name,
                    "present_npcs": npc_names,
                    "referenced_name": name,
                })
    
    return violations


def find_scene_contradictions(
    action_result: str,
    scene_progression: str,
    gm_prompt: str,
    scene_name: str,
    scene_description: str,
    npcs: list,
) -> list[str]:
    """Check if narrative contradicts scene context.
    
    Args:
        action_result: The action result narrative
        scene_progression: The scene progression narrative
        gm_prompt: The GM prompt
        scene_name: Current scene name
        scene_description: Current scene description
        npcs: NPCs present in the scene
        
    Returns:
        List of contradiction reason strings
    """
    combined = f" {action_result.lower()} {scene_progression.lower()} {gm_prompt.lower()} "
    reasons: list[str] = []
    
    npc_names = [npc.name for npc in npcs] if npcs else []
    
    # Check if narrative mentions NPCs not in scene
    # This is a basic check - looking for NPC names that might be from other scenes
    other_scene_npcs = {
        # Tavern NPCs
        "老马库斯", "银弦艾拉", "戴兜帽的商人",
        "marcus", "ella", "merchant",
        # Dungeon entrance NPCs  
        "托尔金", "thorin",
        # Combat NPCs
        "哥布林斥候", "哥布林萨满", "座狼",
        "goblin scout", "goblin shaman", "dire wolf",
    }
    
    for npc_name in other_scene_npcs:
        if npc_name.lower() in combined and npc_name not in npc_names:
            # Check if this NPC is actually not supposed to be here
            reasons.append(f"references_npc_not_in_scene[{npc_name}]")
    
    # Check for scene name consistency - if narrative mentions a different scene
    known_scenes = {
        "锈迹斑斑的灯笼酒馆", "灯笼酒馆", "酒馆",
        "遗忘地下城入口", "地下城入口",
        "地下城通道",
    }
    
    for known_scene in known_scenes:
        if known_scene in combined and known_scene != scene_name:
            # Check if it's referring to a different scene as current location
            location_indicators = ["在", "位于", "来到", "身处", "站在"]
            for indicator in location_indicators:
                if f"{indicator}{known_scene}" in combined.replace(" ", ""):
                    reasons.append(f"wrong_scene_location[mentions '{known_scene}' as current]")
                    break
    
    return list(dict.fromkeys(reasons))


def _build_npc_dialogue_context(
    req: ActionRequest,
    scene: Scene,
) -> str:
    """Build NPC dialogue context for the narrative prompt.
    
    Detects if the action involves talking to an NPC and returns
    the appropriate dialogue context (first contact vs continued dialogue).
    
    Args:
        req: The action request
        scene: The current scene with NPCs
        
    Returns:
        Dialogue context string for prompt injection, or empty string
    """
    # Keywords that indicate talking/speaking to an NPC
    dialogue_keywords = [
        "talk", "speak", "say", "ask", "chat", "greet", "hello", "hi",
        "conversation", "dialogue", "tell", "inquire", "question",
        "说", "说话", "谈话", "交谈", "问", "询问", "打招呼", "问候",
        "聊", "聊聊", "告诉", "打听",
    ]
    
    # Check if action involves dialogue
    action_text = f"{req.intent} {req.approach}".lower()
    is_dialogue_action = any(kw in action_text for kw in dialogue_keywords)
    
    if not is_dialogue_action:
        return ""
    
    # Try to identify which NPC the player is talking to
    # Match NPC names from the scene
    target_npc = None
    for npc in scene.npcs:
        # Check for exact name match or partial match
        npc_name_lower = npc.name.lower()
        npc_id_lower = npc.id.lower()
        if (
            npc_name_lower in action_text
            or npc_id_lower in action_text
            or any(part in action_text for part in npc_name_lower.split())
        ):
            target_npc = npc
            break
    
    # If no specific NPC matched but there's only one friendly/neutral NPC, use that
    if target_npc is None:
        non_hostile = [n for n in scene.npcs if n.type.value in ("friendly", "neutral")]
        if len(non_hostile) == 1:
            target_npc = non_hostile[0]
    
    if target_npc is None:
        return ""
    
    # Import here to avoid circular imports
    from ..npc.dialogue_state import (
        build_dialogue_context_for_prompt,
        is_first_npc_contact,
    )
    
    # Check if this is first contact or continued dialogue
    if is_first_npc_contact(target_npc.id):
        return (
            f"【NPC 对话情境 / NPC DIALOGUE CONTEXT】\n"
            f"这是玩家第一次与 {target_npc.name} 对话。\n"
            f"NPC 还不认识玩家，应该以初次见面的态度回应。\n"
        )
    else:
        # Get dialogue history context
        return build_dialogue_context_for_prompt(target_npc.id, target_npc.name)


def validate_narrative_for_overreach(
    action_result: str,
    scene_progression: str,
    gm_prompt: str,
    context: NarrationConstraintContext | None = None,
    scene_name: Optional[str] = None,
    scene_description: Optional[str] = None,
    scene_npcs: Optional[list] = None,
) -> ValidationResult:
    """Validate narrative text for AI overreach across all constraint categories.
    
    This is the main post-processing validation function that implements
    the three-tier constraint system:
    1. Numeric Authority: AI cannot declare/modify numeric values (HP, damage, etc.)
    2. Plot Control: AI cannot force story progression beyond rule engine results
    3. Combat Integrity: AI cannot contradict combat outcomes (hit/miss, defeat, etc.)
    4. Scene Context: AI narrative should respect current scene setting and NPCs
    
    When violations are detected, they are logged and the narrative is marked
    for fallback to safe templates.
    
    Args:
        action_result: The action_result field from narration
        scene_progression: The scene_progression field from narration
        gm_prompt: The gm_prompt field from narration
        context: Optional constraint context for additional validation
        scene_name: Optional current scene name for scene context validation
        scene_description: Optional scene description for context validation
        scene_npcs: Optional list of NPCs in the scene
        
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
    
    # Category 5: Scene Context Contradictions
    if scene_name and scene_npcs is not None:
        scene_contradictions = find_scene_contradictions(
            action_result=action_result,
            scene_progression=scene_progression,
            gm_prompt=gm_prompt,
            scene_name=scene_name,
            scene_description=scene_description or "",
            npcs=scene_npcs,
        )
        all_violations.extend(scene_contradictions)
    
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
