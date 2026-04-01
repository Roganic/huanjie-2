"""Action resolution engine.

Implements the V1 core loop step 2-3:
  GM judges whether the action is auto-success or needs a check,
  then the rules engine returns a structured result.
"""

from __future__ import annotations

from typing import Optional

from ..agent.narrator import generate_narration
from ..models.action import (
    ActionRequest,
    ActionResponse,
    ActionType,
    AttackDetail,
    CheckDetail,
    DamageDetail,
    Effect,
    Outcome,
    ResolutionType,
)
from ..models.state import Actor
from ..state import get_actor, get_actor_by_id_or_name, get_scene
from .dice import get_weapon_damage, roll_d20, roll_damage

# ---------------------------------------------------------------------------
# DC tiers (rules-core: "先压缩成少量稳定档位，例如 10 / 15 / 20")
# ---------------------------------------------------------------------------

DC_EASY = 10
DC_MEDIUM = 15
DC_HARD = 20

# ---------------------------------------------------------------------------
# Auto-success: only truly trivial, zero-risk actions skip the roll.
# Each phrase must be specific enough to avoid matching non-trivial variants
# like "open the locked chest" or "talk the guard into letting us pass".
# ---------------------------------------------------------------------------

AUTO_SUCCESS_PHRASES = [
    "look around",
    "look at",
    "walk to",
    "walk over",
    "sit down",
    "stand up",
    "put down",
    "pick up",        # picking up an uncontested item, not pick a lock
]

# If any of these words appear alongside a phrase match, the action is
# probably non-trivial and should NOT auto-succeed.
AUTO_SUCCESS_DISQUALIFIERS = [
    "locked", "trapped", "guard", "convince", "persuade", "deceive",
    "lie", "trick", "sneak", "steal", "force", "break", "dangerous",
    "difficult", "careful", "secret", "hidden",
]

# ---------------------------------------------------------------------------
# Skill to ability mapping (D&D 5e standard)
# ---------------------------------------------------------------------------

SKILL_ABILITIES: dict[str, str] = {
    "athletics": "str",
    "acrobatics": "dex",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    "arcana": "int",
    "history": "int",
    "investigation": "int",
    "nature": "int",
    "religion": "int",
    "animal_handling": "wis",
    "insight": "wis",
    "medicine": "wis",
    "perception": "wis",
    "survival": "wis",
    "deception": "cha",
    "intimidation": "cha",
    "performance": "cha",
    "persuasion": "cha",
}

# ---------------------------------------------------------------------------
# Simple ability inference from approach text
# ---------------------------------------------------------------------------

ABILITY_HINTS: dict[str, list[str]] = {
    "str": ["push", "lift", "force", "break", "climb", "grapple", "shove"],
    "dex": ["dodge", "sneak", "hide", "pick", "steal", "acrobat", "tumble"],
    "con": ["endure", "resist", "hold breath", "withstand", "tough"],
    "int": ["recall", "investigate", "analyze", "decipher", "study", "know"],
    "wis": ["perceive", "sense", "insight", "track", "notice", "spot", "listen"],
    "cha": ["persuade", "deceive", "intimidate", "perform", "charm", "bluff"],
}

# Weapon ability mapping (finesse weapons can use DEX, others use STR)
FINESSE_WEAPONS = {"dagger", "rapier", "scimitar", "shortsword"}
RANGED_WEAPONS = {"shortbow", "longbow", "light_crossbow", "heavy_crossbow"}


def _infer_ability(approach: str) -> str:
    """Guess the most relevant ability from approach text."""
    lower = approach.lower()
    for ability, keywords in ABILITY_HINTS.items():
        for kw in keywords:
            if kw in lower:
                return ability
    return "str"


def _infer_attack_ability(weapon: str) -> str:
    """Determine ability modifier for attack based on weapon type."""
    weapon_lower = weapon.lower()
    if weapon_lower in FINESSE_WEAPONS:
        # Finesse: use STR or DEX, assume DEX for simplicity
        return "dex"
    if weapon_lower in RANGED_WEAPONS:
        return "dex"
    return "str"


def _is_auto_success(intent: str, approach: str) -> bool:
    """Return True only for genuinely trivial, zero-risk actions.

    Requires a known trivial phrase AND the absence of any disqualifier
    that would indicate uncertainty or opposition.
    """
    lower = f"{intent} {approach}".lower()
    has_trivial_phrase = any(phrase in lower for phrase in AUTO_SUCCESS_PHRASES)
    if not has_trivial_phrase:
        return False
    has_disqualifier = any(dq in lower for dq in AUTO_SUCCESS_DISQUALIFIERS)
    return not has_disqualifier


def _pick_dc(intent: str) -> int:
    """Assign a DC tier based on simple keyword heuristics."""
    lower = intent.lower()
    if any(w in lower for w in ["hard", "difficult", "dangerous", "impossible"]):
        return DC_HARD
    if any(w in lower for w in ["careful", "tricky", "complex"]):
        return DC_MEDIUM
    return DC_MEDIUM  # default to medium








def _resolve_skill_check(req: ActionRequest) -> ActionResponse:
    """Resolve a skill check action (d20 + ability mod + prof if proficient).
    
    Skill checks differ from generic ability checks in that proficiency bonus
    is only added if the character is proficient in that specific skill.
    """
    actor = get_actor()
    scene = get_scene()

    action_summary = f"{req.actor} attempts to use {req.skill} to {req.intent}"

    # Determine skill and governing ability
    skill_name = req.skill or "athletics"
    ability = req.ability or _get_skill_ability(skill_name)
    
    # Calculate modifiers
    ability_modifier = actor.abilities.modifier(ability)
    is_proficient = _is_skill_proficient(actor, skill_name)
    prof_bonus = actor.proficiency_bonus if is_proficient else 0
    
    dc = req.dc or _pick_dc(req.intent)
    advantage = req.advantage

    # Roll d20 + ability modifier + proficiency (if proficient)
    roll = roll_d20(advantage)
    total = roll + ability_modifier + prof_bonus
    outcome = Outcome.SUCCESS if total >= dc else Outcome.FAILURE

    check = CheckDetail(
        ability=ability,
        modifier=ability_modifier,
        proficiency_bonus=prof_bonus,
        advantage=advantage,
        roll=roll,
        total=total,
        dc=dc,
        skill_name=skill_name,
    )

    effects: list[Effect] = _build_effects(
        actor_id=actor.id,
        scene_id=scene.id,
        ability=ability,
        outcome=outcome,
    )

    # Build check result for narrative generation
    check_result = {
        "ability": ability,
        "skill": skill_name,
        "proficient": is_proficient,
        "modifier": ability_modifier,
        "proficiency_bonus": prof_bonus,
        "dc": dc,
        "roll": roll,
        "total": total,
    }
    
    narration = generate_narration(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        check_result=check_result,
        effects=effects,
    )

    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=check,
        attack=None,
        outcome=outcome,
        effects=effects,
        narration=narration.action_result,
        scene_progression=narration.scene_progression,
        gm_prompt=narration.gm_prompt,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _is_skill_proficient(actor, skill_name: str) -> bool:
    """Check if actor is proficient in a given skill."""
    if not skill_name:
        return False
    skill_name_lower = skill_name.lower()
    for skill in actor.skills:
        if skill.name.lower() == skill_name_lower:
            return skill.proficient
    return False


def _get_skill_ability(skill_name: str) -> str:
    """Get the governing ability for a skill."""
    return SKILL_ABILITIES.get(skill_name.lower(), "str")


def resolve_action(req: ActionRequest) -> ActionResponse:
    """Resolve a player action into a structured result.

    Flow:
      1. Determine if auto-success or check needed
      2. If check: roll d20 + modifier + proficiency vs DC
      3. Build structured response with narration stub
    """
    # Route attack actions to combat resolver
    if req.action_type == ActionType.ATTACK or req.weapon is not None:
        return _resolve_attack(req)

    # Route skill check actions to skill resolver
    if req.action_type == ActionType.SKILL_CHECK or req.skill is not None:
        return _resolve_skill_check(req)

    action_summary = f"{req.actor} attempts to {req.intent} by {req.approach}"
    
    # Get state early for narrative generation
    actor = get_actor()
    scene = get_scene()

    # --- auto-success path ---
    if _is_auto_success(req.intent, req.approach):
        # Auto-success actions are truly trivial, so no time cost or effects
        narration = generate_narration(
            req=req,
            actor=actor,
            scene=scene,
            outcome=Outcome.SUCCESS,
            effects=[],
        )
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            check=None,
            attack=None,
            outcome=Outcome.SUCCESS,
            effects=[],
            narration=narration.action_result,
            scene_progression=narration.scene_progression,
            gm_prompt=narration.gm_prompt,
        )

    # --- generic ability check path ---
    ability = req.ability or _infer_ability(req.approach)
    modifier = actor.abilities.modifier(ability)
    prof = actor.proficiency_bonus  # Generic checks add full prof for simplicity
    dc = req.dc or _pick_dc(req.intent)
    advantage = req.advantage

    roll = roll_d20(advantage)
    total = roll + modifier + prof
    outcome = Outcome.SUCCESS if total >= dc else Outcome.FAILURE

    check = CheckDetail(
        ability=ability,
        modifier=modifier,
        proficiency_bonus=prof,
        advantage=advantage,
        roll=roll,
        total=total,
        dc=dc,
        skill_name=None,
    )

    effects: list[Effect] = _build_effects(
        actor_id=actor.id,
        scene_id=scene.id,
        ability=ability,
        outcome=outcome,
    )

    # Generate AI narration with fallback
    check_result = {
        "ability": ability,
        "modifier": modifier,
        "dc": dc,
        "roll": roll,
        "total": total,
    }
    narration = generate_narration(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        check_result=check_result,
        effects=effects,
    )

    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=check,
        attack=None,
        outcome=outcome,
        effects=effects,
        narration=narration.action_result,
        scene_progression=narration.scene_progression,
        gm_prompt=narration.gm_prompt,
    )


def _resolve_attack(req: ActionRequest) -> ActionResponse:
    """Resolve an attack action (attack roll vs AC, then damage on hit)."""
    actor = get_actor()
    scene = get_scene()

    # Get target (default to enemy if not specified)
    target_id = req.target or "goblin-01"
    target = get_actor_by_id_or_name(target_id)

    # If target not found, treat as generic check
    if target is None:
        action_summary = f"{req.actor} attacks {target_id} with {req.weapon or 'weapon'}"
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=None,
            outcome=Outcome.FAILURE,
            effects=[],
            narration=f"{action_summary} — but the target cannot be found.",
            scene_progression="The confusion breaks the flow of the moment. You can identify a clear target, study the scene, or shift your approach before acting again.",
            gm_prompt="The moment hesitates instead of resolving. Name a clear target or a sharper intent before the scene answers back.",
        )

    # Determine weapon and damage dice
    weapon = req.weapon or "longsword"
    damage_dice = req.damage_dice or get_weapon_damage(weapon)

    # Determine attack ability (STR for melee, DEX for finesse/ranged)
    ability = req.ability or _infer_attack_ability(weapon)
    modifier = actor.abilities.modifier(ability)
    prof = actor.proficiency_bonus
    advantage = req.advantage

    # Attack roll: d20 + ability modifier + proficiency bonus
    hit_roll = roll_d20(advantage)
    total_attack = hit_roll + modifier + prof
    target_ac = target.ac

    outcome = Outcome.SUCCESS if total_attack >= target_ac else Outcome.FAILURE

    # Build attack detail
    attack_detail = AttackDetail(
        target=target.id,
        weapon=weapon,
        hit_roll=hit_roll,
        total_attack=total_attack,
        target_ac=target_ac,
        damage=None,
    )

    effects: list[Effect] = []
    damage_detail: Optional[DamageDetail] = None
    damage_total: Optional[int] = None
    damage_rolls: Optional[list[int]] = None

    if outcome == Outcome.SUCCESS:
        # Hit! Roll damage: weapon dice + ability modifier
        damage_rolls_total, damage_rolls = roll_damage(damage_dice)
        damage_modifier = modifier  # Add ability modifier to damage
        damage_total = max(1, damage_rolls_total + damage_modifier)  # Minimum 1 damage on hit
        damage_total = min(damage_total, target.hp)  # Cap at target's remaining HP
        damage_detail = DamageDetail(
            dice_expression=damage_dice,
            rolls=damage_rolls,
            modifier=damage_modifier,
            total=damage_total,
        )
        attack_detail.damage = damage_detail

        # Apply damage effect to target
        effects.append(
            Effect(
                target=target.id,
                field="hp",
                delta=-damage_total,
                description=f"{actor.name} hits {target.name} with {weapon} for {damage_total} damage.",
            )
        )

        # Check if target is defeated
        new_hp = max(0, target.hp - damage_total)
        if new_hp == 0:
            effects.append(
                Effect(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} has been defeated!",
                )
            )

    # Always advance time
    effects.append(
        Effect(
            target=scene.id,
            field="time",
            delta=1,
            description="Combat time passes.",
        )
    )

    action_summary = f"{actor.name} attacks {target.name} with {weapon}"
    
    # Build attack result for narrative generation
    attack_result = {
        "weapon": weapon,
        "target": target.name,
        "damage": damage_detail.model_dump() if damage_detail else None,
    }
    
    # Generate AI narration with fallback (pass target and effects for hard constraints)
    narration = generate_narration(
        req=req,
        actor=actor,
        scene=scene,
        outcome=outcome,
        attack_result=attack_result,
        effects=effects,
        target=target,
    )

    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=None,
        attack=attack_detail,
        outcome=outcome,
        effects=effects,
        narration=narration.action_result,
        scene_progression=narration.scene_progression,
        gm_prompt=narration.gm_prompt,
    )


# ---------------------------------------------------------------------------
# Effect generation
# ---------------------------------------------------------------------------

_PHYSICAL_ABILITIES = {"str", "dex", "con"}


def _build_effects(
    *,
    actor_id: str,
    scene_id: str,
    ability: str,
    outcome: Outcome,
) -> list[Effect]:
    """Build concrete, applyable effects for a resolved check."""
    effects: list[Effect] = []

    # Every check costs one abstract time tick.
    effects.append(
        Effect(
            target=scene_id,
            field="time",
            delta=1,
            description="Time passes.",
        )
    )

    if outcome == Outcome.FAILURE:
        if ability in _PHYSICAL_ABILITIES:
            effects.append(
                Effect(
                    target=actor_id,
                    field="hp",
                    delta=-1,
                    description="The failed physical effort causes minor harm.",
                )
            )
        else:
            effects.append(
                Effect(
                    target=actor_id,
                    field="narrative_state",
                    delta="setback",
                    description="The failed attempt may attract attention or waste time.",
                )
            )

    return effects
