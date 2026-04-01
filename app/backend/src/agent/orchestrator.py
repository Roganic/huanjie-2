"""GM Agent orchestrator.

Implements the GM Agent that drives action resolution through tool calls.
The agent can perform multi-step reasoning, calling multiple tools in sequence
before generating the final narrative.

Example multi-step scenario:
1. Player casts a spell requiring attack roll + saving throw
2. Agent calls roll_dice for attack
3. Agent calls roll_dice for damage (on hit)
4. Agent calls roll_dice for target's saving throw
5. Agent applies state changes (damage, conditions)
6. Agent generates narrative
"""

from __future__ import annotations

from typing import Optional

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
    SavingThrowDetail,
)
from ..models.state import Actor, NarrativeHistoryEntry
from ..state import (
    append_narrative_history,
    get_actor,
    get_actor_by_id_or_name,
    get_narrative_context,
    get_scene,
)
from .narrator import generate_narration
from .tools import (
    ApplyStateChangeResult,
    CurrentStateResult,
    DiceType,
    NarrativeResult,
    RollDiceResult,
    ToolResultType,
    ToolType,
    tool_apply_state_change,
    tool_generate_narrative,
    tool_get_current_state,
    tool_roll_dice,
)


# ---------------------------------------------------------------------------
# DC Tiers
# ---------------------------------------------------------------------------

DC_EASY = 10
DC_MEDIUM = 15
DC_HARD = 20


# ---------------------------------------------------------------------------
# GM Agent
# ---------------------------------------------------------------------------

class GMAgent:
    """Game Master Agent that orchestrates action resolution.
    
    The GM Agent is the primary driver of action resolution. It:
    1. Analyzes the action request and current state
    2. Decides what checks/rolls are needed
    3. Executes tools in sequence (dice rolls, state changes)
    4. Generates narrative after all mechanical resolution is complete
    5. Returns a consistent ActionResponse
    
    All state changes are applied during orchestration, ensuring the game
    state is consistent when returned to the frontend.
    """
    
    def __init__(self):
        self.tool_results: list[ToolResultType] = []
        self.effects: list[Effect] = []
    
    def reset(self) -> None:
        """Reset agent state for a new action."""
        self.tool_results = []
        self.effects = []
    
    def resolve(self, req: ActionRequest) -> ActionResponse:
        """Resolve an action using GM Agent orchestration.
        
        This is the main entry point. The agent will:
        1. Get current state
        2. Determine what resolution path to take
        3. Execute necessary tool calls
        4. Apply all state changes
        5. Generate narrative
        6. Return complete ActionResponse
        
        Args:
            req: The player's action request
            
        Returns:
            Complete action response with narration
        """
        self.reset()
        
        # Step 1: Get current state
        state_result = self._call_get_current_state()
        actor = state_result.actor
        
        # Step 2: Route to appropriate resolution path
        if req.action_type == ActionType.SPELL_ATTACK or req.requires_saving_throw:
            return self._resolve_spell_attack(req, actor)
        
        if req.action_type == ActionType.ATTACK or req.weapon is not None:
            return self._resolve_attack(req, actor)
        
        return self._resolve_generic_action(req, actor)
    
    def _call_get_current_state(self) -> CurrentStateResult:
        """Call get_current_state tool and record result."""
        result = tool_get_current_state()
        self.tool_results.append(result)
        return result
    
    def _call_roll_dice(
        self,
        dice_type: DiceType,
        reason: str,
        advantage: Optional[bool] = None,
        dice_expression: Optional[str] = None,
        modifier: int = 0,
    ) -> RollDiceResult:
        """Call roll_dice tool and record result."""
        result = tool_roll_dice(
            dice_type=dice_type,
            reason=reason,
            advantage=advantage,
            dice_expression=dice_expression,
            modifier=modifier,
        )
        self.tool_results.append(result)
        return result
    
    def _call_apply_state_change(
        self,
        target: str,
        field: str,
        delta: int | str,
        description: str,
    ) -> ApplyStateChangeResult:
        """Call apply_state_change tool and record result."""
        result = tool_apply_state_change(
            target=target,
            field=field,
            delta=delta,
            description=description,
        )
        self.tool_results.append(result)
        # Track effects for response
        self.effects.append(result.effect)
        return result
    
    def _call_generate_narrative(
        self,
        req: ActionRequest,
        outcome: Outcome,
        check_result: Optional[dict] = None,
        attack_result: Optional[dict] = None,
        saving_throw_result: Optional[dict] = None,
    ) -> NarrativeResult:
        """Call generate_narrative tool and record result."""
        result = tool_generate_narrative(
            req=req,
            outcome=outcome,
            check_result=check_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_result,
            effects=self.effects,
            narrative_history=get_narrative_context(),
        )
        self.tool_results.append(result)
        return result

    def _record_narrative_history(
        self,
        action_summary: str,
        resolution_type: ResolutionType,
        outcome: Outcome,
        narration_result: NarrativeResult,
        check_result: Optional[dict] = None,
        attack_result: Optional[dict] = None,
        saving_throw_result: Optional[dict] = None,
    ) -> None:
        """Persist a compact narrative memory item for future prompt context."""
        narration_summary = " ".join([
            narration_result.narrative.strip(),
            narration_result.scene_progression.strip(),
        ]).strip()

        append_narrative_history(
            NarrativeHistoryEntry(
                action_summary=action_summary,
                resolution_summary={
                    "resolution_type": resolution_type.value,
                    "outcome": outcome.value,
                    "check": check_result,
                    "attack": attack_result,
                    "saving_throw": saving_throw_result,
                    "effects": [effect.model_dump(mode="json") for effect in self.effects],
                },
                narration_summary=narration_summary[:400],
            )
        )
    
    # -----------------------------------------------------------------------
    # Resolution Paths
    # -----------------------------------------------------------------------
    
    def _resolve_generic_action(self, req: ActionRequest, actor: Actor) -> ActionResponse:
        """Resolve a generic (non-attack) action."""
        action_summary = f"{req.actor} attempts to {req.intent} by {req.approach}"
        
        # Check for auto-success
        if self._is_auto_success(req.intent, req.approach):
            return self._resolve_auto_success(req, actor, action_summary)
        
        # Resolve as ability check
        return self._resolve_ability_check(req, actor, action_summary)
    
    def _resolve_auto_success(
        self,
        req: ActionRequest,
        actor: Actor,
        action_summary: str,
    ) -> ActionResponse:
        """Resolve an auto-success action.
        
        Auto-success actions (trivial actions like looking around) don't
        advance time or cause any state changes - they just return narrative.
        """
        # Generate narrative (no state changes for auto-success)
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=Outcome.SUCCESS,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            outcome=Outcome.SUCCESS,
            narration_result=narrative_result,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            check=None,
            attack=None,
            outcome=Outcome.SUCCESS,
            effects=[],  # No effects for auto-success
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
        )
    
    def _resolve_ability_check(
        self,
        req: ActionRequest,
        actor: Actor,
        action_summary: str,
    ) -> ActionResponse:
        """Resolve an action requiring an ability check."""
        # Determine check parameters
        ability = req.ability or self._infer_ability(req.approach)
        modifier = actor.abilities.modifier(ability)
        prof = actor.proficiency_bonus
        dc = req.dc or self._pick_dc(req.intent)
        advantage = req.advantage
        
        # Step 1: Roll d20
        roll_result = self._call_roll_dice(
            dice_type=DiceType.D20,
            reason=f"{ability.upper()} check for {req.intent}",
            advantage=advantage,
            modifier=modifier + prof,
        )
        
        total = roll_result.total
        outcome = Outcome.SUCCESS if total >= dc else Outcome.FAILURE
        
        # Build check detail
        check = CheckDetail(
            ability=ability,
            modifier=modifier,
            proficiency_bonus=prof,
            advantage=advantage,
            roll=roll_result.roll,
            total=total,
            dc=dc,
        )
        
        # Step 2: Apply effects based on outcome
        self._apply_check_effects(actor, ability, outcome)
        
        # Step 3: Generate narrative
        check_result = {
            "ability": ability,
            "modifier": modifier,
            "dc": dc,
            "roll": roll_result.roll,
            "total": total,
        }
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=outcome,
            check_result=check_result,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            outcome=outcome,
            narration_result=narrative_result,
            check_result=check_result,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=check,
            attack=None,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
        )
    
    def _resolve_attack(self, req: ActionRequest, actor: Actor) -> ActionResponse:
        """Resolve an attack action (potentially multi-step)."""
        # Get target
        target_id = req.target or "goblin-01"
        target = get_actor_by_id_or_name(target_id)
        
        if target is None:
            return self._resolve_attack_no_target(req, actor, target_id)
        
        action_summary = f"{actor.name} attacks {target.name} with {req.weapon or 'weapon'}"
        
        # Determine attack parameters
        weapon = req.weapon or "longsword"
        damage_dice = req.damage_dice or self._get_weapon_damage(weapon)
        ability = req.ability or self._infer_attack_ability(weapon)
        modifier = actor.abilities.modifier(ability)
        prof = actor.proficiency_bonus
        advantage = req.advantage
        
        # Step 1: Attack roll
        attack_roll = self._call_roll_dice(
            dice_type=DiceType.D20,
            reason=f"Attack roll against {target.name}",
            advantage=advantage,
            modifier=modifier + prof,
        )
        
        total_attack = attack_roll.total
        target_ac = target.ac
        outcome = Outcome.SUCCESS if total_attack >= target_ac else Outcome.FAILURE
        
        # Build attack detail (will be updated with damage if hit)
        attack_detail = AttackDetail(
            target=target.id,
            weapon=weapon,
            hit_roll=attack_roll.roll,
            total_attack=total_attack,
            target_ac=target_ac,
            damage=None,
        )
        
        damage_detail: Optional[DamageDetail] = None
        
        # Step 2: If hit, roll damage and apply
        if outcome == Outcome.SUCCESS:
            damage_result = self._call_roll_dice(
                dice_type=DiceType.DAMAGE,
                reason=f"Damage with {weapon}",
                dice_expression=damage_dice,
            )
            
            damage_total = damage_result.total
            damage_detail = DamageDetail(
                dice_expression=damage_dice,
                rolls=damage_result.rolls,
                total=damage_total,
            )
            attack_detail.damage = damage_detail
            
            # Apply damage to target
            self._call_apply_state_change(
                target=target.id,
                field="hp",
                delta=-damage_total,
                description=f"{actor.name} hits {target.name} with {weapon} for {damage_total} damage.",
            )
            
            # Check for defeat
            new_hp = max(0, target.hp - damage_total)
            if new_hp == 0:
                self._call_apply_state_change(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} has been defeated!",
                )
        
        # Step 3: Advance time
        scene = get_scene()
        self._call_apply_state_change(
            target=scene.id,
            field="time",
            delta=1,
            description="Combat time passes.",
        )
        
        # Step 4: Generate narrative
        attack_result = {
            "weapon": weapon,
            "target": target.name,
            "damage": damage_detail.model_dump() if damage_detail else None,
        }
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=outcome,
            attack_result=attack_result,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            outcome=outcome,
            narration_result=narrative_result,
            attack_result=attack_result,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=attack_detail,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
        )
    
    def _resolve_attack_no_target(
        self,
        req: ActionRequest,
        actor: Actor,
        target_id: str,
    ) -> ActionResponse:
        """Resolve an attack when target is not found."""
        action_summary = f"{req.actor} attacks {target_id} with {req.weapon or 'weapon'}"
        
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=Outcome.FAILURE,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=None,
            outcome=Outcome.FAILURE,
            effects=self.effects,
            narration=f"{action_summary} — but the target cannot be found.",
            scene_progression="The confusion stalls the moment. You can pick a clear target, read the room for reactions, or reposition before the next move.",
        )
    
    def _resolve_spell_attack(self, req: ActionRequest, actor: Actor) -> ActionResponse:
        """Resolve a spell attack with attack roll + target saving throw.
        
        This demonstrates multi-step GM Agent orchestration:
        1. Attack roll (spell attack)
        2. If hit, target makes saving throw
        3. Damage depends on saving throw outcome (full/half)
        4. Apply all state changes
        5. Generate narrative
        """
        target_id = req.target or "goblin-01"
        target = get_actor_by_id_or_name(target_id)
        
        if target is None:
            return self._resolve_attack_no_target(req, actor, target_id)
        
        action_summary = f"{actor.name} casts {req.intent} at {target.name}"
        
        # Spell parameters
        damage_dice = req.damage_dice or "2d6"  # Default spell damage
        spell_dc = req.saving_throw_dc or 13  # Default spell DC
        save_ability = req.saving_throw_ability or "dex"  # Default DEX save
        
        # Step 1: Spell attack roll (using caster's spell attack modifier)
        # For simplicity, use INT + proficiency
        spell_attack_mod = actor.abilities.modifier("int") + actor.proficiency_bonus
        attack_roll = self._call_roll_dice(
            dice_type=DiceType.D20,
            reason=f"Spell attack roll against {target.name}",
            advantage=req.advantage,
            modifier=spell_attack_mod,
        )
        
        total_attack = attack_roll.total
        target_ac = target.ac
        hit = total_attack >= target_ac
        
        # Build attack detail
        attack_detail = AttackDetail(
            target=target.id,
            weapon="spell",
            hit_roll=attack_roll.roll,
            total_attack=total_attack,
            target_ac=target_ac,
            damage=None,
        )
        
        saving_throw_detail: Optional[SavingThrowDetail] = None
        damage_detail: Optional[DamageDetail] = None
        outcome = Outcome.FAILURE
        
        # Step 2: If spell hits, target makes saving throw
        if hit:
            save_modifier = target.abilities.modifier(save_ability)
            save_roll = self._call_roll_dice(
                dice_type=DiceType.D20,
                reason=f"{save_ability.upper()} saving throw for {target.name}",
                modifier=save_modifier,
            )
            
            total_save = save_roll.total
            save_success = total_save >= spell_dc
            save_outcome = Outcome.SUCCESS if save_success else Outcome.FAILURE
            
            saving_throw_detail = SavingThrowDetail(
                target=target.id,
                ability=save_ability,
                dc=spell_dc,
                roll=save_roll.roll,
                modifier=save_modifier,
                total=total_save,
                outcome=save_outcome,
            )
            
            # Step 3: Roll damage
            damage_result = self._call_roll_dice(
                dice_type=DiceType.DAMAGE,
                reason="Spell damage",
                dice_expression=damage_dice,
            )
            
            # Damage: full on failed save, half on successful save
            damage_total = damage_result.total // 2 if save_success else damage_result.total
            damage_detail = DamageDetail(
                dice_expression=damage_dice,
                rolls=damage_result.rolls,
                total=damage_total,
            )
            attack_detail.damage = damage_detail
            
            # Step 4: Apply damage
            self._call_apply_state_change(
                target=target.id,
                field="hp",
                delta=-damage_total,
                description=(
                    f"{actor.name}'s spell hits {target.name} for {damage_total} damage "
                    f"({'half damage - save successful' if save_success else 'full damage'})."
                ),
            )
            
            # Check for defeat
            new_hp = max(0, target.hp - damage_total)
            if new_hp == 0:
                self._call_apply_state_change(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} has been defeated!",
                )
            
            # Overall outcome is success if spell hit
            outcome = Outcome.SUCCESS
        
        # Step 5: Advance time
        scene = get_scene()
        self._call_apply_state_change(
            target=scene.id,
            field="time",
            delta=1,
            description="Combat time passes.",
        )
        
        # Step 6: Generate narrative
        attack_result = {
            "weapon": "spell",
            "target": target.name,
            "damage": damage_detail.model_dump() if damage_detail else None,
            "saving_throw": saving_throw_detail.model_dump() if saving_throw_detail else None,
        }
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=outcome,
            attack_result=attack_result,
            saving_throw_result=saving_throw_detail.model_dump() if saving_throw_detail else None,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            outcome=outcome,
            narration_result=narrative_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_detail.model_dump() if saving_throw_detail else None,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=attack_detail,
            saving_throw=saving_throw_detail,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
        )
    
    # -----------------------------------------------------------------------
    # Helper Methods
    # -----------------------------------------------------------------------
    
    def _apply_check_effects(
        self,
        actor: Actor,
        ability: str,
        outcome: Outcome,
    ) -> None:
        """Apply effects based on check outcome."""
        scene = get_scene()
        
        # Always advance time
        self._call_apply_state_change(
            target=scene.id,
            field="time",
            delta=1,
            description="Time passes.",
        )
        
        # Apply failure effects for physical abilities
        if outcome == Outcome.FAILURE:
            physical_abilities = {"str", "dex", "con"}
            if ability in physical_abilities:
                self._call_apply_state_change(
                    target=actor.id,
                    field="hp",
                    delta=-1,
                    description="The failed physical effort causes minor harm.",
                )
            else:
                self._call_apply_state_change(
                    target=actor.id,
                    field="narrative_state",
                    delta="setback",
                    description="The failed attempt may attract attention or waste time.",
                )
    
    @staticmethod
    def _is_auto_success(intent: str, approach: str) -> bool:
        """Check if action should auto-succeed (trivial actions only)."""
        trivial_phrases = [
            "look around", "look at", "walk to", "walk over",
            "sit down", "stand up", "put down", "pick up",
        ]
        disqualifiers = [
            "locked", "trapped", "guard", "convince", "persuade",
            "deceive", "lie", "trick", "sneak", "steal", "force",
            "break", "dangerous", "difficult", "careful", "secret", "hidden",
        ]
        
        lower = f"{intent} {approach}".lower()
        has_trivial = any(p in lower for p in trivial_phrases)
        has_disqualifier = any(d in lower for d in disqualifiers)
        return has_trivial and not has_disqualifier
    
    @staticmethod
    def _infer_ability(approach: str) -> str:
        """Infer ability from approach description."""
        hints = {
            "str": ["push", "lift", "force", "break", "climb", "grapple", "shove"],
            "dex": ["dodge", "sneak", "hide", "pick", "steal", "acrobat", "tumble"],
            "con": ["endure", "resist", "hold breath", "withstand", "tough"],
            "int": ["recall", "investigate", "analyze", "decipher", "study", "know"],
            "wis": ["perceive", "sense", "insight", "track", "notice", "spot", "listen"],
            "cha": ["persuade", "deceive", "intimidate", "perform", "charm", "bluff"],
        }
        
        lower = approach.lower()
        for ability, keywords in hints.items():
            for kw in keywords:
                if kw in lower:
                    return ability
        return "str"
    
    @staticmethod
    def _pick_dc(intent: str) -> int:
        """Pick difficulty class based on intent."""
        lower = intent.lower()
        if any(w in lower for w in ["hard", "difficult", "dangerous", "impossible"]):
            return DC_HARD
        if any(w in lower for w in ["careful", "tricky", "complex"]):
            return DC_MEDIUM
        return DC_MEDIUM
    
    @staticmethod
    def _infer_attack_ability(weapon: str) -> str:
        """Infer ability for attack based on weapon type."""
        finesse_weapons = {"dagger", "rapier", "scimitar", "shortsword"}
        ranged_weapons = {"shortbow", "longbow", "light_crossbow", "heavy_crossbow"}
        
        weapon_lower = weapon.lower()
        if weapon_lower in finesse_weapons or weapon_lower in ranged_weapons:
            return "dex"
        return "str"
    
    @staticmethod
    def _get_weapon_damage(weapon: str) -> str:
        """Get damage dice for weapon."""
        damage_map = {
            "dagger": "1d4",
            "shortsword": "1d6",
            "longsword": "1d8",
            "greatsword": "2d6",
            "battleaxe": "1d8",
            "greataxe": "1d12",
            "club": "1d4",
            "mace": "1d6",
            "spear": "1d6",
            "halberd": "1d10",
            "rapier": "1d8",
            "scimitar": "1d6",
            "quarterstaff": "1d6",
            "handaxe": "1d6",
            "light_crossbow": "1d8",
            "shortbow": "1d6",
            "longbow": "1d8",
            "heavy_crossbow": "1d10",
        }
        return damage_map.get(weapon.lower(), "1d6")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_action_with_agent(req: ActionRequest) -> ActionResponse:
    """Resolve an action using the GM Agent orchestrator.
    
    This is the main entry point for agent-driven action resolution.
    
    Args:
        req: Player action request
        
    Returns:
        Complete action response with narrative
    """
    agent = GMAgent()
    return agent.resolve(req)
