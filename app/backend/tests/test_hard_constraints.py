"""Tests for hard constraint injection in AI narrative prompts.

These tests verify that:
1. Rule engine results (success/failure, damage, state changes) are properly injected
2. Hard constraints are clearly separated from narrative space in prompts
3. Failed actions are never narrated as successful
4. AI cannot override numeric values (HP, damage, etc.) in narrative
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.narrator import (
    _build_hard_constraints,
    _build_narrative_prompt,
    _narration_respects_constraints,
    generate_narration,
    NarrationBundle,
)
from src.agent.resolution_constraints import (
    NarrationConstraintContext,
    ValidationResult,
    detect_unauthorized_numeric_declarations,
    validate_narrative_for_overreach,
)
from src.models.action import ActionRequest, ActionType, Effect, Outcome
from src.models.state import AbilityScores, Actor, NarrativeHistoryEntry, Scene
from src.main import app
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()


@pytest.fixture
def sample_actor():
    return Actor(
        id="hero-01",
        name="Aldric",
        abilities=AbilityScores(str=16, dex=12, con=13, int=10, wis=12, cha=8),
        proficiency_bonus=2,
        hp=12,
        hp_max=12,
        ac=14,
        description="A sturdy sellsword.",
    )


@pytest.fixture
def sample_target():
    return Actor(
        id="goblin-01",
        name="Goblin Scout",
        abilities=AbilityScores(str=8, dex=14, con=10, int=10, wis=8, cha=8),
        proficiency_bonus=2,
        hp=7,
        hp_max=7,
        ac=12,
        description="A wiry goblin.",
    )


@pytest.fixture
def sample_scene():
    return Scene(
        id="dungeon-01",
        name="Dark Cave",
        description="A damp cave with dripping water.",
        actors=["hero-01"],
    )


# -----------------------------------------------------------------------------
# Unit tests for _build_hard_constraints
# -----------------------------------------------------------------------------

class TestBuildHardConstraints:
    """Test the hard constraint building function."""

    def test_success_outcome_constraint(self):
        """Hard constraints should include success outcome."""
        constraints = _build_hard_constraints(outcome=Outcome.SUCCESS)
        
        assert any("成功" in c and "success" in c for c in constraints)
        assert any("Outcome" in c for c in constraints)

    def test_failure_outcome_constraint(self):
        """Hard constraints should include failure outcome."""
        constraints = _build_hard_constraints(outcome=Outcome.FAILURE)
        
        assert any("失败" in c and "failure" in c for c in constraints)
        assert any("Outcome" in c for c in constraints)

    def test_check_details_in_constraints(self):
        """Hard constraints should include check details with specific numbers."""
        check_result = {
            "ability": "dex",
            "roll": 15,
            "modifier": 2,
            "total": 17,
            "dc": 15,
        }
        constraints = _build_hard_constraints(
            outcome=Outcome.SUCCESS,
            check_result=check_result,
        )
        
        # Should include ability, roll, modifier, total, and DC
        constraint_text = "\n".join(constraints)
        assert "DEX" in constraint_text
        assert "掷骰=15" in constraint_text
        assert "调整值=2" in constraint_text
        assert "总计=17" in constraint_text
        assert "DC=15" in constraint_text

    def test_attack_hit_constraints(self, sample_target):
        """Hard constraints for successful attack should include damage."""
        attack_result = {
            "weapon": "longsword",
            "target": "Goblin Scout",
            "damage": {"total": 8, "rolls": [6, 2], "dice_expression": "1d8+1"},
        }
        constraints = _build_hard_constraints(
            outcome=Outcome.SUCCESS,
            attack_result=attack_result,
            target=sample_target,
        )
        
        constraint_text = "\n".join(constraints)
        # Should indicate hit
        assert "命中" in constraint_text or "HIT" in constraint_text
        # Should include exact damage number
        assert "伤害数值" in constraint_text
        assert "8" in constraint_text
        # Should show HP change
        assert "HP" in constraint_text
        assert "7" in constraint_text  # Original HP
        assert "0" in constraint_text  # New HP (7 - 8 = 0, clamped)

    def test_attack_miss_constraints(self, sample_target):
        """Hard constraints for failed attack should indicate miss and zero damage."""
        attack_result = {
            "weapon": "longsword",
            "target": "Goblin Scout",
            "damage": None,
        }
        constraints = _build_hard_constraints(
            outcome=Outcome.FAILURE,
            attack_result=attack_result,
            target=sample_target,
        )
        
        constraint_text = "\n".join(constraints)
        # Should indicate miss
        assert "未命中" in constraint_text or "MISS" in constraint_text
        # Should indicate zero damage
        assert "0" in constraint_text or "无伤害" in constraint_text

    def test_hp_effect_constraints(self):
        """Hard constraints should include HP change effects."""
        effects = [
            Effect(target="hero-01", field="hp", delta=-5, description="Takes 5 damage"),
        ]
        constraints = _build_hard_constraints(
            outcome=Outcome.FAILURE,
            effects=effects,
        )
        
        constraint_text = "\n".join(constraints)
        assert "HP" in constraint_text
        assert "-5" in constraint_text

    def test_condition_effect_constraints(self):
        """Hard constraints should include condition changes."""
        effects = [
            Effect(target="hero-01", field="conditions_add", delta="poisoned", description="Poisoned"),
        ]
        constraints = _build_hard_constraints(
            outcome=Outcome.FAILURE,
            effects=effects,
        )
        
        constraint_text = "\n".join(constraints)
        assert "poisoned" in constraint_text
        assert "获得状态" in constraint_text


# -----------------------------------------------------------------------------
# Unit tests for _build_narrative_prompt structure
# -----------------------------------------------------------------------------

class TestBuildNarrativePrompt:
    """Test the complete prompt building with hard constraint section."""

    def test_prompt_has_hard_constraint_section(self, sample_actor, sample_scene):
        """Prompt should have a clearly marked hard constraint section."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="pick the lock",
            approach="use thieves tools",
        )
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
        )
        
        # Should have hard constraint section marker
        assert "【硬约束区" in prompt or "HARD CONSTRAINTS" in prompt
        # Should have narrative space section marker
        assert "【叙事空间" in prompt or "NARRATIVE SPACE" in prompt

    def test_prompt_separates_constraints_from_narrative_space(self, sample_actor, sample_scene):
        """Hard constraints and narrative space should be clearly separated."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack",
            approach="swing sword",
            action_type=ActionType.ATTACK,
        )
        
        check_result = {"ability": "str", "roll": 18, "modifier": 3, "total": 21, "dc": 15}
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
            check_result=check_result,
        )
        
        # Find the hard constraint section
        hard_constraint_start = prompt.find("【硬约束区")
        narrative_space_start = prompt.find("【叙事空间")
        
        # Both sections should exist
        assert hard_constraint_start != -1
        assert narrative_space_start != -1
        
        # Narrative space should come after hard constraints
        assert narrative_space_start > hard_constraint_start

    def test_prompt_includes_outcome_in_hard_constraints(self, sample_actor, sample_scene):
        """The outcome should be clearly stated in hard constraints."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="climb wall",
            approach="scale quickly",
        )
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.FAILURE,
        )
        
        # Should have failure in hard constraints section
        hard_section = prompt.split("【叙事空间")[0]
        assert "失败" in hard_section or "failure" in hard_section

    def test_prompt_includes_writing_instruction(self, sample_actor, sample_scene):
        """Prompt should include instructions about respecting hard constraints."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="do something",
            approach="carefully",
        )
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
        )
        
        # Should have writing instruction section
        assert "写作指示" in prompt or "WRITING INSTRUCTION" in prompt
        # Should mention hard constraints
        assert "硬约束" in prompt

    def test_prompt_includes_character_fields(self, sample_actor, sample_scene):
        """Prompt should include required character fields: name, class, HP, AC."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing sword",
        )
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
        )
        
        # Check for character name
        assert "Aldric" in prompt
        # Check for HP
        assert "HP 12/12" in prompt or "HP 12" in prompt
        # Check for AC
        assert "AC 14" in prompt

    def test_prompt_includes_resolution_result_structure(self, sample_actor, sample_scene, sample_target):
        """Prompt should include the resolution result in structured format."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing sword",
            action_type=ActionType.ATTACK,
        )
        
        attack_result = {
            "weapon": "longsword",
            "target": "Goblin Scout",
            "damage": {"total": 5, "rolls": [4, 1], "dice_expression": "1d8+1"},
        }
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
            attack_result=attack_result,
            target=sample_target,
        )
        
        # Check for resolution result structure
        hard_section = prompt.split("【叙事空间")[0]
        assert "裁定结果" in hard_section or "Outcome" in hard_section
        assert "命中" in hard_section or "HIT" in hard_section
        assert "伤害数值" in hard_section
        assert "5" in hard_section

    def test_prompt_includes_session_narrative_history(self, sample_actor, sample_scene):
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="search the altar",
            approach="brush dust away and inspect the carvings",
        )

        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
            narrative_history=[
                NarrativeHistoryEntry(
                    action_summary="Aldric questioned the ferryman",
                    resolution_summary={"outcome": "success", "resolution_type": "check"},
                    narration_summary="The ferryman revealed that the cave once housed a shrine.",
                )
            ],
        )

        assert "Session Narrative History" in prompt
        assert "Aldric questioned the ferryman" in prompt
        assert "The ferryman revealed" in prompt


# -----------------------------------------------------------------------------
# Unit tests for post-processing validation
# -----------------------------------------------------------------------------

class TestDetectUnauthorizedNumericDeclarations:
    """Test detection of unauthorized numeric declarations in narrative."""

    def test_detect_hp_change_declaration_chinese(self):
        """Should detect Chinese HP change patterns like 'HP变为'."""
        text = "你的攻击命中了哥布林，HP变为10。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0
        violation_types = [v["type"] for v in violations]
        assert any("hp" in vt.lower() or "unauthorized" in vt.lower() for vt in violation_types)

    def test_detect_hp_change_declaration_english(self):
        """Should detect English HP change patterns like 'HP becomes'."""
        text = "The goblin is wounded and HP becomes 5."
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0

    def test_detect_resource_gain_patterns(self):
        """Should detect resource gain patterns like '你获得'."""
        text = "你成功治愈了伤口，你获得10点HP。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0

    def test_detect_resource_loss_patterns(self):
        """Should detect resource loss patterns like '你失去'."""
        text = "哥布林的攻击命中，你失去5点生命。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0

    def test_detect_damage_announcement(self):
        """Should detect direct damage announcements with numbers."""
        text = "你的长剑造成8点伤害。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0

    def test_detect_healing_announcement(self):
        """Should detect direct healing announcements with numbers."""
        text = "治疗药水恢复5点HP。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        assert len(violations) > 0

    def test_no_false_positives_on_descriptive_text(self):
        """Should not flag descriptive text without numeric declarations."""
        text = "你的剑锋划过空气，带着呼啸声劈向敌人。哥布林惊恐地后退，勉强举起武器格挡。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        # This should either have no violations or only unrelated ones
        hp_violations = [v for v in violations if "hp" in v.get("type", "").lower()]
        assert len(hp_violations) == 0

    def test_detect_hp_remaining_patterns(self):
        """Should detect patterns like '现在有X点HP'."""
        text = "受到攻击后，哥布林现在有5点HP。"
        violations = detect_unauthorized_numeric_declarations(text)
        
        # This pattern should be detected by the regex
        assert len(violations) > 0


class TestValidateNarrativeForOverreach:
    """Test comprehensive narrative validation."""

    def test_valid_narrative_passes(self):
        """Valid narrative without numeric overreach should pass."""
        context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
        
        result = validate_narrative_for_overreach(
            action_result="你的剑锋凌厉地斩向哥布林，在月光下划出一道银光。",
            scene_progression="敌人踉跄后退，显然被你的气势所震慑。",
            gm_prompt="你要乘胜追击，还是观察敌人的下一步动作？",
            context=context,
        )
        
        assert result.is_valid
        assert len(result.violations) == 0
        assert result.marked_narrative is None

    def test_invalid_narrative_fails_with_hp_change(self):
        """Narrative with unauthorized HP change should fail."""
        context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
        
        result = validate_narrative_for_overreach(
            action_result="你的攻击命中，哥布林的HP变为3。",
            scene_progression="敌人痛苦地嚎叫。",
            gm_prompt="你继续攻击吗？",
            context=context,
        )
        
        assert not result.is_valid
        assert len(result.violations) > 0
        assert result.marked_narrative is not None
        assert "VALIDATION WARNING" in result.marked_narrative

    def test_invalid_narrative_fails_with_damage_number(self):
        """Narrative with direct damage announcement should fail."""
        context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
        
        result = validate_narrative_for_overreach(
            action_result="你造成了8点伤害，将敌人击退。",
            scene_progression="战场上一片混乱。",
            gm_prompt="下一步行动？",
            context=context,
        )
        
        assert not result.is_valid
        assert len(result.violations) > 0

    def test_failure_outcome_contradiction_detected(self):
        """Should detect when failure is narrated as hit."""
        context = NarrationConstraintContext(
            outcome=Outcome.FAILURE,
            attack_result={"weapon": "sword", "target": "goblin", "damage": None},
        )
        
        # Use English words that match the detection patterns
        result = validate_narrative_for_overreach(
            action_result="You hit the goblin and wound it badly.",
            scene_progression="The enemy staggers.",
            gm_prompt="Finish it?",
            context=context,
        )
        
        assert not result.is_valid
        assert any("failure" in v.lower() or "hit" in v.lower() for v in result.violations)

    def test_validation_logs_warnings(self, caplog):
        """Validation should log warnings for violations."""
        import logging
        
        context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
        
        with caplog.at_level(logging.WARNING):
            validate_narrative_for_overreach(
                action_result="你的攻击让敌人HP变为5。",
                scene_progression="敌人显得虚弱。",
                gm_prompt="继续攻击？",
                context=context,
            )
        
        assert "validation" in caplog.text.lower() or "violation" in caplog.text.lower()


class TestNarrationConstraintValidation:
    """Test the lightweight post-generation contradiction checks."""

    def test_failed_attack_hit_language_rejected(self, sample_target):
        narration = NarrationBundle(
            action_result="Aldric hits the goblin and wounds it badly.",
            scene_progression="The goblin staggers back.",
            gm_prompt="What do you do next?",
        )

        assert not _narration_respects_constraints(
            narration=narration,
            outcome=Outcome.FAILURE,
            attack_result={"weapon": "longsword", "target": "Goblin Scout", "damage": None},
            target=sample_target,
        )

    def test_nonlethal_damage_cannot_describe_target_as_defeated(self, sample_target):
        narration = NarrationBundle(
            action_result="Aldric hits the goblin, leaving it defeated on the cave floor.",
            scene_progression="Its allies freeze for a moment.",
            gm_prompt="Press the attack?",
        )

        assert not _narration_respects_constraints(
            narration=narration,
            outcome=Outcome.SUCCESS,
            attack_result={
                "weapon": "longsword",
                "target": "Goblin Scout",
                "damage": {"total": 3, "rolls": [2, 1], "dice_expression": "1d8"},
            },
            target=sample_target,
        )

    def test_consistent_successful_hit_is_allowed(self, sample_target):
        narration = NarrationBundle(
            action_result="Aldric hits the goblin with a sharp slash across the shoulder.",
            scene_progression="The goblin stumbles back and raises its dagger in panic.",
            gm_prompt="Attack again?",
        )

        assert _narration_respects_constraints(
            narration=narration,
            outcome=Outcome.SUCCESS,
            attack_result={
                "weapon": "longsword",
                "target": "Goblin Scout",
                "damage": {"total": 3, "rolls": [2, 1], "dice_expression": "1d8"},
            },
            target=sample_target,
        )


# -----------------------------------------------------------------------------
# Integration tests for prompt injection
# -----------------------------------------------------------------------------

class TestPromptHardConstraintInjection:
    """Verify hard constraints are properly injected into prompts."""

    def test_damage_number_explicitly_in_hard_constraints(self, sample_actor, sample_target, sample_scene):
        """Exact damage number should appear in hard constraint section."""
        req = ActionRequest(
            scene_id="combat-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            action_type=ActionType.ATTACK,
            weapon="longsword",
            target="goblin-01",
        )
        
        attack_result = {
            "weapon": "longsword",
            "target": "Goblin Scout",
            "damage": {"total": 5, "rolls": [4, 1], "dice_expression": "1d8+1"},
        }
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
            attack_result=attack_result,
            target=sample_target,
        )
        
        # Extract hard constraint section
        hard_section = prompt.split("【叙事空间")[0]
        
        # Exact damage number should be there
        assert "5" in hard_section, "Exact damage number should be in hard constraints"
        assert "伤害数值" in hard_section, "Damage label should be in hard constraints"

    def test_miss_explicitly_states_zero_damage(self, sample_actor, sample_target, sample_scene):
        """Miss outcome should explicitly state zero damage in hard constraints."""
        req = ActionRequest(
            scene_id="combat-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            action_type=ActionType.ATTACK,
            weapon="longsword",
            target="goblin-01",
        )
        
        attack_result = {
            "weapon": "longsword",
            "target": "Goblin Scout",
            "damage": None,
        }
        
        prompt = _build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.FAILURE,
            attack_result=attack_result,
            target=sample_target,
        )
        
        # Extract hard constraint section
        hard_section = prompt.split("【叙事空间")[0]
        
        # Should indicate zero damage or miss
        assert ("0" in hard_section or "无伤害" in hard_section or 
                "未命中" in hard_section or "MISS" in hard_section), (
            "Miss should explicitly state zero damage or miss in hard constraints"
        )


# -----------------------------------------------------------------------------
# End-to-end tests for narrative consistency
# -----------------------------------------------------------------------------

@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestGenerateNarrationGuardrails:
    """Verify contradictory AI output is rejected before returning to callers."""

    def test_generate_narration_falls_back_when_ai_contradicts_failure(
        self,
        monkeypatch,
        sample_actor,
        sample_scene,
        sample_target,
    ):
        req = ActionRequest(
            scene_id="combat-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            action_type=ActionType.ATTACK,
            weapon="longsword",
            target="goblin-01",
        )

        async def fake_call(_prompt: str):
            return NarrationBundle(
                action_result="Aldric hits the goblin cleanly and drives it back.",
                scene_progression="The goblin reels from the successful strike.",
                gm_prompt="Press the attack?",
            )

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        monkeypatch.setattr("src.agent.narrator._call_kimi_api", fake_call)

        narration = generate_narration(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.FAILURE,
            attack_result={"weapon": "longsword", "target": "Goblin Scout", "damage": None},
            target=sample_target,
        )

        assert "miss" in narration.action_result.lower()
