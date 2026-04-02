"""Map endpoints for scene topology and exploration tracking."""

from fastapi import APIRouter, HTTPException, Request

from ..models.map import MapConnection, MapNode, MapResponse
from ..scene_map import SCENE_MAP, get_scene_node
from ..state import get_scene

router = APIRouter(tags=["map"])


def _request_session_id(request: Request) -> str | None:
    return request.headers.get("X-Session-Id") or request.query_params.get("session_id")


def _resolve_session(request: Request) -> str:
    """Resolve session ID from request, using default if not provided."""
    session_id = _request_session_id(request)
    if session_id is None:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    return session_id


def _build_map_topology() -> tuple[list[MapNode], list[MapConnection]]:
    """Build the complete map topology from scene map definitions."""
    nodes: list[MapNode] = []
    connections: list[MapConnection] = []
    
    for scene_id, node in SCENE_MAP.items():
        # Create MapNode
        map_node = MapNode(
            id=scene_id,
            name=node.name,
            description=node.description[:100] + "..." if len(node.description) > 100 else node.description,
            exits=[{"direction": e.direction, "target_scene_id": e.target_scene_id} for e in node.exits],
            connections=[e.target_scene_id for e in node.exits],
        )
        nodes.append(map_node)
        
        # Create connections from exits
        for exit_info in node.exits:
            connection = MapConnection(
                from_node=scene_id,
                to_node=exit_info.target_scene_id,
                direction=exit_info.direction
            )
            connections.append(connection)
    
    return nodes, connections


@router.get("/map", response_model=MapResponse)
async def get_map(request: Request):
    """Get the current map state including topology and exploration progress.
    
    Returns:
        MapResponse containing:
        - current_node: Current scene ID where the player is located
        - nodes: All available scene nodes in the map
        - connections: All connections between nodes
        - explored_nodes: List of scene IDs that have been visited
    """
    from ..state import require_bootstrap_state, get_explored_nodes
    
    session_id = _resolve_session(request)
    
    # Validate session exists
    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    # Get current scene
    scene = get_scene(session_id)
    current_node = scene.id
    
    # Get explored nodes
    explored_nodes = get_explored_nodes(session_id)
    
    # Ensure current node is in explored nodes
    if current_node not in explored_nodes:
        explored_nodes = explored_nodes + [current_node]
    
    # Build topology
    nodes, connections = _build_map_topology()
    
    return MapResponse(
        current_node=current_node,
        nodes=nodes,
        connections=connections,
        explored_nodes=explored_nodes
    )


@router.get("/map/explored")
async def get_explored_nodes_endpoint(request: Request):
    """Get list of explored scene IDs.
    
    Returns:
        JSON with explored_nodes list and current_node.
    """
    from ..state import require_bootstrap_state, get_explored_nodes
    
    session_id = _resolve_session(request)
    
    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    scene = get_scene(session_id)
    explored_nodes = get_explored_nodes(session_id)
    
    # Ensure current node is in explored nodes
    if scene.id not in explored_nodes:
        explored_nodes = explored_nodes + [scene.id]
    
    return {
        "current_node": scene.id,
        "explored_nodes": explored_nodes
    }
