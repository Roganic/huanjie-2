"""Narrative generation using configurable AI providers.

Provides immersive, GM-style narrative text for game actions.
Falls back to template narratives when no provider is available.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from ..models.action import ActionRequest, ActionResponse, Outcome
from ..models.state import Actor, Scene
from .providers import get_provider

# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT = """You are a skilled Game Master (GM) for a fantasy tabletop RPG. 
Your task is to write immersive narrative descriptions of player actions.

Guidelines:
- Write in second person ("you") or third person limited perspective
- Use vivid, atmospheric language that fits the fantasy setting
- Describe the action, its outcome, and the immediate consequences
- Keep it to 1-3 paragraphs (150-300 words)
- Focus on sensory details: what the character sees, hears, feels
- For combat: describe the tension, the clash of weapons, the impact
- For skill checks: describe the effort, the struggle, the result
- Never use system terminology like "roll", "DC", "modifier", "check"
- Never break character or mention game mechanics explicitly

Tone: dramatic but not overwrought, grounded fantasy adventure."""


def _build_narrative_prompt(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
) -> str:
    """Build the user prompt for narrative generation."""

    # Build context section
    context_lines = [
        f"Scene: {scene.name}",
        f"Scene Description: {scene.description}",
        f"",
        f"Character: {actor.name}",
        f"Character Description: {actor.description}",
        f"Character Status: HP {actor.hp}/{actor.hp_max}",
        f"",
        f"Action Intent: {req.intent}",
        f"Action Approach: {req.approach}",
        f"Outcome: {outcome.value.upper()}",
    ]

    # Add check details if present (without game mechanics terminology)
    if check_result:
        ability = check_result.get("ability", "")
        ability_desc = {
            "str": "strength and physical power",
            "dex": "agility and finesse",
            "con": "endurance and resilience",
            "int": "intellect and knowledge",
            "wis": "perception and insight",
            "cha": "force of personality",
        }.get(ability, ability)
        context_lines.append(f"This action relied on the character's {ability_desc}.")

    # Add attack details if present
    if attack_result:
        weapon = attack_result.get("weapon", "weapon")
        target = attack_result.get("target", "enemy")
        damage = attack_result.get("damage")
        context_lines.append(f"")
        context_lines.append(f"Combat Details:")
        context_lines.append(f"- Weapon: {weapon}")
        context_lines.append(f"- Target: {target}")
        if damage and outcome == Outcome.SUCCESS:
            context_lines.append(f"- The attack landed a solid hit, dealing significant damage.")
        elif outcome == Outcome.FAILURE:
            context_lines.append(f"- The attack failed to connect.")

    context_lines.append(f"")
    context_lines.append(f"Write an immersive narrative describing this moment.")

    return "\n".join(context_lines)


# ---------------------------------------------------------------------------
# Fallback Templates (when API is unavailable)
# ---------------------------------------------------------------------------

def _fallback_narration(
    req: ActionRequest,
    actor: Actor,
    scene: Scene,
    outcome: Outcome,
    attack_result: Optional[dict] = None,
) -> str:
    """Generate a template fallback narrative when API is unavailable."""

    action_desc = f"{req.actor} {req.intent}"

    if attack_result:
        # Combat fallback
        weapon = attack_result.get("weapon", "weapon")
        target = attack_result.get("target", "enemy")

        if outcome == Outcome.SUCCESS:
            damage = attack_result.get("damage")
            if damage:
                return (
                    f"{actor.name} lunges forward with {weapon} in hand, striking at the {target}. "
                    f"The attack hits true, biting into flesh with a sickening crunch."
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
) -> str:
    """Generate narrative text for an action resolution.

    Provider selection:
      1. ``req.provider`` if explicitly requested and available
      2. First available provider from environment configuration
      3. Fallback template if no provider is configured

    Args:
        req: The action request (may include ``provider`` override)
        actor: The acting character
        scene: The current scene
        outcome: Success or failure
        check_result: Optional check details
        attack_result: Optional attack details

    Returns:
        Immersive narrative text (or fallback if API unavailable)
    """
    prompt = _build_narrative_prompt(req, actor, scene, outcome, check_result, attack_result)

    provider = get_provider(req.provider)
    if provider is not None:
        try:
            loop = asyncio.new_event_loop()
            try:
                narrative = loop.run_until_complete(
                    provider.generate(NARRATIVE_SYSTEM_PROMPT, prompt)
                )
                if narrative:
                    return narrative
            finally:
                loop.close()
        except Exception:
            pass

    return _fallback_narration(req, actor, scene, outcome, attack_result)
