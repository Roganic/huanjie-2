"""Narrative generation using Kimi API.

Provides immersive, GM-style narrative text for game actions.
Falls back to template narratives when API is unavailable.

Hard Constraint Principle:
- Rule engine results (success/failure, damage values, state changes) are INVIOLABLE facts
- AI narrative MUST respect these facts and cannot contradict them
- The prompt explicitly separates "ESTABLISHED FACTS" from "NARRATIVE SPACE"
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

import httpx
from pydantic import BaseModel

from ..models.action import (
    ActionRequest,
    Effect,
    Outcome,
)
from ..models.state import Actor, Scene

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_API_URL = os.getenv("KIMI_API_URL", "https://api.moonshot.cn/v1/chat/completions")
KIMI_MODEL = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
KIMI_TIMEOUT_SECONDS = float(os.getenv("KIMI_TIMEOUT_SECONDS", "5"))

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT = """You are a skilled Game Master (GM) for a fantasy tabletop RPG.
Your task is to write immersive narrative descriptions of player actions and proactively advance the scene.

CRITICAL RULE - HARD CONSTRAINTS (绝对不可违反):
The "【硬约束区 / HARD CONSTRAINTS】" section in the prompt contains ESTABLISHED FACTS determined by the rule engine.
These are ABSOLUTE and CANNOT be changed, ignored, or contradicted in your narrative:
- If outcome is "失败" (failure), you CANNOT describe it as success or hitting
- If damage is "8", you MUST describe damage consistent with 8 HP loss
- If target HP changes to "5", you CANNOT say the target was defeated
- State changes (conditions, HP, resources) are FACTS, not suggestions

Guidelines:
- Write in second person ("you") or third person limited perspective
- Use vivid, atmospheric language that fits the fantasy setting
- Split your output into two distinct parts:
  1. action_result: describe the action, its outcome, and the immediate consequences
  2. scene_progression: proactively advance the scene with at least one of:
     - NPC reaction
     - environmental change
     - a concrete prompt or opening the player can act on next
- Keep each part to 1 short paragraph
- Focus on sensory details: what the character sees, hears, feels
- For combat: describe the tension, the clash of weapons, the impact
- For skill checks: describe the effort, the struggle, the result
- NEVER contradict the hard constraints - they are the ground truth
- Never use system terminology like "roll", "DC", "modifier", "check"
- Never break character or mention game mechanics explicitly
- Return valid JSON only, with keys "action_result" and "scene_progression"

Tone: dramatic but not overwrought, grounded fantasy adventure."""


class NarrationBundle(BaseModel):
    """Structured narration result for action and proactive scene advancement."""

    action_result: str
    scene_progression: str


def _build_hard_constraints(
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
) -> list[str]:
    """Build the hard constraint section listing rule engine facts.
    
    These are inviolable facts that the AI narrative must respect.
    """
    lines: list[str] = []
    
    # Core outcome - this is always present
    outcome_cn = "成功" if outcome == Outcome.SUCCESS else "失败"
    lines.append(f"- 裁定结果 / Outcome: {outcome_cn} ({outcome.value})")
    
    # Check details with specific numbers
    if check_result:
        ability = check_result.get("ability", "")
        roll = check_result.get("roll", 0)
        total = check_result.get("total", 0)
        dc = check_result.get("dc", 0)
        modifier = check_result.get("modifier", 0)
        lines.append(f"- 检定详情 / Check: {ability.upper()}, 掷骰={roll}, 调整值={modifier}, 总计={total}, DC={dc}")
    
    # Attack details with specific numbers
    if attack_result:
        weapon = attack_result.get("weapon", "weapon")
        target_name = attack_result.get("target", "enemy")
        damage = attack_result.get("damage")
        
        if outcome == Outcome.SUCCESS:
            if damage:
                damage_total = damage.get("total", 0)
                lines.append(f"- 命中结果 / Attack: 命中 (HIT)")
                lines.append(f"- 伤害数值 / Damage: {damage_total} 点")
                if target:
                    new_hp = max(0, target.hp - damage_total)
                    lines.append(f"- 目标状态 / Target State: {target.name} HP 从 {target.hp} 变为 {new_hp}")
            else:
                lines.append(f"- 命中结果 / Attack: 命中 (HIT)，但未造成伤害")
        else:
            lines.append(f"- 命中结果 / Attack: 未命中 (MISS)")
            lines.append(f"- 伤害数值 / Damage: 0 (攻击未命中，无伤害)")
    
    # State changes from effects
    if effects:
        for eff in effects:
            if eff.field == "hp" and isinstance(eff.delta, int):
                delta_str = f"+{eff.delta}" if eff.delta > 0 else str(eff.delta)
                lines.append(f"- 状态变更 / State Change: {eff.target} HP {delta_str}")
            elif eff.field == "conditions_add" and isinstance(eff.delta, str):
                lines.append(f"- 状态变更 / State Change: {eff.target} 获得状态 [{eff.delta}]")
            elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
                lines.append(f"- 状态变更 / State Change: {eff.target} 移除状态 [{eff.delta}]")
    
    return lines


def _build_narrative_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
) -> str:
    """Build the user prompt for narrative generation with hard constraints.
    
    The prompt explicitly separates:
    1. 【硬约束区】Hard Constraints - rule engine facts (ABSOLUTE)
    2. 【叙事空间】Narrative Space - context for creative writing
    """
    lines: list[str] = []
    
    # ========================================================================
    # SECTION 1: HARD CONSTRAINTS (硬约束区)
    # These are inviolable facts from the rule engine
    # ========================================================================
    lines.append("【硬约束区 / HARD CONSTRAINTS】")
    lines.append("以下是由规则引擎裁定的确定事实，叙事必须与此完全一致，不可更改：")
    lines.append("")
    
    hard_constraints = _build_hard_constraints(
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        effects=effects,
        actor=actor,
        target=target,
    )
    lines.extend(hard_constraints)
    lines.append("")
    lines.append("=" * 60)
    lines.append("")
    
    # ========================================================================
    # SECTION 2: NARRATIVE SPACE (叙事空间)
    # Context for creative writing (AI has freedom here)
    # ========================================================================
    lines.append("【叙事空间 / NARRATIVE SPACE】")
    lines.append("以下信息供叙事参考，你可以自由发挥：")
    lines.append("")
    
    # Scene context
    lines.append(f"场景 / Scene: {scene.name}")
    lines.append(f"场景描述 / Scene Description: {scene.description}")
    lines.append("")
    
    # Character context
    lines.append(f"角色 / Character: {actor.name}")
    lines.append(f"角色描述 / Character Description: {actor.description}")
    lines.append(f"角色状态 / Character Status: HP {actor.hp}/{actor.hp_max}")
    lines.append("")
    
    # Action context
    lines.append(f"行动意图 / Action Intent: {req.intent}")
    lines.append(f"行动方式 / Action Approach: {req.approach}")
    
    # Ability context (flavor only, no numbers)
    if check_result:
        ability = check_result.get("ability", "")
        ability_desc = {
            "str": "力量与体格 / strength and physical power",
            "dex": "敏捷与灵巧 / agility and finesse",
            "con": "体质与耐力 / endurance and resilience",
            "int": "智力与学识 / intellect and knowledge",
            "wis": "感知与洞察 / perception and insight",
            "cha": "魅力与个性 / force of personality",
        }.get(ability, ability)
        lines.append(f"相关属性 / Relevant Ability: {ability_desc}")
    
    # Combat context
    if attack_result:
        weapon = attack_result.get("weapon", "weapon")
        target_name = attack_result.get("target", "enemy")
        lines.append("")
        lines.append(f"战斗信息 / Combat Info:")
        lines.append(f"- 武器 / Weapon: {weapon}")
        lines.append(f"- 目标 / Target: {target_name}")
    
    # ========================================================================
    # SECTION 3: WRITING INSTRUCTION
    # ========================================================================
    lines.append("")
    lines.append("=" * 60)
    lines.append("")
    lines.append("【写作指示 / WRITING INSTRUCTION】")
    lines.append("基于以上硬约束和叙事空间，返回一个 JSON 对象，包含 action_result 与 scene_progression 两个字段。")
    lines.append("要求：")
    lines.append("1. 严格遵守硬约束区的事实，不得与之矛盾")
    lines.append("2. 如果结果是失败，绝对不能描述为成功或命中")
    lines.append("3. 如果伤害是0，绝对不能描述为造成伤害")
    lines.append("4. 使用生动的感官细节，避免系统术语")
    lines.append("5. scene_progression 必须至少包含 NPC 反应、环境变化、或对玩家的明确提示之一")
    lines.append('6. 仅返回 JSON，例如 {"action_result": "...", "scene_progression": "..."}')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fallback Templates (when API is unavailable)
# ---------------------------------------------------------------------------

def _fallback_action_result(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
) -> str:
    """Generate a template fallback narrative when API is unavailable."""
    
    if attack_result:
        # Combat fallback
        weapon = attack_result.get("weapon", "weapon")
        target = attack_result.get("target", "enemy")
        
        if outcome == Outcome.SUCCESS:
            damage = attack_result.get("damage")
            if damage:
                return (
                    f"{actor.name} lunges forward with {weapon} in hand, striking at the {target}. "
                    f"The blow lands cleanly, and the impact echoes through the scene."
                )
            else:
                return (
                    f"{actor.name} swings the {weapon} in a wide arc, catching the {target} "
                    f"off-guard. The attack hits its mark."
                )
        else:
            # Miss - include "miss" for test compatibility
            return (
                f"{actor.name} attacks {target} with the {weapon}, "
                f"but misses as the {target} dances aside at the last moment."
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

    if outcome == Outcome.SUCCESS:
        return (
            f"A ripple of response moves through {scene.name} as the moment settles into its new shape. "
            f"You can follow the opening immediately, watch how others react, or probe the environment for what changed."
        )

    return (
        f"The setback leaves a brief opening for the world to answer back; sounds, glances, and pressure shift around {actor.name}. "
        f"You can reassess the room, respond to any NPC reaction, or try a new angle before the moment closes."
    )


def _fallback_narration_bundle(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
) -> NarrationBundle:
    return NarrationBundle(
        action_result=_fallback_action_result(req, actor, scene, outcome, attack_result),
        scene_progression=_fallback_scene_progression(req, actor, scene, outcome, attack_result),
    )


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

def _parse_narration_bundle(content: str) -> Optional[NarrationBundle]:
    """Parse the model response into the required two-part narration bundle."""
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
    if not action_result or not scene_progression:
        return None

    return NarrationBundle(
        action_result=action_result,
        scene_progression=scene_progression,
    )


async def _call_kimi_api(prompt: str) -> Optional[NarrationBundle]:
    """Call Kimi API to generate structured narrative text.
    
    Returns None if API call fails or times out.
    """
    if not KIMI_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 500,
    }
    
    try:
        async with httpx.AsyncClient(timeout=KIMI_TIMEOUT_SECONDS) as client:
            response = await client.post(
                KIMI_API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                if not content:
                    return None
                return _parse_narration_bundle(content.strip())
            return None
            
    except asyncio.TimeoutError:
        return None
    except httpx.HTTPError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_narration(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    target: Optional[Actor] = None,
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
        
    Returns:
        Narration bundle for action result and scene progression
    """
    # Build the prompt with hard constraints
    prompt = _build_narrative_prompt(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        effects=effects,
        target=target,
    )
    
    # Try to call Kimi API (only if key is configured)
    if KIMI_API_KEY:
        try:
            # Use a new event loop to avoid issues with existing loops
            loop = asyncio.new_event_loop()
            try:
                narrative = loop.run_until_complete(_call_kimi_api(prompt))
                if narrative:
                    return narrative
            finally:
                loop.close()
        except Exception:
            pass
    
    # Fall back to template
    return _fallback_narration_bundle(req, actor, scene, outcome, attack_result)
