"""Narrative generation for game actions.

Provides immersive, GM-style narrative text for game actions.
Falls back to template narratives when API is unavailable.

Hard Constraint Principle:
- Rule engine results (success/failure, damage values, state changes) are INVIOLABLE facts
- AI narrative MUST respect these facts and cannot contradict them
- The prompt explicitly separates "ESTABLISHED FACTS" from "NARRATIVE SPACE"
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from pydantic import BaseModel

from ..models.action import (
    ActionRequest,
    Effect,
    Outcome,
)
from ..models.state import Actor, NarrativeHistoryEntry, NPC, Scene
from ..config import get_llm_config
from ..llm_client import OpenAICompatibleClient
from .resolution_constraints import (
    NarrationConstraintContext,
    ValidationResult,
    build_hard_constraints,
    build_narrative_prompt,
    detect_unauthorized_numeric_declarations,
    find_contradictions,
    validate_narrative_for_overreach,
)

# Backward-compatible export for existing scripts/tests.
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT = """你是一位经验丰富的奇幻桌游主持人（GM）。
你的任务是用**中文**为玩家的行动撰写沉浸式叙事描述，并主动推进场景发展。
所有输出必须使用中文，包括 action_result、scene_progression 和 gm_prompt 三个字段。

CRITICAL RULE - HARD CONSTRAINTS (绝对不可违反):
The "【硬约束区 / HARD CONSTRAINTS】" section in the prompt contains ESTABLISHED FACTS determined by the rule engine.
These are ABSOLUTE and CANNOT be changed, ignored, or contradicted in your narrative:
- If outcome is "失败" (failure), you CANNOT describe it as success or hitting
- If damage is "8", you MUST describe damage consistent with 8 HP loss
- If target HP changes to "5", you CANNOT say the target was defeated
- State changes (conditions, HP, resources) are FACTS, not suggestions

ABSOLUTE PROHIBITION - 数值权威禁止 (NUMERIC AUTHORITY RESTRICTION):
You are STRICTLY FORBIDDEN from announcing or modifying any numeric values in your narrative:
- NEVER say "HP becomes", "HP 变为", "生命值变为" or any HP modification
- NEVER say "You gain", "你获得", "你得到" followed by any numeric resource
- NEVER say "You lose", "你失去", "你损失" followed by any numeric resource
- NEVER announce specific damage numbers like "deals 5 damage" or "造成 5 点伤害"
- NEVER announce healing amounts like "restores 3 HP" or "恢复 3 点生命"
- NEVER state new HP totals like "now has 5 HP" or "现在剩下 5 点生命"

The rule engine ALONE has authority over all numeric values. Your job is ONLY to describe:
- Sensory details (what characters see, hear, feel)
- Emotional reactions and dramatic tension
- Environmental changes and atmospheric effects
- Strategic implications and narrative consequences

VIOLATION CONSEQUENCE: Any output containing unauthorized numeric declarations will be rejected.

叙事规则：
- 使用第二人称（"你"）或第三人称有限视角
- 语言生动、有氛围感，符合奇幻冒险风格
- 输出分为三个部分：
  1. action_result：描述行动、结果及直接后果
  2. scene_progression：描述行动后场景的即时反应或环境变化
  3. gm_prompt：主动向玩家抛出下一个节拍——具体的提示、压力或事件
- 每部分保持在1个简短段落内
- 结合近期会话历史，让场景持续演进而非重置
- 聚焦感官细节：角色看到、听到、感受到什么
- 战斗场景：描述紧张感、兵器碰撞、打击感
- 技能检定：描述努力、挣扎、结果
- 绝对不能违反硬约束——它们是事实
- 不要使用系统术语如"投骰"、"DC"、"修正值"、"检定"（直接描述结果）
- 不要出戏或提及游戏机制
- 只返回合法 JSON，包含 "action_result"、"scene_progression"、"gm_prompt" 三个键

语气：戏剧性但不夸张，扎实的奇幻冒险风格。"""


class NarrationBundle(BaseModel):
    """Structured narration result for action and proactive scene advancement."""

    action_result: str
    scene_progression: str
    gm_prompt: str


def _build_hard_constraints(
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
    combat_round: Optional[int] = None,
    is_combat_ended: Optional[bool] = None,
    combat_outcome: Optional[str] = None,
    npc_target: Optional[NPC] = None,
) -> list[str]:
    """Backward-compatible wrapper around centralized constraint mapping."""
    return build_hard_constraints(
        NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
            combat_round=combat_round,
            is_combat_ended=is_combat_ended,
            combat_outcome=combat_outcome,
            npc_target=npc_target,
        )
    )


def _build_narrative_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
    combat_round: Optional[int] = None,
    is_combat_ended: Optional[bool] = None,
    combat_outcome: Optional[str] = None,
    npc_target: Optional[NPC] = None,
) -> str:
    """Backward-compatible wrapper around centralized prompt building."""
    return build_narrative_prompt(
        req=req,
        actor=actor,
        scene=scene,
        context=NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
            combat_round=combat_round,
            is_combat_ended=is_combat_ended,
            combat_outcome=combat_outcome,
            npc_target=npc_target,
        ),
        narrative_history=narrative_history,
    )


# ---------------------------------------------------------------------------
# Fallback Templates (when API is unavailable)
# ---------------------------------------------------------------------------

def _fallback_action_result(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    is_combat_ended: Optional[bool] = None,
    combat_round: Optional[int] = None,
    npc_target: Optional[NPC] = None,
) -> str:
    """Generate a template fallback narrative when API is unavailable."""
    
    if attack_result:
        # Combat fallback
        weapon = attack_result.get("weapon", "weapon")
        target = attack_result.get("target", "enemy")
        hit = attack_result.get("hit", outcome == Outcome.SUCCESS)
        damage = attack_result.get("damage")
        
        # Check for combat ended (target defeated)
        if is_combat_ended:
            return (
                f"{actor.name} hits the {target} with a decisive strike from the {weapon}, "
                f"and the {target} collapses to the ground, defeated. "
                f"The combat concludes as the battlefield falls silent."
            )
        
        if hit:
            # Hit - include "hits" for test compatibility
            if damage:
                return (
                    f"{actor.name} lunges forward with {weapon} in hand and hits the {target}. "
                    f"The blow lands cleanly, and the impact echoes through the scene."
                )
            else:
                return (
                    f"{actor.name} swings the {weapon} in a wide arc and hits the {target}, "
                    f"catching them off-guard for a brief instant."
                )
        else:
            # Miss - include "miss" for test compatibility
            return (
                f"{actor.name} attacks {target} with the {weapon}, "
                f"but misses as the {target} dances aside at the last moment."
            )
    
    # NPC interaction fallback
    if npc_target:
        return (
            f"{actor.name} approaches {npc_target.name} and tries to {req.intent}. "
            f"The interaction proceeds as expected, with {npc_target.name} responding in kind."
        )

    # General action fallback
    if outcome == Outcome.SUCCESS:
        return (
            f"{actor.name} sets out to {req.intent}. Through skill and determination, "
            f"the attempt succeeds, bringing the desired result."
        )
    else:
        return (
            f"{actor.name} attempts to {req.intent}, but fortune does not favor them this time. "
            f"The effort falls short of success."
        )


def _fallback_scene_progression(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    is_combat_ended: Optional[bool] = None,
    npc_target: Optional[NPC] = None,
) -> str:
    """Return a deterministic scene progression when AI is unavailable."""
    if attack_result:
        target = attack_result.get("target", "enemy")
        if outcome == Outcome.SUCCESS:
            return (
                f"The {target} recoils and the air in {scene.name} tightens around the clash. "
                f"You can press the advantage now or scan the room for whoever reacts next."
            )
        return (
            f"The {target} regains footing as the fight resets for a heartbeat, and nearby movement grows tense. "
            f"You can reposition, watch for a counterattack, or call out to control the next exchange."
        )

    if npc_target:
        return (
            f"The conversation with {npc_target.name} settles into the atmosphere of {scene.name}. "
            f"Others nearby continue their business, though some may be listening."
        )

    if outcome == Outcome.SUCCESS:
        return (
            f"A ripple of response moves through {scene.name} as the moment settles into its new shape. "
            f"You can follow the opening immediately, watch how others react, or probe the environment for what changed."
        )

    return (
        f"The setback leaves a brief opening for the world to answer back; sounds, glances, and pressure shift around {actor.name}. "
        f"You can reassess the room, respond to any NPC reaction, or try a new angle before the moment closes."
    )


def _build_history_callback(narrative_history: Optional[list[NarrativeHistoryEntry]]) -> str:
    if not narrative_history:
        return ""

    latest = narrative_history[-1]
    seed = latest.narration_summary or latest.action_summary
    compact = seed.replace("\n", " ").strip()
    if len(compact) > 120:
        compact = compact[:117].rstrip() + "..."

    if len(narrative_history) >= 3:
        return f" The scene is already carrying momentum from several exchanges, especially {compact}"
    return f" The room is still reacting to the last beat: {compact}"


def _fallback_gm_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
    is_combat_ended: Optional[bool] = None,
    npc_target: Optional[NPC] = None,
) -> str:
    history_callback = _build_history_callback(narrative_history)
    time_pressure = (
        f" Time in {scene.name} has advanced to beat {scene.time}."
        if scene.time
        else ""
    )

    if attack_result:
        target = attack_result.get("target", "enemy")
        if outcome == Outcome.SUCCESS:
            return (
                f"{target} staggers but does not leave the scene; something in the melee is about to answer your advantage."
                f"{history_callback}{time_pressure} Do you press the wounded foe, break away to reposition, or react to whoever else moves?"
            )
        return (
            f"{target} has seen your line now and the fight threatens to turn back on you."
            f"{history_callback}{time_pressure} What do you do before the counterpressure lands?"
        )

    if npc_target:
        return (
            f"{npc_target.name} seems to be waiting for your next words or action."
            f"{history_callback}{time_pressure} Do you continue the conversation, change the subject, or move on?"
        )

    if outcome == Outcome.SUCCESS:
        return (
            f"A fresh opening has appeared in {scene.name}, but it will not stay open for long."
            f"{history_callback}{time_pressure} Do you exploit that opening immediately, question whoever reacts, or examine what just shifted?"
        )

    return (
        f"The failed attempt gives the scene permission to push back."
        f"{history_callback}{time_pressure} What catches your attention first: an NPC response, a change in the environment, or a new tactic?"
    )


def _fallback_narration_bundle(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
    combat_round: Optional[int] = None,
    is_combat_ended: Optional[bool] = None,
    combat_outcome: Optional[str] = None,
    npc_target: Optional[NPC] = None,
) -> NarrationBundle:
    return NarrationBundle(
        action_result=_fallback_action_result(req, actor, scene, outcome, attack_result, is_combat_ended, combat_round, npc_target),
        scene_progression=_fallback_scene_progression(req, actor, scene, outcome, attack_result, is_combat_ended, npc_target),
        gm_prompt=_fallback_gm_prompt(req, actor, scene, outcome, attack_result, narrative_history, is_combat_ended, npc_target),
    )


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

def _parse_narration_bundle(content: str) -> Optional[NarrationBundle]:
    """Parse the model response into the required narration bundle."""
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    action_result = str(data.get("action_result", "")).strip()
    scene_progression = str(data.get("scene_progression", "")).strip()
    gm_prompt = str(data.get("gm_prompt", "")).strip()
    if not action_result or not scene_progression or not gm_prompt:
        return None

    return NarrationBundle(
        action_result=action_result,
        scene_progression=scene_progression,
        gm_prompt=gm_prompt,
    )


def _narration_respects_constraints(
    narration: NarrationBundle,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
    check_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
) -> bool:
    """Backward-compatible boolean helper for contradiction validation."""
    reasons = find_contradictions(
        action_result=narration.action_result,
        scene_progression=narration.scene_progression,
        context=NarrationConstraintContext(
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=effects,
            actor=actor,
            target=target,
        ),
    )
    return not reasons


async def _call_kimi_api(prompt: str) -> Optional[NarrationBundle]:
    config = get_llm_config("kimi")
    if config is None:
        return None
    client = OpenAICompatibleClient(config)
    generated = await client.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
    return _parse_narration_bundle(generated) if generated else None


async def _call_openai_api(prompt: str) -> Optional[NarrationBundle]:
    config = get_llm_config("openai")
    if config is None:
        return None
    client = OpenAICompatibleClient(config)
    generated = await client.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
    return _parse_narration_bundle(generated) if generated else None


def generate_narration(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
    combat_round: Optional[int] = None,
    is_combat_ended: Optional[bool] = None,
    combat_outcome: Optional[str] = None,
    npc_target: Optional[NPC] = None,
) -> NarrationBundle:
    """Generate structured narrative text for an action resolution.
    
    This is a synchronous wrapper around the async API call.
    Falls back to template narrative if API is unavailable.
    
    Hard constraints (outcome, damage, state changes) are injected into the prompt
    to ensure AI narrative respects rule engine results.
    
    Args:
        req: The action request
        actor: The acting character
        scene: The current scene
        outcome: Success or failure
        check_result: Optional check details
        attack_result: Optional attack details
        effects: Optional list of state change effects
        target: Optional target actor (for combat context)
        combat_round: Optional combat round number
        is_combat_ended: Whether combat has ended
        combat_outcome: Combat outcome if ended ('victory', 'defeat')
        
    Returns:
        Narration bundle for action result and scene progression
    """
    context = NarrationConstraintContext(
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        actor=actor,
        target=target,
        combat_round=combat_round,
        is_combat_ended=is_combat_ended,
        combat_outcome=combat_outcome,
        npc_target=npc_target,
    )
    prompt = _build_narrative_prompt(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        target=target,
        narrative_history=narrative_history,
        combat_round=combat_round,
        is_combat_ended=is_combat_ended,
        combat_outcome=combat_outcome,
        npc_target=npc_target,
    )

    # Log combat narrative prompts for observability
    if attack_result:
        logger.info(
            "Combat narrative prompt generated for %s vs %s (round=%s, hit=%s, damage=%s)",
            actor.name,
            attack_result.get("target", "unknown"),
            combat_round,
            attack_result.get("hit"),
            attack_result.get("damage", {}).get("total") if isinstance(attack_result.get("damage"), dict) else None,
            extra={
                "actor_hp": actor.hp,
                "target_hp": target.hp if target else None,
                "combat_round": combat_round,
                "is_combat_ended": is_combat_ended,
                "prompt_preview": prompt[:800],
            },
        )

    def _run_provider(current_prompt: str) -> Optional[NarrationBundle]:
        try:
            import asyncio

            if req.provider == "openai":
                return asyncio.run(_call_openai_api(current_prompt))
            if req.provider == "kimi" or KIMI_API_KEY:
                return asyncio.run(_call_kimi_api(current_prompt))
            return None
        except Exception:
            return None

    narrative = _run_provider(prompt)
    if narrative:
        # Use comprehensive validation including numeric authority checks
        validation = validate_narrative_for_overreach(
            action_result=narrative.action_result,
            scene_progression=narrative.scene_progression,
            gm_prompt=narrative.gm_prompt,
            context=context,
        )
        
        if validation.is_valid:
            return narrative

        logger.warning(
            "Narration failed validation with %d violations; retrying once",
            len(validation.violations),
            extra={
                "outcome": outcome.value,
                "action_intent": req.intent,
                "violations": validation.violations,
            },
        )
        retry_prompt = (
            f"{prompt}\n\n"
            "【修正要求 / CORRECTION REQUIRED】\n"
            "你上一版叙事违反以下约束规则。请严格修正，不得重复以下问题：\n"
            f"{json.dumps(validation.violations, ensure_ascii=False)}\n\n"
            "特别提醒：你作为叙事AI，绝对不得自行宣布或修改任何数值（如HP、伤害值等）。"
            "数值相关描述只能通过感官细节体现，不得直接陈述数值变化。"
        )
        retry_narrative = _run_provider(retry_prompt)
        if retry_narrative:
            retry_validation = validate_narrative_for_overreach(
                action_result=retry_narrative.action_result,
                scene_progression=retry_narrative.scene_progression,
                gm_prompt=retry_narrative.gm_prompt,
                context=context,
            )
            if retry_validation.is_valid:
                return retry_narrative

            logger.warning(
                "Narration retry still failed validation; using fallback",
                extra={
                    "outcome": outcome.value,
                    "action_intent": req.intent,
                    "violations": retry_validation.violations,
                },
            )

    return _fallback_narration_bundle(
        req,
        actor,
        scene,
        outcome,
        attack_result,
        narrative_history,
        combat_round=combat_round,
        is_combat_ended=is_combat_ended,
        combat_outcome=combat_outcome,
        npc_target=npc_target,
    )
