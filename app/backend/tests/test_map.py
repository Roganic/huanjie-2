"""Tests for the map system."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state
from src.scenes.data import SCENE_REGISTRY


@pytest.fixture(autouse=True)
def _fresh_state(_isolated_runtime):
    reset_state()
    from tests.conftest import create_default_actor
    create_default_actor()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestMapGeneration:
    """Test map node generation from scene registry."""

    def test_map_nodes_match_scene_registry(self):
        """Map should have exactly the same nodes as the scene registry."""
        from src.map import generate_map_from_scenes

        nodes = generate_map_from_scenes()
        assert len(nodes) == len(SCENE_REGISTRY)

        node_ids = {n.id for n in nodes}
        scene_ids = set(SCENE_REGISTRY.keys())
        assert node_ids == scene_ids

    def test_map_nodes_have_required_fields(self):
        """Each map node should have id, name, and connections."""
        from src.map import generate_map_from_scenes

        nodes = generate_map_from_scenes()
        for node in nodes:
            assert node.id
            assert node.name
            assert isinstance(node.connections, list)


class TestMapState:
    """Test map state tracking in session."""

    def test_initial_explored_nodes(self):
        """Creating a character should mark the starting scene as explored."""
        from src.state import create_session, get_map_state

        bootstrap = create_session()
        session_id = bootstrap.session_id
        map_state = get_map_state(session_id)

        assert bootstrap.scene.id in map_state["explored_nodes"]
        assert map_state["current_node"] == bootstrap.scene.id

    def test_switch_scene_updates_explored(self):
        """Switching scenes should add the new scene to explored nodes."""
        from src.state import create_session, switch_scene, get_map_state

        bootstrap = create_session()
        session_id = bootstrap.session_id
        from src.state import create_character
        from src.models.state import CharacterCreateRequest
        create_character(CharacterCreateRequest(name="地图测试", character_class="warrior"), session_id)
        initial_scene = "tavern-01"

        # Switch to a different scene
        target_scene = "village-square-01"
        if initial_scene == target_scene:
            target_scene = "tavern-01"

        switch_scene(target_scene, session_id)
        map_state = get_map_state(session_id)

        assert map_state["current_node"] == target_scene
        assert target_scene in map_state["explored_nodes"]
        assert initial_scene in map_state["explored_nodes"]


class TestMapEndpoint:
    """Test GET /map API endpoint."""

    @pytest.mark.asyncio
    async def test_get_map_returns_topology(self, client):
        async with client as c:
            resp = await c.get("/map?session_id=default-session")
        assert resp.status_code == 200
        data = resp.json()

        assert "nodes" in data
        assert "current_node" in data
        assert "explored_nodes" in data

        for node in data["nodes"]:
            assert "id" in node
            assert "name" in node
            assert "connections" in node
            assert isinstance(node["connections"], list)

    @pytest.mark.asyncio
    async def test_get_map_current_node_matches_state(self, client):
        async with client as c:
            state_resp = await c.get("/state?session_id=default-session")
            map_resp = await c.get("/map?session_id=default-session")

        state_data = state_resp.json()
        map_data = map_resp.json()

        assert map_data["current_node"] == state_data["scene"]["id"]

    @pytest.mark.asyncio
    async def test_get_map_explored_updates_after_move(self, client):
        async with client as c:
            # Use default session which has Aldric created automatically
            # Get initial map state
            map_resp = await c.get("/map?session_id=default-session")
            assert map_resp.status_code == 200
            initial_map = map_resp.json()
            initial_explored = set(initial_map["explored_nodes"])

            # Submit a movement action to village square
            action_resp = await c.post(
                "/action?session_id=default-session",
                json={
                    "scene_id": initial_map["current_node"],
                    "actor": "Aldric",
                    "intent": "前往村庄广场",
                    "approach": "步行前往",
                    "ability": "str",
                    "dc": 10,
                },
            )
            # Action may return streamed or direct response; just ensure 200
            assert action_resp.status_code == 200

            # Get updated map state
            map_resp2 = await c.get("/map?session_id=default-session")
            updated_map = map_resp2.json()
            updated_explored = set(updated_map["explored_nodes"])

            # At minimum the current node should still be explored
            assert updated_map["current_node"] == "village-square-01"
            assert "village-square-01" in updated_explored
            # Explored set should not shrink
            assert initial_explored.issubset(updated_explored)
