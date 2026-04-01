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
from ..models.state import Actor, NarrativeHistoryEntry, Scene
from .providers import get_provider
from .resolution_constraints import (
    NarrationConstraintContext,
    build_hard_constraints,
    build_narrative_prompt,
    find_contradictions,
)

# Backward-compatible export for existing scripts/tests.
KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
logger = logging.getLogger(__name__)

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
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    actor: Optional[Actor] = None,
    target: Optional[Actor] = None,
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
    provider = get_provider("kimi")
    if provider is None:
        return None
    generated = await provider.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
    return _parse_narration_bundle(generated) if generated else None


async def _call_openai_api(prompt: str) -> Optional[NarrationBundle]:
    provider = get_provider("openai")
    if provider is None:
        return None
    generated = await provider.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
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
    context = NarrationConstraintContext(
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        actor=actor,
        target=target,
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
    )

    def _run_provider(current_prompt: str) -> Optional[NarrationBundle]:
        try:
            import asyncio

            if req.provider == "openai":
                return asyncio.run(_call_openai_api(current_prompt))
            if req.provider == "kimi" or KIMI_API_KEY:
                return asyncio.run(_call_kimi_api(current_prompt))

            provider = get_provider(req.provider)
            if provider is None:
                return None

            generated = asyncio.run(provider.generate(NARRATIVE_SYSTEM_PROMPT, current_prompt))
            return _parse_narration_bundle(generated) if generated else None
        except Exception:
            return None

    narrative = _run_provider(prompt)
    if narrative:
        reasons = find_contradictions(
            action_result=narrative.action_result,
            scene_progression=narrative.scene_progression,
            context=context,
        )
        if not reasons:
            return narrative

        logger.warning(
            "Narration contradicted rule resolution; retrying once",
            extra={
                "outcome": outcome.value,
                "action_intent": req.intent,
                "reasons": reasons,
            },
        )
        retry_prompt = (
            f"{prompt}\n\n"
            "【修正要求 / CORRECTION REQUIRED】\n"
            "你上一版叙事与硬约束冲突。请严格修正，不得重复以下问题：\n"
            f"{json.dumps(reasons, ensure_ascii=False)}"
        )
        retry_narrative = _run_provider(retry_prompt)
        if retry_narrative:
            retry_reasons = find_contradictions(
                action_result=retry_narrative.action_result,
                scene_progression=retry_narrative.scene_progression,
                context=context,
            )
            if not retry_reasons:
                return retry_narrative

            logger.warning(
                "Narration retry still contradicted rule resolution; using fallback",
                extra={
                    "outcome": outcome.value,
                    "action_intent": req.intent,
                    "reasons": retry_reasons,
                },
            )

    return _fallback_narration_bundle(req, actor, scene, outcome, attack_result)
