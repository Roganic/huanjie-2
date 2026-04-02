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

import time
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
    SkillCheckDetail,
)
from ..models.state import Actor, NarrativeHistoryEntry
from ..npc import find_target_npc, is_npc_interaction
from ..state import (
    append_narrative_history,
    end_combat_session,
    get_actor,
    get_actor_by_id_or_name,
    get_combat_state,
    get_narrative_context,
    get_scene,
    start_combat_session,
    update_combatant_hp,
)
from .narrator import generate_narration
from ..npc.dialogue_operations import (
    is_npc_dialogue_action,
    identify_target_npc,
    record_dialogue_from_action,
)
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
        
        if req.action_type == ActionType.SKILL_CHECK or req.skill is not None:
            return self._resolve_skill_check(req, actor)
        
        # Check for equipment actions before generic action resolution
        from ..action_handler import handle_equipment_action
        equipment_response = handle_equipment_action(req, actor)
        if equipment_response is not None:
            return equipment_response
        
        # Check for NPC interaction before generic action resolution
        scene = get_scene()
        if is_npc_interaction(req.intent, req.approach):
            target_npc = find_target_npc(req.intent, req.approach, scene.npcs)
            if target_npc is not None:
                return self._resolve_npc_interaction(req, actor, target_npc)
        
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
        combat_round: Optional[int] = None,
        is_combat_ended: Optional[bool] = None,
        combat_outcome: Optional[str] = None,
        npc_target: Optional[Any] = None,
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
            combat_round=combat_round,
            is_combat_ended=is_combat_ended,
            combat_outcome=combat_outcome,
            npc_target=npc_target,
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
            narration_result.gm_prompt.strip(),
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
                narration=narration_result.narrative,
                scene_progression=narration_result.scene_progression,
                gm_prompt=narration_result.gm_prompt,
                created_at=int(time.time() * 1000),
            )
        )
    
    def _maybe_record_npc_dialogue(
        self,
        req: ActionRequest,
        narration_result: NarrativeResult,
    ) -> None:
        """Record NPC dialogue if this was a dialogue action.
        
        This method checks if the action involved talking to an NPC and,
        if so, records the dialogue to the NPC's dialogue state.
        """
        if is_npc_dialogue_action(req):
            npc_info = identify_target_npc(req)
            if npc_info:
                npc_id, npc_name = npc_info
                # Record player message
                player_message = f"{req.intent} (方式: {req.approach})"
                from ..state import record_npc_dialogue
                record_npc_dialogue(npc_id, npc_name, "player", player_message)
                
                # Record NPC response (truncated)
                npc_response = narration_result.narrative[:300]
                record_npc_dialogue(npc_id, npc_name, npc_name, npc_response)
    
    # -----------------------------------------------------------------------
    # Resolution Paths
    # -----------------------------------------------------------------------
    
    def _resolve_skill_check(
        self,
        req: ActionRequest,
        actor: Actor,
    ) -> ActionResponse:
        """Resolve a skill check action (proficiency-based).
        
        Skill checks add proficiency bonus only if the character is proficient
        in that specific skill.
        """
        skill_name = req.skill or "athletics"
        action_summary = f"{req.actor} uses {skill_name} to {req.intent}"
        
        # Determine governing ability
        skill_abilities = {
            "athletics": "str",
            "acrobatics": "dex", "sleight_of_hand": "dex", "stealth": "dex",
            "arcana": "int", "history": "int", "investigation": "int",
            "nature": "int", "religion": "int",
            "animal_handling": "wis", "insight": "wis", "medicine": "wis",
            "perception": "wis", "survival": "wis",
            "deception": "cha", "intimidation": "cha", "performance": "cha",
            "persuasion": "cha",
        }
        ability = req.ability or skill_abilities.get(skill_name.lower(), "str")
        
        # Calculate modifiers
        ability_modifier = actor.abilities.modifier(ability)
        
        # Check proficiency
        is_proficient = False
        for skill in actor.skills:
            if skill.name.lower() == skill_name.lower():
                is_proficient = skill.proficient
                break
        
        prof_bonus = actor.proficiency_bonus if is_proficient else 0
        
        dc = req.dc or self._pick_dc(req.intent)
        advantage = req.advantage
        
        # Roll d20 + ability modifier + proficiency (if proficient)
        roll_result = self._call_roll_dice(
            dice_type=DiceType.D20,
            reason=f"{skill_name} check ({ability.upper()})",
            advantage=advantage,
            modifier=ability_modifier + prof_bonus,
        )
        
        total = roll_result.total
        outcome = Outcome.SUCCESS if total >= dc else Outcome.FAILURE
        
        # Build check detail
        check = CheckDetail(
            ability=ability,
            modifier=ability_modifier,
            proficiency_bonus=prof_bonus,
            advantage=advantage,
            roll=roll_result.roll,
            total=total,
            dc=dc,
            skill_name=skill_name,
        )
        
        # Apply effects
        self._apply_check_effects(actor, ability, outcome)
        
        # Generate narrative
        check_result = {
            "ability": ability,
            "skill": skill_name,
            "proficient": is_proficient,
            "modifier": ability_modifier,
            "proficiency_bonus": prof_bonus,
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
        self._maybe_record_npc_dialogue(req, narrative_result)
        
        # Build skill_check detail for frontend display
        skill_check = SkillCheckDetail(
            skill=skill_name,
            roll=roll_result.roll,
            modifier=ability_modifier + prof_bonus,
            total=total,
            dc=dc,
            success=outcome == Outcome.SUCCESS,
        )
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=check,
            skill_check=skill_check,
            attack=None,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
            gm_prompt=narrative_result.gm_prompt,
        )

    def _resolve_generic_action(self, req: ActionRequest, actor: Actor) -> ActionResponse:
        """Resolve a generic (non-attack) action."""
        action_summary = f"{req.actor} attempts to {req.intent} by {req.approach}"
        
        # Check for auto-success
        if self._is_auto_success(req.intent, req.approach):
            return self._resolve_auto_success(req, actor, action_summary)
        
        # Resolve as ability check
        return self._resolve_ability_check(req, actor, action_summary)
    
    def _resolve_npc_interaction(
        self,
        req: ActionRequest,
        actor: Actor,
        target_npc: Any,
    ) -> ActionResponse:
        """Resolve an NPC interaction action.
        
        NPC interactions follow a dedicated narrative path:
        - No combat is triggered
        - No character stats are modified
        - The narrative is generated with the target NPC's identity in context
        - The result is recorded in narrative history
        """
        action_summary = f"{req.actor} interacts with {target_npc.name}: {req.intent}"
        
        # Generate narrative with NPC target context
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=Outcome.SUCCESS,
            npc_target=target_npc,
        )
        
        # Record to narrative history (no state effects for NPC interactions)
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
            effects=[],  # NPC interactions do not modify character stats
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
            gm_prompt=narrative_result.gm_prompt,
        )
    
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
        self._maybe_record_npc_dialogue(req, narrative_result)
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            check=None,
            attack=None,
            outcome=Outcome.SUCCESS,
            effects=[],  # No effects for auto-success
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
            gm_prompt=narrative_result.gm_prompt,
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
        prof = actor.proficiency_bonus  # Generic checks add full prof for simplicity
        dc = req.dc or self._pick_dc(req.intent)
        advantage = req.advantage
        
        # Step 1: Roll d20 + ability modifier + proficiency
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
        self._maybe_record_npc_dialogue(req, narrative_result)
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=check,
            attack=None,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
            gm_prompt=narrative_result.gm_prompt,
        )
    
    def _resolve_attack(self, req: ActionRequest, actor: Actor) -> ActionResponse:
        """Resolve an attack action (potentially multi-step)."""
        # Get target
        target_id = req.target or "goblin-01"
        target = get_actor_by_id_or_name(target_id)
        
        if target is None:
            return self._resolve_attack_no_target(req, actor, target_id)
        
        # Ensure combat is active
        combat_state = get_combat_state()
        if not combat_state.is_active:
            start_combat_session()
            combat_state = get_combat_state()
        
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
        hit = outcome == Outcome.SUCCESS
        
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
        is_combat_ended = False
        combat_outcome: Optional[str] = None
        
        # Step 2: If hit, roll damage and apply
        if hit:
            damage_result = self._call_roll_dice(
                dice_type=DiceType.DAMAGE,
                reason=f"Damage with {weapon}",
                dice_expression=damage_dice,
            )
            
            # Damage = weapon dice + ability modifier (min 1 damage on hit)
            damage_modifier = modifier  # Same ability used for attack roll
            damage_total = max(1, damage_result.total + damage_modifier)
            damage_detail = DamageDetail(
                dice_expression=damage_dice,
                rolls=damage_result.rolls,
                modifier=damage_modifier,
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
            
            # Refresh target to get updated HP
            target = get_actor_by_id_or_name(target_id) or target
            update_combatant_hp(target.id, target.hp)
            
            # Check for defeat
            if target.hp == 0:
                self._call_apply_state_change(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} has been defeated!",
                )
                is_combat_ended = True
                combat_outcome = "victory"
                end_combat_session("victory")
        
        # Update attacker HP in combat state
        update_combatant_hp(actor.id, actor.hp)
        
        # Step 3: Advance time
        scene = get_scene()
        self._call_apply_state_change(
            target=scene.id,
            field="time",
            delta=1,
            description="战斗时间流逝。",
        )
        
        # Step 4: Generate narrative with combat context
        attack_result = {
            "weapon": weapon,
            "target": target.name,
            "hit": hit,
            "damage": damage_detail.model_dump() if damage_detail else None,
        }
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=outcome,
            attack_result=attack_result,
            combat_round=combat_state.round_number,
            is_combat_ended=is_combat_ended,
            combat_outcome=combat_outcome,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            outcome=outcome,
            narration_result=narrative_result,
            attack_result=attack_result,
        )
        
        # Advance combat round for next action
        from ..state import advance_combat_round
        if not is_combat_ended:
            advance_combat_round()
        
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            check=None,
            attack=attack_detail,
            outcome=outcome,
            effects=self.effects,
            narration=narrative_result.narrative,
            scene_progression=narrative_result.scene_progression,
            gm_prompt=narrative_result.gm_prompt,
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
            scene_progression="局面陷入混乱，时机短暂停滞。你可以选定明确目标、观察周围反应，或趁机重新布位。",
            gm_prompt="不确定感弥漫在空气中。在局势对你不利之前，先确认你真正要对付的目标。",
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
        
        # Ensure combat is active
        combat_state = get_combat_state()
        if not combat_state.is_active:
            start_combat_session()
            combat_state = get_combat_state()
        
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
        is_combat_ended = False
        combat_outcome: Optional[str] = None
        
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
            
            # Refresh target to get updated HP
            target = get_actor_by_id_or_name(target_id) or target
            update_combatant_hp(target.id, target.hp)
            
            # Check for defeat
            if target.hp == 0:
                self._call_apply_state_change(
                    target=target.id,
                    field="conditions_add",
                    delta="defeated",
                    description=f"{target.name} has been defeated!",
                )
                is_combat_ended = True
                combat_outcome = "victory"
                end_combat_session("victory")
            
            # Overall outcome is success if spell hit
            outcome = Outcome.SUCCESS
        
        # Update attacker HP in combat state
        update_combatant_hp(actor.id, actor.hp)
        
        # Step 5: Advance time
        scene = get_scene()
        self._call_apply_state_change(
            target=scene.id,
            field="time",
            delta=1,
            description="战斗时间流逝。",
        )
        
        # Step 6: Generate narrative with combat context
        attack_result = {
            "weapon": "spell",
            "target": target.name,
            "hit": hit,
            "damage": damage_detail.model_dump() if damage_detail else None,
            "saving_throw": saving_throw_detail.model_dump() if saving_throw_detail else None,
        }
        narrative_result = self._call_generate_narrative(
            req=req,
            outcome=outcome,
            attack_result=attack_result,
            saving_throw_result=saving_throw_detail.model_dump() if saving_throw_detail else None,
            combat_round=combat_state.round_number,
            is_combat_ended=is_combat_ended,
            combat_outcome=combat_outcome,
        )
        self._record_narrative_history(
            action_summary=action_summary,
            resolution_type=ResolutionType.CHECK,
            outcome=outcome,
            narration_result=narrative_result,
            attack_result=attack_result,
            saving_throw_result=saving_throw_detail.model_dump() if saving_throw_detail else None,
        )
        
        # Advance combat round for next action
        from ..state import advance_combat_round
        if not is_combat_ended:
            advance_combat_round()
        
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
            gm_prompt=narrative_result.gm_prompt,
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
            description="时间流逝。",
        )
        
        # Apply failure effects for physical abilities
        if outcome == Outcome.FAILURE:
            physical_abilities = {"str", "dex", "con"}
            if ability in physical_abilities:
                self._call_apply_state_change(
                    target=actor.id,
                    field="hp",
                    delta=-1,
                    description="体力消耗造成轻微伤害。",
                )
            else:
                self._call_apply_state_change(
                    target=actor.id,
                    field="narrative_state",
                    delta="setback",
                    description="失败的尝试可能引起注意或浪费时间。",
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
