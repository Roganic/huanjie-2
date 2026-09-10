"""Integration tests for LLM-driven narrative generation.

Covers the LLM call path (with a mock client) and the fallback path
when no API key is configured.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent.narrator import generate_narration, NarrationBundle
from src.models.action import ActionRequest, Outcome
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
        description="A sturdy warrior.",
    )


@pytest.fixture
def sample_scene():
    return Scene(
        id="dungeon-01",
        name="Dark Cave",
        description="A damp cave with dripping water.",
        actors=["hero-01"],
    )


class TestLLMNarrativePath:
    """Verify LLM client integration and fallback behavior."""

    def test_llm_narrative_path_with_mock_client(self, sample_actor, sample_scene, monkeypatch):
        """When LLM client returns valid narrative, it should be used."""

        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            weapon="longsword",
        )

        mock_client = AsyncMock()
        mock_client.generate.return_value = (
            '{"action_result": "Aldric swings his longsword in a fierce arc.", '
            '"scene_progression": "The cave echoes with the clash of steel.", '
            '"gm_prompt": "Do you press the attack?"}'
        )

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        with patch("src.agent.narrator.get_provider", return_value=mock_client):
            narration = generate_narration(
                req=req,
                actor=sample_actor,
                scene=sample_scene,
                outcome=Outcome.SUCCESS,
            )

        assert narration.action_result == "Aldric swings his longsword in a fierce arc."
        assert "cave" in narration.scene_progression.lower()
        assert "press the attack" in narration.gm_prompt.lower()
        mock_client.generate.assert_awaited_once()

    def test_llm_fallback_when_no_api_key(self, sample_actor, sample_scene):
        """When no API key is configured, should fall back to template narrative."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="look around",
            approach="casually observe",
        )

        narration = generate_narration(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            outcome=Outcome.SUCCESS,
        )

        # Fallback should still mention the character
        assert "Aldric" in narration.action_result
        # Should be a template (reasonable length, non-empty)
        assert len(narration.action_result) > 10

    def test_llm_narrative_degrades_on_invalid_json(self, sample_actor, sample_scene, monkeypatch):
        """When LLM returns invalid JSON, should fall back to safe template."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            weapon="longsword",
        )

        mock_client = AsyncMock()
        mock_client.generate.return_value = "this is not json"

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        with patch("src.agent.narrator.get_provider", return_value=mock_client):
            narration = generate_narration(
                req=req,
                actor=sample_actor,
                scene=sample_scene,
                outcome=Outcome.SUCCESS,
            )

        # Fallback template should still be returned
        assert "Aldric" in narration.action_result
        assert len(narration.action_result) > 10

    def test_llm_narrative_degrades_on_constraint_violation(
        self, sample_actor, sample_scene, monkeypatch
    ):
        """When LLM returns a narrative violating constraints, fallback is used."""
        req = ActionRequest(
            scene_id="dungeon-01",
            actor="Aldric",
            intent="attack the goblin",
            approach="swing my longsword",
            weapon="longsword",
        )

        mock_client = AsyncMock()
        # Numeric authority violation: AI declares HP change
        mock_client.generate.return_value = (
            '{"action_result": "Aldric hits and the goblin HP becomes 2.", '
            '"scene_progression": "The enemy is weakened.", '
            '"gm_prompt": "Press the attack?"}'
        )

        monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "test-key")
        with patch("src.agent.narrator.get_provider", return_value=mock_client):
            narration = generate_narration(
                req=req,
                actor=sample_actor,
                scene=sample_scene,
                outcome=Outcome.SUCCESS,
            )

        # Constraint violation should trigger fallback
        assert "Aldric" in narration.action_result
        assert "HP becomes" not in narration.action_result
