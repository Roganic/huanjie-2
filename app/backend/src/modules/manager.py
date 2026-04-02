"""Module manager for loading and managing adventure modules."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..models.module import (
    Module,
    ModuleSummary,
    ActiveModule,
)
from .models import ActiveModuleState


# Module storage directory
MODULES_DIR = Path(__file__).parent.parent.parent / "modules"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


class ModuleManager:
    """Manages loading and caching of adventure modules."""
    
    def __init__(self):
        self._modules: dict[str, Module] = {}
        self._active_modules: dict[str, ActiveModuleState] = {}  # session_id -> state
        
        # Ensure modules directory exists
        MODULES_DIR.mkdir(parents=True, exist_ok=True)
        
        # Auto-load built-in modules
        self._load_builtin_modules()
    
    def _load_builtin_modules(self) -> None:
        """Load all built-in modules from the modules directory."""
        builtin_dir = MODULES_DIR
        if not builtin_dir.exists():
            return
        
        for json_file in builtin_dir.glob("*.json"):
            try:
                self.load_module_from_file(str(json_file))
            except Exception as e:
                print(f"[ModuleManager] Failed to load built-in module {json_file}: {e}")
    
    def load_module_from_file(self, file_path: str) -> Module:
        """Load a module from a JSON file.
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            The loaded Module
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid or missing required fields
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Module file not found: {file_path}")
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return self.load_module_from_dict(data)
    
    def load_module_from_dict(self, data: dict) -> Module:
        """Load a module from a dictionary.
        
        Args:
            data: Dictionary containing module data
            
        Returns:
            The loaded Module
        """
        module = Module.model_validate(data)
        self._modules[module.id] = module
        return module
    
    def get_module(self, module_id: str) -> Optional[Module]:
        """Get a loaded module by ID.
        
        Args:
            module_id: The module ID
            
        Returns:
            The Module if found, None otherwise
        """
        return self._modules.get(module_id)
    
    def list_modules(self) -> list[ModuleSummary]:
        """Get a list of all loaded modules.
        
        Returns:
            List of module summaries
        """
        return [
            ModuleSummary(
                id=module.id,
                name=module.name,
                description=module.description,
                version=module.metadata.version,
                difficulty=module.metadata.difficulty,
            )
            for module in self._modules.values()
        ]
    
    def activate_module(
        self,
        session_id: str,
        module_id: str,
        starting_node_id: Optional[str] = None,
    ) -> Optional[ActiveModule]:
        """Activate a module for a session.
        
        Args:
            session_id: The session ID
            module_id: The module ID to activate
            starting_node_id: Optional starting node ID (defaults to module's starting_node_id)
            
        Returns:
            ActiveModule info if successful, None if module not found
        """
        module = self.get_module(module_id)
        if not module:
            return None
        
        # Determine starting node
        node_id = starting_node_id or module.starting_node_id
        if not node_id and module.story_nodes:
            # Default to first story node
            node_id = module.story_nodes[0].id
        
        # Determine starting scene
        scene_id = module.starting_scene_id
        if node_id:
            node = module.get_story_node(node_id)
            if node and node.scene_id:
                scene_id = node.scene_id
        
        active = ActiveModule(
            id=module_id,
            name=module.name,
            current_node_id=node_id,
            current_scene_id=scene_id,
            completed_nodes=[],
            active_flags=[],
        )
        
        # Store session state
        self._active_modules[session_id] = ActiveModuleState(
            session_id=session_id,
            module_id=module_id,
            module_name=module.name,
            current_node_id=node_id,
            current_scene_id=scene_id,
            completed_nodes=[],
            active_flags=[],
        )
        
        return active
    
    def get_active_module(self, session_id: str) -> Optional[ActiveModuleState]:
        """Get the active module for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            ActiveModuleState if a module is active, None otherwise
        """
        return self._active_modules.get(session_id)
    
    def deactivate_module(self, session_id: str) -> bool:
        """Deactivate the module for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            True if a module was deactivated, False otherwise
        """
        if session_id in self._active_modules:
            del self._active_modules[session_id]
            return True
        return False
    
    def update_session_state(
        self,
        session_id: str,
        current_node_id: Optional[str] = None,
        current_scene_id: Optional[str] = None,
        completed_node: Optional[str] = None,
        flags: Optional[list[str]] = None,
    ) -> Optional[ActiveModuleState]:
        """Update the active module state for a session.
        
        Args:
            session_id: The session ID
            current_node_id: New current node ID
            current_scene_id: New current scene ID
            completed_node: Node ID to mark as completed
            flags: Flags to add
            
        Returns:
            Updated ActiveModuleState if active, None otherwise
        """
        state = self._active_modules.get(session_id)
        if not state:
            return None
        
        if current_node_id is not None:
            state.current_node_id = current_node_id
        
        if current_scene_id is not None:
            state.current_scene_id = current_scene_id
        
        if completed_node and completed_node not in state.completed_nodes:
            state.completed_nodes.append(completed_node)
        
        if flags:
            for flag in flags:
                if flag not in state.active_flags:
                    state.active_flags.append(flag)
        
        return state
    
    def clear_all(self) -> None:
        """Clear all loaded modules and active sessions."""
        self._modules.clear()
        self._active_modules.clear()


# Singleton instance
_module_manager: Optional[ModuleManager] = None


def get_module_manager() -> ModuleManager:
    """Get the singleton module manager instance."""
    global _module_manager
    if _module_manager is None:
        _module_manager = ModuleManager()
    return _module_manager
