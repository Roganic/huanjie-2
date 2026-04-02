"""API models for module endpoints."""

from typing import Optional

from pydantic import BaseModel, Field

from ..models.module import Module


class LoadModuleRequest(BaseModel):
    """Request to load a module."""
    file_path: Optional[str] = Field(
        default=None,
        description="Path to JSON file containing the module"
    )
    module_data: Optional[dict] = Field(
        default=None,
        description="Module data inline (alternative to file_path)"
    )
    
    model_config = {"populate_by_name": True}


class LoadModuleResponse(BaseModel):
    """Response from loading a module."""
    success: bool
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    message: str = ""
    
    model_config = {"populate_by_name": True}


class ActiveModuleState(BaseModel):
    """State of the currently active module for a session."""
    session_id: str
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    current_node_id: Optional[str] = None
    current_scene_id: Optional[str] = None
    completed_nodes: list[str] = Field(default_factory=list)
    active_flags: list[str] = Field(default_factory=list)
    
    model_config = {"populate_by_name": True}


class ModuleListResponse(BaseModel):
    """Response containing list of loaded modules."""
    modules: list[dict]
    total: int
    
    model_config = {"populate_by_name": True}
