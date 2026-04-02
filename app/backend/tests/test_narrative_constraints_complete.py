"""Complete tests for narrative constraint system.

These tests verify all three constraint categories:
1. Numeric Authority - AI cannot declare/modify numeric values
2. Plot Advancement - AI cannot force story progression  
3. Combat Results - AI cannot contradict combat outcomes

And verify that violating narratives trigger fallback to safe templates.
"""

import pytest
from unittest.mock import patch

from src.agent.narrator import generate_narration, NarrationBundle
from src.agent.resolution_constraints import (
    NarrationConstraintContext,
    ValidationResult,
    detect_unauthorized_numeric_declarations,
    detect_unauthorized_plot_advancement,
    detect_unauthorized_state_changes,
    validate_narrative_for_overreach,
)
from src.models.action import ActionRequest, ActionType, Outcome
from src.models.state import AbilityScores, Actor, Scene


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
# Category 1: Numeric Authority Violation Tests
# -----------------------------------------------------------------------------

class TestNumericAuthorityViolations:
    """Test detection of AI attempting to declare/modify numeric values."""

    def test_detect_chinese_hp_change_pattern(self):
        """Should detect Chinese HP change patterns."""
        text = "哥布林的HP变为5点。"
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0
        # Check that it detected numeric declaration (type is unauthorized_numeric_declaration)
        assert any("unauthorized" in v["type"].lower() for v in violations)

    def test_detect_english_hp_becomes_pattern(self):
        """Should detect English 'HP becomes' patterns."""
        text = "The goblin is wounded and HP becomes 3."
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0

    def test_detect_damage_announcement_with_number(self):
        """Should detect direct damage number announcements."""
        text = "你的攻击造成8点伤害。"
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0

    def test_detect_healing_with_number(self):
        """Should detect direct healing amount announcements."""
        text = "治疗魔法恢复了10点HP。"
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0

    def test_detect_resource_gain_with_number(self):
        """Should detect resource gain with numbers."""
        text = "你获得了15点临时生命。"
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0

    def test_detect_ac_change(self):
        """Should detect AC modification attempts."""
        text = "施法后，你的AC变为18。"
        violations = detect_unauthorized_numeric_declarations(text)
        assert len(violations) > 0

    def test_validation_rejects_numeric_overreach(self):
        """Full validation should reject narratives with numeric overreach."""
        result = validate_narrative_for_overreach(
            action_result="你的剑造成5点伤害，哥布林的HP变为2。",
            scene_progression="敌人显得很虚弱。",
            gm_prompt="继续攻击？",
            context=NarrationConstraintContext(outcome=Outcome.SUCCESS),
        )
        assert not result.is_valid
        assert any("numeric" in v.lower() for v in result.violations)


# -----------------------------------------------------------------------------
# Category 2: Plot Advancement / Story Forcing Tests
# -----------------------------------------------------------------------------

class TestPlotAdvancementViolations:
    """Test detection of AI attempting to force story progression."""

    def test_detect_auto_success_pattern(self):
        """Should detect auto-success patterns."""
        text = "你轻松解开了这个复杂的谜题。"
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_enemy_auto_defeat(self):
        """Should detect enemy auto-defeat patterns."""
        text = "敌人被击败，倒在地上。"
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_puzzle_auto_solve(self):
        """Should detect puzzle auto-solving patterns."""
        text = "陷阱自动解除，门打开了。"
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_scene_skip(self):
        """Should detect scene skipping patterns."""
        text = "剧情直接进入下一章。"
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_no_check_needed(self):
        """Should detect 'no check needed' patterns."""
        text = "无需检定，你直接成功了。"
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_english_auto_resolution(self):
        """Should detect English auto-resolution patterns."""
        text = "You automatically defeat the enemy and unlock the door."
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_detect_english_scene_jump(self):
        """Should detect English scene jump patterns."""
        text = "The scene jumps directly to the treasure room."
        violations = detect_unauthorized_plot_advancement(text)
        assert len(violations) > 0

    def test_validation_rejects_plot_forcing(self):
        """Full validation should reject narratives with plot forcing."""
        result = validate_narrative_for_overreach(
            action_result="你轻松击败了所有敌人。",
            scene_progression="剧情自动推进到下一个场景。",
            gm_prompt="继续前进？",
            context=NarrationConstraintContext(outcome=Outcome.SUCCESS),
        )
        assert not result.is_valid
        assert any("plot" in v.lower() or "forcing" in v.lower() for v in result.violations)


# -----------------------------------------------------------------------------
# Category 3: Combat Result Violation Tests
# -----------------------------------------------------------------------------

class TestCombatResultViolations:
    """Test detection of AI contradicting combat outcomes."""

    def test_detect_failure_narrated_as_hit(self):
        """Should detect when failure outcome is narrated as hit."""
        context = NarrationConstraintContext(
            outcome=Outcome.FAILURE,
            attack_result={"weapon": "sword", "target": "goblin", "damage": None},
        )
        result = validate_narrative_for_overreach(
            action_result="You hit the goblin cleanly.",
            scene_progression="The enemy staggers back.",
            gm_prompt="Press the attack?",
            context=context,
        )
        assert not result.is_valid
        assert any("failure" in v.lower() or "hit" in v.lower() for v in result.violations)

    def test_detect_defeated_before_zero_hp(self):
        """Should detect describing target as defeated when HP > 0."""
        target = Actor(
            id="goblin-01",
            name="Goblin",
            abilities=AbilityScores(str=8, dex=14, con=10, int=10, wis=8, cha=8),
            proficiency_bonus=2,
            hp=7,
            hp_max=7,
            ac=12,
        )
        context = NarrationConstraintContext(
            outcome=Outcome.SUCCESS,
            attack_result={
                "weapon": "sword",
                "target": "Goblin",
                "damage": {"total": 3},  # Non-lethal damage
            },
            target=target,
        )
        result = validate_narrative_for_overreach(
            action_result="You strike the goblin, killing it instantly.",
            scene_progression="The body falls lifeless.",
            gm_prompt="Loot the body?",
            context=context,
        )
        assert not result.is_valid
        assert any("defeat" in v.lower() for v in result.violations)

    def test_zero_damage_narrated_as_wound(self):
        """Should detect zero damage narrated as wounding."""
        context = NarrationConstraintContext(
            outcome=Outcome.FAILURE,
            attack_result={"weapon": "sword", "target": "goblin", "damage": None},
        )
        result = validate_narrative_for_overreach(
            action_result="Your blade wounds the goblin.",
            scene_progression="Blood flows from the cut.",
            gm_prompt="Attack again?",
            context=context,
        )
        assert not result.is_valid


# -----------------------------------------------------------------------------
# Category 4: State Change Violation Tests
# -----------------------------------------------------------------------------

class TestStateChangeViolations:
    """Test detection of unauthorized state changes."""

    def test_detect_unauthorized_condition_gain(self):
        """Should detect unauthorized condition gain announcements."""
        text = "你获得了中毒状态。"
        violations = detect_unauthorized_state_changes(text)
        assert len(violations) > 0

    def test_detect_unauthorized_condition_change(self):
        """Should detect unauthorized condition change announcements."""
        text = "状态变为恐惧。"
        violations = detect_unauthorized_state_changes(text)
        assert len(violations) > 0


# -----------------------------------------------------------------------------
# Integration Tests: Fallback to Safe Templates
# -----------------------------------------------------------------------------

class TestConstraintViolationFallback:
    """Test that constraint violations trigger fallback to safe templates."""

    def test_generate_narration_returns_safe_template_on_violation(
        self,
        monkeypatch,
        sample_actor,
        sample_scene,
        sample_target,
    ):
        """When AI generates violating narrative, should fallback to safe template."""
        req = ActionRequest(
            scene_id="combat-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            action_type=ActionType.ATTACK,
            weapon="longsword",
            target="goblin-01",
        )

        # Mock AI to return a narrative with numeric overreach
        async def fake_call(_prompt: str):
            return NarrationBundle(
                action_result="Aldric hits the goblin and its HP becomes 2.",
                scene_progression="The enemy is weakened.",
                gm_prompt="Press the attack?",
            )

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        monkeypatch.setattr("src.agent.narrator._call_kimi_api", fake_call)

        narration = generate_narration(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
            attack_result={
                "weapon": "longsword",
                "target": "Goblin Scout",
                "damage": {"total": 5, "rolls": [4, 1], "dice_expression": "1d8+1"},
            },
            target=sample_target,
        )

        # Should fallback to safe template (no HP declaration)
        assert "HP" not in narration.action_result or "becomes" not in narration.action_result.lower()

    def test_generate_narration_returns_safe_template_on_plot_forcing(
        self,
        monkeypatch,
        sample_actor,
        sample_scene,
    ):
        """When AI tries to force plot, should fallback to safe template."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="pick the lock",
            approach="use thieves tools",
            action_type=ActionType.SKILL_CHECK,
            skill="sleight_of_hand",
        )

        # Mock AI to return a narrative with plot forcing
        async def fake_call(_prompt: str):
            return NarrationBundle(
                action_result="你轻松解开了锁，谜题自动完成。",
                scene_progression="剧情直接进入宝藏室。",
                gm_prompt="拿走所有宝藏？",
            )

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        monkeypatch.setattr("src.agent.narrator._call_kimi_api", fake_call)

        narration = generate_narration(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
        )

        # Should fallback to safe template (no auto-resolution language)
        assert "自动" not in narration.action_result
        assert "直接" not in narration.scene_progression


# -----------------------------------------------------------------------------
# Validation Result Structure Tests
# -----------------------------------------------------------------------------

class TestValidationResultStructure:
    """Test that validation results have proper structure."""

    def test_validation_result_includes_violation_types(self):
        """Validation result should include specific violation types."""
        result = validate_narrative_for_overreach(
            action_result="你的攻击造成5点伤害，HP变为10。",
            scene_progression="你轻松击败了敌人，剧情自动推进。",
            gm_prompt="继续前进？",
            context=NarrationConstraintContext(outcome=Outcome.SUCCESS),
        )
        
        assert not result.is_valid
        assert result.violations
        assert result.marked_narrative is not None
        
        # Check violation categories are included
        violation_text = " ".join(result.violations).lower()
        assert "numeric" in violation_text or "plot" in violation_text

    def test_validation_logs_violations(self, caplog):
        """Validation should log violations at warning level."""
        import logging
        
        with caplog.at_level(logging.WARNING):
            validate_narrative_for_overreach(
                action_result="HP变为5。",
                scene_progression="敌人被击败。",
                gm_prompt="继续？",
                context=NarrationConstraintContext(outcome=Outcome.SUCCESS),
            )
        
        assert "constraint" in caplog.text.lower() or "violation" in caplog.text.lower()

    def test_marked_narrative_includes_warning_header(self):
        """Marked narrative should include validation warning header."""
        result = validate_narrative_for_overreach(
            action_result="HP变为5。",
            scene_progression="测试。",
            gm_prompt="继续？",
            context=NarrationConstraintContext(outcome=Outcome.SUCCESS),
        )
        
        assert result.marked_narrative is not None
        assert "VALIDATION WARNING" in result.marked_narrative
        assert "校验警告" in result.marked_narrative
