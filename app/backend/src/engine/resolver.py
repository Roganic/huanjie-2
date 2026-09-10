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
from ..spells.spell_resolver import (
    cast_spell,
    is_cast_command,
    is_rest_command,
    parse_cast_command,
)
from ..spells.spell_registry import get_spell
from ..spells.spell_resolver import restore_spell_slots as _restore_spell_slots

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
    "环顾四周", "看看周围", "四处看看", "坐下", "站起来",
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
    "陷阱", "隐藏", "秘密", "危险", "潜行", "偷窃", "说服", "威胁",
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

    # Route spell cast commands to spell resolver
    if is_cast_command(req.intent):
        return _resolve_spell_cast(req)

    # Handle rest commands
    is_rest, rest_type = is_rest_command(req.intent)
    if is_rest:
        return _resolve_rest(req, rest_type)

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
    prof = 0  # Generic ability checks do not automatically gain skill proficiency.
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
    # Priority: 1. Request override, 2. Equipped weapon, 3. Unarmed fallback
    if req.weapon:
        weapon = req.weapon
        damage_dice = req.damage_dice or get_weapon_damage(weapon)
    elif actor.equipped and actor.equipped.weapon:
        # Use equipped weapon
        equipped_weapon = actor.equipped.weapon
        weapon = equipped_weapon.name
        damage_dice = req.damage_dice or equipped_weapon.damage_dice or get_weapon_damage(equipped_weapon.id)
    else:
        # Unarmed attack fallback
        weapon = "unarmed"
        damage_dice = req.damage_dice or "1d4"

    # Determine attack ability (STR for melee, DEX for finesse/ranged)
    # Priority: 1. Request override, 2. Equipped weapon's attack_ability, 3. Inferred from weapon name
    if req.ability:
        ability = req.ability
    elif actor.equipped and actor.equipped.weapon and actor.equipped.weapon.attack_ability:
        ability = actor.equipped.weapon.attack_ability
    else:
        ability = _infer_attack_ability(weapon)
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

    if outcome == Outcome.SUCCESS:
        # Hit! Roll damage: weapon dice + ability modifier
        damage_rolls_total, damage_rolls = roll_damage(damage_dice)
        damage_modifier = modifier  # Add ability modifier to damage
        damage_calculated = max(1, damage_rolls_total + damage_modifier)  # Minimum 1 damage on hit
        damage_applied = min(damage_calculated, target.hp)  # Cap at target's remaining HP for effect
        damage_detail = DamageDetail(
            dice_expression=damage_dice,
            rolls=damage_rolls,
            modifier=damage_modifier,
            total=damage_calculated,  # Report calculated total (not capped by HP)
        )
        attack_detail.damage = damage_detail

        # Apply damage effect to target (capped by remaining HP)
        effects.append(
            Effect(
                target=target.id,
                field="hp",
                delta=-damage_applied,
                description=f"{actor.name} hits {target.name} with {weapon} for {damage_applied} damage.",
            )
        )

        # Check if target is defeated
        new_hp = max(0, target.hp - damage_applied)
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
        "damage": damage_detail.model_dump() if outcome == Outcome.SUCCESS and attack_detail.damage else None,
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
# Spell Resolution
# ---------------------------------------------------------------------------


def _resolve_spell_cast(req: ActionRequest) -> ActionResponse:
    """Resolve a spell casting action."""
    actor = get_actor()
    scene = get_scene()
    
    # Parse spell name and target from intent
    spell_name, target_name = parse_cast_command(req.intent)
    
    if spell_name is None:
        return ActionResponse(
            action_summary=f"{req.actor} attempts to cast a spell",
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=None,
            outcome=Outcome.FAILURE,
            effects=[],
            narration="无法识别你想施放的法术。",
            scene_progression="请明确你想施放什么法术。",
            gm_prompt="Ask the player to specify which spell they want to cast.",
        )
    
    # Look up target if specified
    target = None
    if target_name:
        target = get_actor_by_id_or_name(target_name)
    if target is None:
        # Default to enemy if no target specified or target not found
        from ..state import get_enemy
        target = get_enemy()
    
    # Cast the spell
    result = cast_spell(actor, spell_name, target)
    
    # Build action summary
    action_summary = f"{actor.name} 施放 {result.spell_name}"
    if result.target:
        action_summary += f" 攻击 {result.target}"
    
    # Build effects
    effects: list[Effect] = []
    
    # Add spell slot consumption effect (for tracking)
    if result.slot_level > 0:
        effects.append(
            Effect(
                target=actor.id,
                field="spell_slot_consumed",
                delta=result.slot_level,
                description=f"消耗 {result.slot_level} 环法术位",
            )
        )
    
    # Add damage effect if hit
    if result.damage and result.damage > 0 and target:
        damage_applied = min(result.damage, target.hp)
        effects.append(
            Effect(
                target=target.id,
                field="hp",
                delta=-damage_applied,
                description=f"{result.spell_name} 造成 {damage_applied} 点 {result.damage_type.value if result.damage_type else ''}伤害",
            )
        )
        
        # Check if target is defeated
        new_hp = max(0, target.hp - damage_applied)
        if new_hp == 0:
            effects.append(
                Effect(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} 被法术击败了！",
                )
            )
    
    # Always advance time
    effects.append(
        Effect(
            target=scene.id,
            field="time",
            delta=1,
            description="施法消耗时间。",
        )
    )
    
    # Build attack detail for attack roll spells
    attack_detail = None
    if result.requires_attack_roll and result.attack_roll is not None:
        from ..models.action import DamageDetail
        spell_obj = get_spell(spell_name)
        damage_dice = spell_obj.damage_dice if spell_obj else "1d8"
        attack_detail = AttackDetail(
            target=target.id if target else "unknown",
            weapon=result.spell_name,
            hit_roll=result.attack_roll,
            total_attack=result.attack_total or result.attack_roll,
            target_ac=result.target_ac or (target.ac if target else 10),
            damage=DamageDetail(
                dice_expression=damage_dice,
                rolls=result.damage_rolls,
                modifier=result.damage_modifier,
                total=result.damage or 0,
            ) if result.damage else None,
        )
    
    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=None,
        attack=attack_detail,
        outcome=Outcome.SUCCESS if result.success else Outcome.FAILURE,
        effects=effects,
        narration=result.narrative if result.success else (result.error_message or "施法失败。"),
        scene_progression="法术效果已经展现。" if result.success else "施法被打断或失败了。",
        gm_prompt="Continue the scene based on the spell's effect." if result.success else "Ask what the player wants to do next.",
    )


def _resolve_rest(req: ActionRequest, rest_type: str) -> ActionResponse:
    """Resolve a rest action (short or long rest)."""
    actor = get_actor()
    scene = get_scene()
    
    action_summary = f"{actor.name} 进行{ '短休' if rest_type == 'short' else '长休' }"
    
    effects: list[Effect] = []
    
    # Restore spell slots on long rest
    if rest_type == "long":
        restored = _restore_spell_slots(actor, rest_type)
        if restored:
            effects.append(
                Effect(
                    target=actor.id,
                    field="spell_slots_restored",
                    delta=1,
                    description="所有法术位已恢复",
                )
            )
            narration = f"{actor.name} 完成长休，所有法术位已恢复。"
        else:
            narration = f"{actor.name} 完成长休。"
    else:
        # Short rest does not restore spell slots for mages
        narration = f"{actor.name} 完成短休。法师的法术位只能通过长休恢复。"
    
    # Advance time significantly
    time_delta = 60 if rest_type == "short" else 480  # 1 hour or 8 hours
    effects.append(
        Effect(
            target=scene.id,
            field="time",
            delta=time_delta,
            description=f"{'短休' if rest_type == 'short' else '长休'}消耗时间。",
        )
    )
    
    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.AUTO_SUCCESS,
        check=None,
        attack=None,
        outcome=Outcome.SUCCESS,
        effects=effects,
        narration=narration,
        scene_progression="休息后，你感觉精神焕发。",
        gm_prompt="Describe the rest and what the character notices upon waking.",
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
