"""Smoke test for the deployable game loop."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_public_game_flow_smoke(client):
    async with client as c:
        create_response = await c.post(
            "/state/character",
            json={"name": "Mira", "archetype": "rogue"},
        )
        assert create_response.status_code == 200
        created_state = create_response.json()
        assert created_state["actor"]["name"] == "Mira"
        assert created_state["actor"]["id"].startswith("player")

        action_response = await c.post(
            "/action",
            json={
                "scene_id": created_state["scene"]["id"],
                "actor": "Mira",
                "intent": "slip behind the sentry and cut the bell rope",
                "approach": "move through the shadows and strike fast",
                "ability": "dex",
                "advantage": True,
            },
        )
        assert action_response.status_code == 200
        action_payload = action_response.json()
        assert action_payload["narration"]
        assert action_payload["scene_progression"]
        assert action_payload["outcome"] in ("success", "failure")

        reset_response = await c.post("/state/reset")
        assert reset_response.status_code == 200
        reset_state_payload = reset_response.json()
        assert reset_state_payload["actor"]["name"] == "Aldric"
        assert reset_state_payload["scene"]["id"] == "tavern-01"
