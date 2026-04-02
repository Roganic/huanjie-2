"""Session memory management for narrative context.

This module provides functions for managing and summarizing session narrative
history to be included in AI narrative prompts.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models.state import NarrativeHistoryEntry

logger = logging.getLogger(__name__)

# Default number of recent history entries to include in prompts
DEFAULT_HISTORY_ENTRIES = 5


def get_recent_action_summaries(
    narrative_history: list[NarrativeHistoryEntry],
    max_entries: int = DEFAULT_HISTORY_ENTRIES,
) -> list[str]:
    """Extract recent action summaries from narrative history.
    
    Args:
        narrative_history: List of narrative history entries
        max_entries: Maximum number of entries to return (default: 5)
        
    Returns:
        List of action summary strings, most recent last
    """
    if not narrative_history:
        return []
    
    # Get the most recent entries
    recent_entries = narrative_history[-max_entries:]
    
    # Extract action summaries
    summaries = []
    for entry in recent_entries:
        if entry.action_summary:
            summaries.append(entry.action_summary)
    
    return summaries


def format_history_for_prompt(
    narrative_history: list[NarrativeHistoryEntry],
    max_entries: int = DEFAULT_HISTORY_ENTRIES,
) -> str:
    """Format narrative history for inclusion in AI prompts.
    
    Args:
        narrative_history: List of narrative history entries
        max_entries: Maximum number of entries to include
        
    Returns:
        Formatted history string for prompts
    """
    if not narrative_history:
        return "无历史记录。当前是本次会话中最早需要参考的动作。"
    
    lines = []
    recent_entries = narrative_history[-max_entries:]
    
    for idx, entry in enumerate(recent_entries, start=1):
        lines.append(f"{idx}. 行动: {entry.action_summary}")
        if entry.resolution_summary:
            outcome = entry.resolution_summary.get("outcome", "unknown")
            lines.append(f"   结果: {outcome}")
        if entry.narration_summary:
            # Truncate if too long
            summary = entry.narration_summary
            if len(summary) > 100:
                summary = summary[:97] + "..."
            lines.append(f"   叙事摘要: {summary}")
    
    return "\n".join(lines)


def log_history_context(
    narrative_history: list[NarrativeHistoryEntry],
    max_entries: int = DEFAULT_HISTORY_ENTRIES,
    scene_name: Optional[str] = None,
) -> None:
    """Log the history context being used for narrative generation.
    
    Args:
        narrative_history: List of narrative history entries
        max_entries: Maximum number of entries included
        scene_name: Optional current scene name for context
    """
    summaries = get_recent_action_summaries(narrative_history, max_entries)
    
    extra = {
        "history_count": len(narrative_history),
        "included_entries": len(summaries),
        "max_entries": max_entries,
        "action_summaries": summaries,
    }
    
    if scene_name:
        extra["scene_name"] = scene_name
    
    logger.info(
        "Session memory context prepared: %d entries from history, using last %d",
        len(narrative_history),
        len(summaries),
        extra=extra,
    )


def build_memory_context(
    narrative_history: list[NarrativeHistoryEntry],
    max_entries: int = DEFAULT_HISTORY_ENTRIES,
) -> dict:
    """Build a structured memory context for narrative generation.
    
    Args:
        narrative_history: List of narrative history entries
        max_entries: Maximum number of entries to include
        
    Returns:
        Dictionary with memory context data
    """
    summaries = get_recent_action_summaries(narrative_history, max_entries)
    
    return {
        "has_history": len(narrative_history) > 0,
        "total_entries": len(narrative_history),
        "recent_summaries": summaries,
        "formatted_history": format_history_for_prompt(narrative_history, max_entries),
    }
