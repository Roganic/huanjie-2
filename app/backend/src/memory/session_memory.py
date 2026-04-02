"""Session memory management for AI narrative context.

Provides a simple list-based memory system for storing and retrieving
narrative history entries. No external vector database required.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    """Types of actions that can be recorded in memory."""
    ATTACK = "attack"
    SKILL_CHECK = "skill_check"
    SPELL = "spell"
    ITEM_USE = "item_use"
    MOVEMENT = "movement"
    INTERACTION = "interaction"
    OTHER = "other"


class ResolutionOutcome(str, Enum):
    """Outcome of an action resolution."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    CRITICAL_SUCCESS = "critical_success"
    CRITICAL_FAILURE = "critical_failure"


@dataclass
class MemoryEntry:
    """A single entry in the session memory.
    
    Contains all relevant information about an action and its resolution
    for narrative continuity.
    """
    # Identification
    entry_id: str
    timestamp: float
    
    # Action details
    action_type: ActionType
    action_summary: str
    intent: str
    actor_name: str
    
    # Resolution details
    outcome: ResolutionOutcome
    resolution_summary: dict[str, Any] = field(default_factory=dict)
    
    # Key numeric values (extracted for quick reference)
    hit_roll: Optional[int] = None
    damage: Optional[int] = None
    dc: Optional[int] = None
    check_total: Optional[int] = None
    
    # Narrative context
    narration_summary: str = ""
    scene_name: str = ""
    target_name: Optional[str] = None
    
    def to_prompt_format(self) -> dict[str, Any]:
        """Convert to dictionary format suitable for prompt injection."""
        result = {
            "action": self.action_summary,
            "actor": self.actor_name,
            "outcome": self.outcome.value,
            "type": self.action_type.value,
        }
        
        # Add key numeric values if present
        key_values = {}
        if self.hit_roll is not None:
            key_values["hit_roll"] = self.hit_roll
        if self.damage is not None:
            key_values["damage"] = self.damage
        if self.dc is not None:
            key_values["dc"] = self.dc
        if self.check_total is not None:
            key_values["check_total"] = self.check_total
        
        if key_values:
            result["key_values"] = key_values
        
        if self.target_name:
            result["target"] = self.target_name
        
        if self.narration_summary:
            result["narration_summary"] = self.narration_summary[:200]  # Truncate for prompt
        
        return result


@dataclass
class MemoryConfig:
    """Configuration for session memory behavior."""
    max_entries: int = 10  # Default: keep last 10 actions
    max_prompt_entries: int = 5  # Maximum entries to include in prompt
    max_prompt_chars: int = 2000  # Maximum characters for history context
    
    def __post_init__(self):
        # Ensure max_entries is reasonable
        if self.max_entries < 1:
            self.max_entries = 1
        if self.max_entries > 100:
            self.max_entries = 100
        
        # Ensure prompt limits are reasonable
        if self.max_prompt_entries < 1:
            self.max_prompt_entries = 1
        if self.max_prompt_entries > self.max_entries:
            self.max_prompt_entries = self.max_entries


class SessionMemory:
    """Manages narrative memory for a single session.
    
    Simple list-based storage with automatic truncation.
    Thread-safe for concurrent access.
    """
    
    def __init__(self, session_id: str, config: Optional[MemoryConfig] = None):
        self.session_id = session_id
        self.config = config or MemoryConfig()
        self._entries: list[MemoryEntry] = []
        self._lock = threading.RLock()
        self._entry_counter = 0
    
    def add_entry(
        self,
        action_type: ActionType | str,
        action_summary: str,
        intent: str,
        actor_name: str,
        outcome: ResolutionOutcome | str,
        resolution_summary: Optional[dict[str, Any]] = None,
        hit_roll: Optional[int] = None,
        damage: Optional[int] = None,
        dc: Optional[int] = None,
        check_total: Optional[int] = None,
        narration_summary: str = "",
        scene_name: str = "",
        target_name: Optional[str] = None,
    ) -> MemoryEntry:
        """Add a new entry to the session memory.
        
        Automatically truncates to max_entries limit.
        
        Returns:
            The newly created MemoryEntry
        """
        with self._lock:
            self._entry_counter += 1
            
            # Normalize enums
            if isinstance(action_type, str):
                action_type = ActionType(action_type)
            if isinstance(outcome, str):
                outcome = ResolutionOutcome(outcome)
            
            entry = MemoryEntry(
                entry_id=f"{self.session_id}-{self._entry_counter}",
                timestamp=time.time(),
                action_type=action_type,
                action_summary=action_summary,
                intent=intent,
                actor_name=actor_name,
                outcome=outcome,
                resolution_summary=resolution_summary or {},
                hit_roll=hit_roll,
                damage=damage,
                dc=dc,
                check_total=check_total,
                narration_summary=narration_summary,
                scene_name=scene_name,
                target_name=target_name,
            )
            
            self._entries.append(entry)
            
            # Truncate to max_entries
            if len(self._entries) > self.config.max_entries:
                self._entries = self._entries[-self.config.max_entries:]
            
            logger.debug(
                "Added memory entry %s for session %s (total: %d)",
                entry.entry_id,
                self.session_id,
                len(self._entries),
            )
            
            return entry
    
    def get_all_entries(self) -> list[MemoryEntry]:
        """Get all entries in chronological order."""
        with self._lock:
            return list(self._entries)
    
    def get_recent_entries(self, count: Optional[int] = None) -> list[MemoryEntry]:
        """Get the most recent entries.
        
        Args:
            count: Number of entries to return (default: max_prompt_entries)
        
        Returns:
            List of entries in chronological order
        """
        with self._lock:
            limit = count or self.config.max_prompt_entries
            return list(self._entries[-limit:])
    
    def get_context_for_prompt(self) -> list[dict[str, Any]]:
        """Get entries formatted for prompt injection.
        
        Respects max_prompt_entries and max_prompt_chars limits.
        
        Returns:
            List of entry dictionaries for prompt building
        """
        with self._lock:
            entries = self._entries[-self.config.max_prompt_entries:]
            result = []
            total_chars = 0
            
            for entry in entries:
                formatted = entry.to_prompt_format()
                entry_chars = len(str(formatted))
                
                if result and total_chars + entry_chars > self.config.max_prompt_chars:
                    # Would exceed limit, stop adding entries
                    break
                
                result.append(formatted)
                total_chars += entry_chars
            
            return result
    
    def clear(self) -> None:
        """Clear all entries from memory."""
        with self._lock:
            self._entries.clear()
            logger.debug("Cleared memory for session %s", self.session_id)
    
    def __len__(self) -> int:
        """Return the number of entries in memory."""
        with self._lock:
            return len(self._entries)
    
    def to_serializable(self) -> dict[str, Any]:
        """Convert to serializable dictionary for persistence."""
        with self._lock:
            return {
                "session_id": self.session_id,
                "config": {
                    "max_entries": self.config.max_entries,
                    "max_prompt_entries": self.config.max_prompt_entries,
                    "max_prompt_chars": self.config.max_prompt_chars,
                },
                "entries": [
                    {
                        "entry_id": e.entry_id,
                        "timestamp": e.timestamp,
                        "action_type": e.action_type.value,
                        "action_summary": e.action_summary,
                        "intent": e.intent,
                        "actor_name": e.actor_name,
                        "outcome": e.outcome.value,
                        "resolution_summary": e.resolution_summary,
                        "hit_roll": e.hit_roll,
                        "damage": e.damage,
                        "dc": e.dc,
                        "check_total": e.check_total,
                        "narration_summary": e.narration_summary,
                        "scene_name": e.scene_name,
                        "target_name": e.target_name,
                    }
                    for e in self._entries
                ],
            }
    
    @classmethod
    def from_serializable(cls, data: dict[str, Any]) -> "SessionMemory":
        """Restore SessionMemory from serialized dictionary."""
        config_data = data.get("config", {})
        config = MemoryConfig(
            max_entries=config_data.get("max_entries", 10),
            max_prompt_entries=config_data.get("max_prompt_entries", 5),
            max_prompt_chars=config_data.get("max_prompt_chars", 2000),
        )
        
        memory = cls(data["session_id"], config)
        
        for entry_data in data.get("entries", []):
            entry = MemoryEntry(
                entry_id=entry_data["entry_id"],
                timestamp=entry_data["timestamp"],
                action_type=ActionType(entry_data["action_type"]),
                action_summary=entry_data["action_summary"],
                intent=entry_data["intent"],
                actor_name=entry_data["actor_name"],
                outcome=ResolutionOutcome(entry_data["outcome"]),
                resolution_summary=entry_data.get("resolution_summary", {}),
                hit_roll=entry_data.get("hit_roll"),
                damage=entry_data.get("damage"),
                dc=entry_data.get("dc"),
                check_total=entry_data.get("check_total"),
                narration_summary=entry_data.get("narration_summary", ""),
                scene_name=entry_data.get("scene_name", ""),
                target_name=entry_data.get("target_name"),
            )
            memory._entries.append(entry)
        
        return memory


# Global memory store (similar to session store pattern)
_memory_store: dict[str, SessionMemory] = {}
_memory_lock = threading.RLock()


def get_session_memory(session_id: str, config: Optional[MemoryConfig] = None) -> SessionMemory:
    """Get or create SessionMemory for a given session ID.
    
    Args:
        session_id: The session identifier
        config: Optional configuration (only used when creating new memory)
    
    Returns:
        SessionMemory instance for the session
    """
    with _memory_lock:
        if session_id not in _memory_store:
            _memory_store[session_id] = SessionMemory(session_id, config)
        return _memory_store[session_id]


def add_memory_entry(
    session_id: str,
    action_type: ActionType | str,
    action_summary: str,
    intent: str,
    actor_name: str,
    outcome: ResolutionOutcome | str,
    **kwargs,
) -> Optional[MemoryEntry]:
    """Convenience function to add an entry to a session's memory.
    
    Args:
        session_id: The session identifier
        action_type: Type of action performed
        action_summary: Brief summary of the action
        intent: The original intent of the action
        actor_name: Name of the acting character
        outcome: Result of the action
        **kwargs: Additional fields for MemoryEntry
    
    Returns:
        The created MemoryEntry, or None if creation failed
    """
    try:
        memory = get_session_memory(session_id)
        return memory.add_entry(
            action_type=action_type,
            action_summary=action_summary,
            intent=intent,
            actor_name=actor_name,
            outcome=outcome,
            **kwargs,
        )
    except Exception as e:
        logger.warning("Failed to add memory entry for session %s: %s", session_id, e)
        return None


def get_memory_context(session_id: str) -> list[dict[str, Any]]:
    """Get formatted memory context for prompt building.
    
    Args:
        session_id: The session identifier
    
    Returns:
        List of entry dictionaries formatted for prompt injection
    """
    try:
        memory = get_session_memory(session_id)
        return memory.get_context_for_prompt()
    except Exception as e:
        logger.warning("Failed to get memory context for session %s: %s", session_id, e)
        return []


def clear_session_memory(session_id: str) -> None:
    """Clear all memory for a specific session.
    
    Args:
        session_id: The session identifier
    """
    with _memory_lock:
        if session_id in _memory_store:
            _memory_store[session_id].clear()
            del _memory_store[session_id]
            logger.debug("Cleared and removed memory for session %s", session_id)


def serialize_session_memory(session_id: str) -> Optional[dict[str, Any]]:
    """Serialize session memory for persistence.
    
    Args:
        session_id: The session identifier
    
    Returns:
        Serializable dictionary, or None if no memory exists
    """
    with _memory_lock:
        if session_id not in _memory_store:
            return None
        return _memory_store[session_id].to_serializable()


def deserialize_session_memory(data: dict[str, Any]) -> SessionMemory:
    """Deserialize session memory from persisted data.
    
    Args:
        data: Serialized memory data
    
    Returns:
        Restored SessionMemory instance
    """
    with _memory_lock:
        memory = SessionMemory.from_serializable(data)
        _memory_store[memory.session_id] = memory
        return memory
