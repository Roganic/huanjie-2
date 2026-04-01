"""Session-scoped persistence for combat state."""

from __future__ import annotations

from .models import CombatState


# In-memory combat state store keyed by session_id
_combat_states: dict[str, CombatState] = {}


def save_combat_state(state: CombatState) -> None:
    """Persist a combat state by session_id."""
    _combat_states[state.session_id] = state.model_copy(deep=True)


def load_combat_state(session_id: str) -> CombatState | None:
    """Load a persisted combat state by session_id."""
    state = _combat_states.get(session_id)
    if state is None:
        return None
    return state.model_copy(deep=True)


def clear_combat_state(session_id: str) -> None:
    """Remove a combat state from the store."""
    _combat_states.pop(session_id, None)


def reset_all_combat_states() -> None:
    """Clear all combat states (useful for testing)."""
    _combat_states.clear()
