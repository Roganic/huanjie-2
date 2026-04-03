"""Session action memory with append/trim logic.

Provides structured action history management for narrative continuity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Default limits for action history
MAX_ACTION_HISTORY = 10
DEFAULT_PROMPT_HISTORY = 5


@dataclass
class ActionHistoryEntry:
    """A single action history entry for session memory."""

    action: str
    result: str
    narrative_summary: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for API responses."""
        return {
            "action": self.action,
            "result": self.result,
            "narrative_summary": self.narrative_summary,
        }


class Memory:
    """Manages action history with automatic trimming.

    Provides methods to:
    - Append new action entries
    - Trim to maximum size (oldest removed first)
    - Retrieve recent entries for prompt injection
    """

    def __init__(self, max_entries: int = MAX_ACTION_HISTORY):
        self.max_entries = max_entries
        self._entries: list[ActionHistoryEntry] = []

    def append(self, entry: ActionHistoryEntry) -> None:
        """Append an entry and auto-trim if over limit."""
        self._entries.append(entry)
        self.trim()

    def trim(self) -> None:
        """Trim oldest entries when exceeding max_entries."""
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def get_recent(self, count: Optional[int] = None) -> list[ActionHistoryEntry]:
        """Get the most recent entries.

        Args:
            count: Number of entries to return (default: max_entries)

        Returns:
            List of recent ActionHistoryEntry objects
        """
        n = count or self.max_entries
        return list(self._entries[-n:])

    def to_dicts(self, count: Optional[int] = None) -> list[dict[str, str]]:
        """Convert recent entries to dictionaries."""
        return [entry.to_dict() for entry in self.get_recent(count)]

    def __len__(self) -> int:
        return len(self._entries)


def from_narrative_entry(
    action_summary: str,
    outcome: str,
    narration_summary: str,
) -> ActionHistoryEntry:
    """Create an ActionHistoryEntry from narrative components."""
    return ActionHistoryEntry(
        action=action_summary,
        result=outcome,
        narrative_summary=narration_summary,
    )
