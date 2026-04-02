"""NPC dialogue state management.

This module provides dialogue history tracking for NPC interactions,
allowing NPCs to remember previous conversations with the player.
"""

from __future__ import annotations

import time
from typing import Optional

from pydantic import BaseModel, Field


class NPCDialogueEntry(BaseModel):
    """A single dialogue entry in the conversation history.
    
    Tracks what was said by whom and when.
    """
    speaker: str = Field(..., description="Who spoke: 'player' or NPC name")
    content: str = Field(..., description="The dialogue content")
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000), description="Timestamp in ms")
    
    def to_prompt_line(self) -> str:
        """Convert to a single line for prompt injection."""
        return f"{self.speaker}: {self.content}"


class NPCDialogueState(BaseModel):
    """Dialogue state for a single NPC.
    
    Tracks the full conversation history and metadata for an NPC.
    """
    npc_id: str
    npc_name: str
    dialogue_count: int = Field(default=0, description="Number of dialogue interactions")
    history: list[NPCDialogueEntry] = Field(default_factory=list, description="Full dialogue history")
    last_interaction_at: Optional[int] = Field(default=None, description="Last interaction timestamp")
    
    model_config = {"populate_by_name": True}
    
    def add_entry(self, speaker: str, content: str) -> None:
        """Add a new dialogue entry."""
        entry = NPCDialogueEntry(speaker=speaker, content=content)
        self.history.append(entry)
        # Keep only last 5 entries
        self.history = self.history[-5:]
        self.dialogue_count += 1
        self.last_interaction_at = entry.timestamp
    
    def get_recent_history(self, max_entries: int = 5) -> list[NPCDialogueEntry]:
        """Get the most recent dialogue entries."""
        return self.history[-max_entries:]
    
    def is_first_contact(self) -> bool:
        """Check if this is the first interaction with this NPC."""
        return self.dialogue_count == 0


# In-memory storage for NPC dialogue states (mirrors session storage pattern)
_npc_dialogue_states: dict[str, dict[str, NPCDialogueState]] = {}


def _get_session_npc_states(session_id: str) -> dict[str, NPCDialogueState]:
    """Get or create the NPC dialogue states dict for a session."""
    if session_id not in _npc_dialogue_states:
        _npc_dialogue_states[session_id] = {}
    return _npc_dialogue_states[session_id]


def record_dialogue(
    npc_id: str,
    npc_name: str,
    speaker: str,
    content: str,
    session_id: str = "default-session",
) -> NPCDialogueState:
    """Record a dialogue entry for an NPC.
    
    Args:
        npc_id: The NPC's unique ID
        npc_name: The NPC's display name
        speaker: Who spoke ('player' or NPC name)
        content: What was said
        session_id: The session ID
        
    Returns:
        The updated dialogue state for this NPC
    """
    session_states = _get_session_npc_states(session_id)
    
    if npc_id not in session_states:
        session_states[npc_id] = NPCDialogueState(
            npc_id=npc_id,
            npc_name=npc_name,
        )
    
    state = session_states[npc_id]
    state.add_entry(speaker, content)
    return state


def get_dialogue_history(
    npc_id: str,
    session_id: str = "default-session",
    max_entries: int = 5,
) -> list[NPCDialogueEntry]:
    """Get dialogue history for a specific NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID
        max_entries: Maximum number of entries to return
        
    Returns:
        List of dialogue entries
    """
    session_states = _get_session_npc_states(session_id)
    
    if npc_id not in session_states:
        return []
    
    return session_states[npc_id].get_recent_history(max_entries)


def get_npc_dialogue_count(
    npc_id: str,
    session_id: str = "default-session",
) -> int:
    """Get the dialogue count for a specific NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID
        
    Returns:
        Number of dialogue interactions (0 if never spoken)
    """
    session_states = _get_session_npc_states(session_id)
    
    if npc_id not in session_states:
        return 0
    
    return session_states[npc_id].dialogue_count


def get_npc_dialogue_state(
    npc_id: str,
    session_id: str = "default-session",
) -> Optional[NPCDialogueState]:
    """Get the full dialogue state for a specific NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID
        
    Returns:
        The dialogue state or None if never interacted
    """
    session_states = _get_session_npc_states(session_id)
    return session_states.get(npc_id)


def build_dialogue_context_for_prompt(
    npc_id: str,
    npc_name: str,
    session_id: str = "default-session",
    max_entries: int = 5,
) -> str:
    """Build dialogue context string for prompt injection.
    
    Args:
        npc_id: The NPC's unique ID
        npc_name: The NPC's display name
        session_id: The session ID
        max_entries: Maximum number of history entries to include
        
    Returns:
        Formatted dialogue context string for prompt injection
    """
    state = get_npc_dialogue_state(npc_id, session_id)
    
    if state is None or state.dialogue_count == 0:
        return f"【NPC 对话状态 / NPC DIALOGUE STATE】\n这是玩家第一次与 {npc_name} 接触。NPC 还不认识玩家。\n"
    
    lines = [f"【NPC 对话状态 / NPC DIALOGUE STATE】"]
    lines.append(f"玩家与 {npc_name} 的对话次数: {state.dialogue_count}")
    lines.append("")
    lines.append("最近的对话历史 / Recent Dialogue History:")
    
    for entry in state.get_recent_history(max_entries):
        lines.append(f"  - {entry.to_prompt_line()}")
    
    lines.append("")
    lines.append(f"叙事指引: NPC 应该记得之前的对话内容，体现对话的连贯性。")
    lines.append("")
    
    return "\n".join(lines)


def reset_session_npc_states(session_id: str) -> None:
    """Reset all NPC dialogue states for a session.
    
    Called when a session is reset.
    """
    if session_id in _npc_dialogue_states:
        del _npc_dialogue_states[session_id]


def get_all_npc_dialogue_counts(
    session_id: str = "default-session",
) -> dict[str, int]:
    """Get dialogue counts for all NPCs in a session.
    
    Args:
        session_id: The session ID
        
    Returns:
        Dict mapping NPC IDs to dialogue counts
    """
    session_states = _get_session_npc_states(session_id)
    return {
        npc_id: state.dialogue_count 
        for npc_id, state in session_states.items()
    }


def get_all_npc_dialogue_states(
    session_id: str = "default-session",
) -> dict[str, NPCDialogueState]:
    """Get all NPC dialogue states for a session.
    
    Args:
        session_id: The session ID
        
    Returns:
        Dict mapping NPC IDs to their dialogue states
    """
    session_states = _get_session_npc_states(session_id)
    return dict(session_states)
