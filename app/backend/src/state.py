"""Mutable in-memory state store for the V1 prototype.

Provides a single actor and scene whose fields can be mutated by
action effects.  ``apply_effects`` is the only write path — all
mutations go through the same Effect model returned by the resolver.

This module will eventually be replaced by proper session / persistence.
"""

from __future__ import annotations

from typing import Optional

from .models.action import Effect
from .models.state import (
    AbilityScores,
    Actor,
    BootstrapState,
    CharacterClass,
    CharacterCreateRequest,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
)

# ---------------------------------------------------------------------------
# Initial data (used to build the first mutable copies)
# ---------------------------------------------------------------------------

_CHARACTER_CREATION_SCENE_INIT = dict(
    id="character-creation-01",
    name="命运启程",
    description=(
        "你站在冒险开始前的门槛上。先决定自己的姓名、道路与天赋，"
        "随后故事才会真正展开。"
    ),
    actors=[],
)

_ADVENTURE_SCENE_INIT = dict(
    id="tavern-01",
    name="The Rusty Lantern",
    description=(
        "A dimly-lit tavern at a crossroads village. The smell of stale ale "
        "mixes with wood smoke. A few locals nurse their drinks in silence."
    ),
    actors=[],
)

_CLASS_TEMPLATES: dict[CharacterClass, dict[str, object]] = {
    CharacterClass.WARRIOR: {
        "description": "A disciplined frontline warrior who trusts steel and grit.",
        "abilities": AbilityScores(**{
            "str": 15,
            "dex": 13,
            "con": 14,
            "int": 8,
            "wis": 12,
            "cha": 10,
        }),
        "hp": 12,
        "ac": 16,
    },
    CharacterClass.MAGE: {
        "description": "A learned spellcaster who shapes danger with study and will.",
        "abilities": AbilityScores(**{
            "str": 8,
            "dex": 13,
            "con": 12,
            "int": 15,
            "wis": 14,
            "cha": 10,
        }),
        "hp": 8,
        "ac": 12,
    },
    CharacterClass.ROGUE: {
        "description": "A quick-footed opportunist who survives by timing and nerve.",
        "abilities": AbilityScores(**{
            "str": 10,
            "dex": 15,
            "con": 13,
            "int": 12,
            "wis": 14,
            "cha": 8,
        }),
        "hp": 10,
        "ac": 14,
    },
}

# A simple enemy for combat testing
_ENEMY_INIT = dict(
    id="goblin-01",
    name="Goblin Scout",
    abilities=AbilityScores(**{
        "str": 8,
        "dex": 14,
        "con": 10,
        "int": 10,
        "wis": 8,
        "cha": 8,
    }),
    proficiency_bonus=2,
    hp=7,
    hp_max=7,
    ac=12,  # Leather armor + DEX
    description="A small, wiry goblin with a rusty dagger.",
)

# Combat scene with enemy
_COMBAT_SCENE_INIT = dict(
    id="combat-01",
    name="Forest Ambush",
    description="A narrow forest path. A goblin emerges from the underbrush.",
    actors=["goblin-01"],
)

# ---------------------------------------------------------------------------
# Mutable singletons
# ---------------------------------------------------------------------------

_phase: GamePhase = GamePhase.CHARACTER_CREATION
_actor: Actor | None = None
_enemy: Actor = Actor(**_ENEMY_INIT)
_scene: Scene = Scene(**_CHARACTER_CREATION_SCENE_INIT)
_narrative_history: list[NarrativeHistoryEntry] = []


MAX_STORED_NARRATIVE_HISTORY = 50
DEFAULT_PROMPT_HISTORY_ENTRIES = 5
DEFAULT_PROMPT_HISTORY_CHARS = 1800


def get_bootstrap_state() -> BootstrapState:
    """Return the current (live) actor and scene."""
    return BootstrapState(
        phase=_phase,
        actor=_actor,
        scene=_scene,
        narrative_history=list(_narrative_history),
    )


def get_actor() -> Actor | None:
    return _actor


def get_enemy() -> Actor:
    """Get the enemy actor (for combat testing)."""
    return _enemy


def get_actor_by_id_or_name(target: str) -> Optional[Actor]:
    """Find an actor by ID or name (case-insensitive)."""
    target_lower = target.lower()
    for actor in [_actor, _enemy]:
        if actor is None:
            continue
        if actor.id.lower() == target_lower or actor.name.lower() == target_lower:
            return actor
    return None


def get_scene() -> Scene:
    return _scene


def get_narrative_history() -> list[NarrativeHistoryEntry]:
    """Return the full narrative history for the current in-memory session."""
    return list(_narrative_history)


def append_narrative_history(entry: NarrativeHistoryEntry) -> None:
    """Append a narrative memory item and cap total in-memory growth."""
    global _narrative_history
    _narrative_history = [*_narrative_history, entry][-MAX_STORED_NARRATIVE_HISTORY:]


def get_narrative_context(
    max_entries: int = DEFAULT_PROMPT_HISTORY_ENTRIES,
    max_chars: int = DEFAULT_PROMPT_HISTORY_CHARS,
) -> list[NarrativeHistoryEntry]:
    """Return recent narrative history bounded for prompt injection."""
    selected: list[NarrativeHistoryEntry] = []
    current_chars = 0

    for entry in reversed(_narrative_history[-max_entries:]):
        entry_chars = len(entry.model_dump_json())
        if selected and current_chars + entry_chars > max_chars:
            break
        selected.append(entry)
        current_chars += entry_chars

    selected.reverse()
    return selected


def set_combat_scene() -> None:
    """Switch to combat scene with enemy present."""
    global _scene
    actors = ["goblin-01"]
    if _actor is not None:
        actors.insert(0, _actor.id)
    _scene = Scene(**{**_COMBAT_SCENE_INIT, "actors": actors})


def has_character() -> bool:
    return _actor is not None and _phase == GamePhase.ADVENTURE


def create_character(req: CharacterCreateRequest) -> BootstrapState:
    """Create the player's starting character and enter the opening scene."""
    global _actor, _phase, _scene, _narrative_history

    template = _CLASS_TEMPLATES[req.character_class]
    hp = int(template["hp"])
    actor_id = f"{req.character_class.value}-{req.name.strip().lower().replace(' ', '-')}"

    _actor = Actor(
        id=actor_id,
        name=req.name.strip(),
        character_class=req.character_class,
        abilities=template["abilities"],
        proficiency_bonus=2,
        hp=hp,
        hp_max=hp,
        ac=int(template["ac"]),
        description=str(template["description"]),
    )
    _phase = GamePhase.ADVENTURE
    _scene = Scene(**{**_ADVENTURE_SCENE_INIT, "actors": [_actor.id]})
    _narrative_history = []
    return get_bootstrap_state()


# ---------------------------------------------------------------------------
# Effect application
# ---------------------------------------------------------------------------

def apply_effects(effects: list[Effect]) -> None:
    """Apply a list of effects to the mutable state store.

    Silently skips effects whose target or field is not recognised so
    that the resolver can emit forward-looking effect types without
    breaking current state handling.
    """
    for eff in effects:
        _apply_one(eff)


def _apply_one(eff: Effect) -> None:
    global _actor, _enemy, _scene

    # --- actor-targeted effects ---
    if _actor is not None and eff.target in (_actor.id, _actor.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            _actor = _actor.model_copy(
                update={"hp": max(0, min(_actor.hp_max, _actor.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in _actor.conditions:
                _actor = _actor.model_copy(
                    update={"conditions": [*_actor.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            _actor = _actor.model_copy(
                update={
                    "conditions": [c for c in _actor.conditions if c != eff.delta],
                }
            )
        # unrecognised actor field — silently skip

    # --- enemy-targeted effects ---
    elif eff.target in (_enemy.id, _enemy.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            _enemy = _enemy.model_copy(
                update={"hp": max(0, min(_enemy.hp_max, _enemy.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in _enemy.conditions:
                _enemy = _enemy.model_copy(
                    update={"conditions": [*_enemy.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            _enemy = _enemy.model_copy(
                update={
                    "conditions": [c for c in _enemy.conditions if c != eff.delta],
                }
            )
        # unrecognised enemy field — silently skip

    # --- scene-targeted effects ---
    elif eff.target == _scene.id:
        if eff.field == "time" and isinstance(eff.delta, int):
            _scene = _scene.model_copy(
                update={"time": _scene.time + eff.delta}
            )


# ---------------------------------------------------------------------------
# Reset (for tests)
# ---------------------------------------------------------------------------

def reset_state() -> None:
    """Restore mutable state to its initial values."""
    global _phase, _actor, _enemy, _scene, _narrative_history
    _phase = GamePhase.CHARACTER_CREATION
    _actor = None
    _enemy = Actor(**_ENEMY_INIT)
    _scene = Scene(**_CHARACTER_CREATION_SCENE_INIT)
    _narrative_history = []
