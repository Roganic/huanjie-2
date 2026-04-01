"""Tests for hard constraint injection in AI narrative prompts.

These tests verify that:
1. Rule engine results (success/failure, damage, state changes) are properly injected
2. Hard constraints are clearly separated from narrative space in prompts
3. Failed actions are never narrated as successful
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


class TestNarrationConstraintValidation:
    """Test the lightweight post-generation contradiction checks."""

    def test_failed_attack_hit_language_rejected(self, sample_target):
        narration = NarrationBundle(
            action_result="Aldric hits the goblin and wounds it badly.",
            scene_progression="The goblin staggers back.",
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
# End-to-end tests for narrative consistency
# -----------------------------------------------------------------------------

@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestNarrativeConsistency:
    """End-to-end tests verifying narrative respects rule engine results."""

    @pytest.mark.asyncio
    async def test_failed_attack_not_described_as_hit(self, client):
        """CRITICAL: A failed attack must never be narrated as a successful hit.
        
        This test verifies the hard constraint principle:
        - Rule engine says: attack FAILED (miss)
        - Narrative must NOT say: hit, struck, connected, landed, etc.
        """
        from src.state import set_combat_scene, get_enemy, reset_state
        
        reset_state()
        set_combat_scene()
        
        # Force a miss by using a very high target AC
        # We'll manipulate this by making multiple attacks until we get a miss
        # Or we can use a deterministic approach by patching the dice roll
        
        # For this test, we'll use the actual API and check that if outcome is failure,
        # the narrative doesn't contain hit language
        async with client as c:
            resp = await c.post("/action", json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack the goblin",
                "approach": "swing my longsword",
                "weapon": "longsword",
                "target": "goblin-01",
            })
        
        assert resp.status_code == 200
        data = resp.json()
        
        # If the outcome is failure (miss)
        if data["outcome"] == "failure":
            narration = data["narration"].lower()
            
            # These words would indicate a successful hit - they should NOT appear
            hit_indicators = ["hits", "hit", "strikes", "struck", "connected", 
                            "landed", "wounds", "wounded", "slashes", "pierces"]
            
            for indicator in hit_indicators:
                assert indicator not in narration, (
                    f"Failed attack should not use hit language like '{indicator}'. "
                    f"Narration: {data['narration']}"
                )
            
            # Should contain miss-related language (in the fallback template)
            # or at least not contradict the miss outcome
            assert "miss" in narration or "misses" in narration or \
                   "dodge" in narration or "aside" in narration or \
                   "avoid" in narration or "fail" in narration or \
                   "narrowly" in narration or "dances" in narration, (
                f"Miss narration should indicate failure to connect. "
                f"Narration: {data['narration']}"
            )

    @pytest.mark.asyncio
    async def test_successful_attack_described_as_hit(self, client):
        """A successful attack should be narrated appropriately.
        
        When the rule engine says SUCCESS, the narrative should reflect a hit.
        """
        from src.state import set_combat_scene, reset_state
        
        reset_state()
        set_combat_scene()
        
        # Make multiple attempts to get a success
        max_attempts = 20
        for attempt in range(max_attempts):
            reset_state()
            set_combat_scene()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.post("/action", json={
                    "scene_id": "combat-01",
                    "actor": "Aldric",
                    "intent": "attack the goblin",
                    "approach": "swing my longsword",
                    "weapon": "longsword",
                    "target": "goblin-01",
                })
            
            data = resp.json()
            
            if data["outcome"] == "success":
                narration = data["narration"].lower()
                
                # Should indicate a hit landed
                hit_words = ["hit", "hits", "strike", "strikes", "slash", "bites", 
                           "cut", "wound", "pierce", "connect"]
                assert any(word in narration for word in hit_words), (
                    f"Successful attack should indicate a hit. "
                    f"Narration: {data['narration']}"
                )
                return
        
        pytest.skip(f"Could not get a successful attack after {max_attempts} attempts")

    @pytest.mark.asyncio
    async def test_narration_matches_outcome_structure(self, client):
        """Narration should structurally match the outcome type."""
        from src.state import reset_state
        
        # Test success case
        reset_state()
        async with client as c:
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "look around",
                "approach": "casually observe",
            })
        
        data = resp.json()
        assert data["outcome"] == "success"
        # Auto-success should have positive language
        narration = data["narration"].lower()
        # Should not contain failure language
        assert "fail" not in narration or "failure" not in narration

    @pytest.mark.asyncio
    async def test_attack_damage_consistent_with_narrative(self, client):
        """Damage dealt should be consistent between effects and narrative context."""
        from src.state import set_combat_scene, get_enemy, reset_state
        
        reset_state()
        set_combat_scene()
        initial_hp = get_enemy().hp
        
        async with client as c:
            resp = await c.post("/action", json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack the goblin",
                "approach": "swing my longsword",
                "weapon": "longsword",
                "target": "goblin-01",
            })
        
        data = resp.json()
        
        if data["outcome"] == "success" and data.get("attack") and data["attack"].get("damage"):
            damage = data["attack"]["damage"]["total"]
            effects = data["effects"]
            
            # Find the HP effect
            hp_effects = [e for e in effects if e["field"] == "hp" and "goblin" in e["target"].lower()]
            assert len(hp_effects) > 0, "Should have HP effect for successful attack"
            
            # Damage should match (negative delta)
            hp_delta = hp_effects[0]["delta"]
            assert hp_delta == -damage, f"HP delta {hp_delta} should match damage {-damage}"


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


@pytest.mark.asyncio
async def test_second_action_prompt_includes_prior_narrative_history(monkeypatch, client):
    prompts: list[str] = []
    original_builder = _build_narrative_prompt

    def capture_prompt(*args, **kwargs):
        prompt = original_builder(*args, **kwargs)
        prompts.append(prompt)
        return prompt

    monkeypatch.setattr("src.agent.narrator._build_narrative_prompt", capture_prompt)

    async with client as c:
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "inspect the fireplace",
            "approach": "kneel beside the ashes and search for recent traces",
        })
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "question the innkeeper",
            "approach": "ask about whoever used the hearth last",
            "ability": "cha",
            "dc": 10,
        })

    assert len(prompts) == 2
    assert "Session Narrative History" in prompts[1]
    assert "Aldric attempts to inspect the fireplace" in prompts[1]
