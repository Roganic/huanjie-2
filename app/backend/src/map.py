"""Map system for node topology and exploration tracking."""

from __future__ import annotations

from pydantic import BaseModel


class MapNode(BaseModel):
    id: str
    name: str
    connections: list[str]


def generate_map_from_scenes() -> list[MapNode]:
    """Generate map nodes automatically from the scene registry."""
    from .scenes.data import SCENE_REGISTRY

    nodes: list[MapNode] = []
    for scene_id, scene in SCENE_REGISTRY.items():
        connections: list[str] = []
        # Gather connections from exits
        for exit_data in scene.exits:
            if exit_data.target_scene_id not in connections:
                connections.append(exit_data.target_scene_id)
        # Also include connected_scenes as fallback
        for connected_id in scene.connected_scenes:
            if connected_id not in connections:
                connections.append(connected_id)
        nodes.append(MapNode(id=scene_id, name=scene.name, connections=connections))

    return nodes


def build_map_response(current_scene_id: str, explored_nodes: list[str]) -> dict:
    """Build the full map state response for the API."""
    nodes = generate_map_from_scenes()
    return {
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "current_node": current_scene_id,
        "explored_nodes": list(explored_nodes),
    }
