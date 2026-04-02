"""Session memory management for AI narrative context.

This module provides session-level memory management to enable AI DM
to maintain narrative continuity across multiple actions.
"""

from .session_memory import (
    SessionMemory,
    MemoryEntry,
    MemoryConfig,
    ActionType,
    ResolutionOutcome,
    get_session_memory,
    add_memory_entry,
    get_memory_context,
    clear_session_memory,
    serialize_session_memory,
    deserialize_session_memory,
)

__all__ = [
    "SessionMemory",
    "MemoryEntry",
    "MemoryConfig",
    "ActionType",
    "ResolutionOutcome",
    "get_session_memory",
    "add_memory_entry",
    "get_memory_context",
    "clear_session_memory",
    "serialize_session_memory",
    "deserialize_session_memory",
]
