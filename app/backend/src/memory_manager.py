"""Memory manager for narrative event history.

Provides session-level event memory management for AI narrative context.
Records key events (action type, result summary, scene) and formats
them for injection into narrative prompts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .models.state import NarrativeHistoryEntry


@dataclass
class EventMemoryEntry:
    """A single event memory entry for narrative context.
    
    This is a simplified view of NarrativeHistoryEntry optimized for
    LLM prompt injection - containing only the essential context.
    """
    timestamp: int  # Unix timestamp in milliseconds
    scene_name: str
    action_type: str
    action_description: str
    result_summary: str
    outcome: str  # "success" or "failure"
    
    def to_prompt_line(self) -> str:
        """Convert to a single line format suitable for prompts."""
        time_str = datetime.fromtimestamp(self.timestamp / 1000).strftime("%H:%M:%S")
        return (
            f"[{time_str}] {self.scene_name}: {self.action_description} "
            f"({self.outcome}) - {self.result_summary[:80]}"
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "timestamp": self.timestamp,
            "scene_name": self.scene_name,
            "action_type": self.action_type,
            "action_description": self.action_description,
            "result_summary": self.result_summary,
            "outcome": self.outcome,
        }


class MemoryManager:
    """Manages event memory for narrative context.
    
    Provides methods to:
    - Add new event memories from action results
    - Retrieve recent events for prompt injection
    - Format events for different use cases
    """
    
    DEFAULT_MAX_EVENTS = 10  # Default number of recent events to keep
    DEFAULT_MAX_CHARS = 2000  # Default max characters for prompt context
    
    def __init__(self, max_events: int = DEFAULT_MAX_EVENTS, max_chars: int = DEFAULT_MAX_CHARS):
        self.max_events = max_events
        self.max_chars = max_chars
    
    def extract_from_narrative_entry(
        self,
        entry: NarrativeHistoryEntry,
        scene_name: str = "未知场景",
    ) -> EventMemoryEntry:
        """Extract a memory entry from a NarrativeHistoryEntry.
        
        Args:
            entry: The narrative history entry from session storage
            scene_name: The name of the scene where the action occurred
            
        Returns:
            A simplified EventMemoryEntry for memory storage
        """
        resolution = entry.resolution_summary or {}
        
        # Determine action type from resolution
        action_type = resolution.get("resolution_type", "action")
        
        # Determine outcome
        outcome = resolution.get("outcome", "unknown")
        
        # Build result summary from narration_summary (truncated)
        result_summary = entry.narration_summary or entry.action_summary
        
        return EventMemoryEntry(
            timestamp=entry.created_at or int(datetime.now().timestamp() * 1000),
            scene_name=scene_name,
            action_type=action_type,
            action_description=entry.action_summary,
            result_summary=result_summary,
            outcome=outcome,
        )
    
    def get_recent_events(
        self,
        narrative_history: list[NarrativeHistoryEntry],
        scene_name: Optional[str] = None,
        max_events: Optional[int] = None,
    ) -> list[EventMemoryEntry]:
        """Extract recent event memories from narrative history.
        
        Args:
            narrative_history: Full list of narrative history entries
            scene_name: Optional scene name to filter by
            max_events: Maximum number of events to return (default: self.max_events)
            
        Returns:
            List of EventMemoryEntry objects, most recent last
        """
        max_e = max_events or self.max_events
        
        # Get the most recent entries
        recent_entries = narrative_history[-max_e:] if len(narrative_history) > max_e else narrative_history
        
        events = []
        for entry in recent_entries:
            event = self.extract_from_narrative_entry(entry, scene_name or "未知场景")
            events.append(event)
        
        return events
    
    def format_for_prompt(
        self,
        events: list[EventMemoryEntry],
        max_chars: Optional[int] = None,
    ) -> str:
        """Format event memories for injection into narrative prompts.
        
        Args:
            events: List of event memory entries
            max_chars: Maximum characters to include (default: self.max_chars)
            
        Returns:
            Formatted string suitable for prompt injection
        """
        if not events:
            return "无近期事件 / No recent events."
        
        max_c = max_chars or self.max_chars
        lines = ["近期事件历史 / Recent Event History:"]
        
        current_chars = len(lines[0])
        
        for i, event in enumerate(events, 1):
            line = f"{i}. {event.to_prompt_line()}"
            if current_chars + len(line) + 1 > max_c and i > 1:
                break
            lines.append(line)
            current_chars += len(line) + 1
        
        return "\n".join(lines)
    
    def build_memory_context(
        self,
        narrative_history: list[NarrativeHistoryEntry],
        current_scene_name: str,
        max_events: Optional[int] = None,
    ) -> str:
        """Build a complete memory context string for narrative prompts.
        
        This is the main entry point for getting formatted memory context
        to inject into LLM prompts.
        
        Args:
            narrative_history: Full narrative history from session
            current_scene_name: Name of the current scene
            max_events: Maximum events to include
            
        Returns:
            Formatted memory context string
        """
        events = self.get_recent_events(
            narrative_history,
            scene_name=current_scene_name,
            max_events=max_events,
        )
        return self.format_for_prompt(events)


# Global memory manager instance
_default_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = MemoryManager()
    return _default_manager


def format_recent_events_for_prompt(
    narrative_history: list[NarrativeHistoryEntry],
    current_scene_name: str = "",
    max_events: int = 5,
) -> str:
    """Convenience function to format recent events for prompts.
    
    Args:
        narrative_history: Full narrative history from session
        current_scene_name: Name of the current scene
        max_events: Maximum number of events to include
        
    Returns:
        Formatted string for prompt injection
    """
    manager = get_memory_manager()
    return manager.build_memory_context(
        narrative_history,
        current_scene_name,
        max_events=max_events,
    )


def get_recent_event_memories(
    narrative_history: list[NarrativeHistoryEntry],
    max_events: int = 10,
) -> list[dict[str, Any]]:
    """Get recent events as dictionaries for API responses.
    
    Args:
        narrative_history: Full narrative history from session
        max_events: Maximum number of events to return
        
    Returns:
        List of event dictionaries
    """
    manager = get_memory_manager()
    events = manager.get_recent_events(narrative_history, max_events=max_events)
    return [event.to_dict() for event in events]
