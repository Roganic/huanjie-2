"""Module system API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..modules.manager import get_module_manager
from ..modules.models import LoadModuleRequest, LoadModuleResponse
from ..models.module import ModuleSummary, Module

router = APIRouter(tags=["modules"])


def _request_session_id(request: Request) -> str | None:
    """Extract session ID from request headers or query params."""
    return request.headers.get("X-Session-Id") or request.query_params.get("session_id")


@router.get("/modules")
async def list_modules(request: Request) -> dict:
    """List all loaded modules.
    
    Returns a list of modules with their id, name, and description.
    """
    manager = get_module_manager()
    modules = manager.list_modules()
    
    return {
        "modules": [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "version": m.version,
                "difficulty": m.difficulty,
            }
            for m in modules
        ],
        "total": len(modules),
    }


@router.get("/modules/{module_id}")
async def get_module(module_id: str, request: Request) -> dict:
    """Get a specific module's full content.
    
    Args:
        module_id: The unique identifier of the module
        
    Returns:
        Complete module data including scenes, npcs, quests, story_nodes, triggers
    """
    manager = get_module_manager()
    module = manager.get_module(module_id)
    
    if not module:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")
    
    return module.model_dump(mode="json")


@router.post("/modules/load", response_model=LoadModuleResponse)
async def load_module(request: LoadModuleRequest, req: Request) -> LoadModuleResponse:
    """Load a module from a file path or request body.
    
    Args:
        request: LoadModuleRequest containing either file_path or module_data
        
    Returns:
        LoadModuleResponse with success status and module info
    """
    manager = get_module_manager()
    
    try:
        if request.file_path:
            # Load from file
            module = manager.load_module_from_file(request.file_path)
        elif request.module_data:
            # Load from inline data
            module = manager.load_module_from_dict(request.module_data)
        else:
            return LoadModuleResponse(
                success=False,
                message="Either file_path or module_data must be provided"
            )
        
        return LoadModuleResponse(
            success=True,
            module_id=module.id,
            module_name=module.name,
            message=f"Successfully loaded module '{module.name}'"
        )
        
    except FileNotFoundError as e:
        return LoadModuleResponse(
            success=False,
            message=f"File not found: {str(e)}"
        )
    except Exception as e:
        return LoadModuleResponse(
            success=False,
            message=f"Failed to load module: {str(e)}"
        )


@router.post("/modules/{module_id}/activate")
async def activate_module(module_id: str, request: Request) -> dict:
    """Activate a module for the current session.
    
    Args:
        module_id: The module to activate
        
    Returns:
        Active module information
    """
    session_id = _request_session_id(request)
    if not session_id:
        # Use default session for backward compatibility
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    
    manager = get_module_manager()
    
    # Check if module exists
    module = manager.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")
    
    # Activate the module
    active = manager.activate_module(session_id, module_id)
    if not active:
        raise HTTPException(status_code=500, detail="Failed to activate module")
    
    return {
        "success": True,
        "module_id": active.id,
        "module_name": active.name,
        "current_node_id": active.current_node_id,
        "current_scene_id": active.current_scene_id,
        "message": f"Module '{active.name}' activated"
    }


@router.post("/modules/deactivate")
async def deactivate_module(request: Request) -> dict:
    """Deactivate the current module for the session.
    
    Returns:
        Success status
    """
    session_id = _request_session_id(request)
    if not session_id:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    
    manager = get_module_manager()
    success = manager.deactivate_module(session_id)
    
    return {
        "success": success,
        "message": "Module deactivated" if success else "No active module"
    }


@router.get("/modules/active/state")
async def get_active_module_state(request: Request) -> dict:
    """Get the active module state for the current session.
    
    Returns:
        Active module state or empty object if no module active
    """
    session_id = _request_session_id(request)
    if not session_id:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    
    manager = get_module_manager()
    state = manager.get_active_module(session_id)
    
    if not state:
        return {"active": False}
    
    return {
        "active": True,
        "session_id": state.session_id,
        "module_id": state.module_id,
        "module_name": state.module_name,
        "current_node_id": state.current_node_id,
        "current_scene_id": state.current_scene_id,
        "completed_nodes": state.completed_nodes,
        "active_flags": state.active_flags,
    }
