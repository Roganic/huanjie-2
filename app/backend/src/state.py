"""Mutable in-memory state store for the V1 prototype.

Provides a single actor and scene whose fields can be mutated by
action effects.  ``apply_effects`` is the only write path — all
mutations go through the same Effect model returned by the resolver.

This module will eventually be replaced by proper session / persistence.
"""

from __future__ import annotations

from .models.action import Effect
from .models.state import AbilityScores, Actor, BootstrapState, Scene

# ---------------------------------------------------------------------------
# Initial data (used to build the first mutable copies)
# ---------------------------------------------------------------------------

_ACTOR_INIT = dict(
    id="aldric-01",
    name="Aldric",
    abilities=AbilityScores(**{
        "str": 16,
        "dex": 12,
        "con": 13,
        "int": 10,
        "wis": 12,
        "cha": 8,
    }),
    proficiency_bonus=2,
    hp=12,
    hp_max=12,
    description="A sturdy human sellsword with a practical outlook.",
)

_SCENE_INIT = dict(
    id="tavern-01",
    name="The Rusty Lantern",
    description=(
        "A dimly-lit tavern at a crossroads village. The smell of stale ale "
        "mixes with wood smoke. A few locals nurse their drinks in silence."
    ),
    actors=["aldric-01"],
)

# ---------------------------------------------------------------------------
# Mutable singletons
# ---------------------------------------------------------------------------

_actor: Actor = Actor(**_ACTOR_INIT)
_scene: Scene = Scene(**_SCENE_INIT)


def get_bootstrap_state() -> BootstrapState:
    """Return the current (live) actor and scene."""
    return BootstrapState(actor=_actor, scene=_scene)


def get_actor() -> Actor:
    return _actor


def get_scene() -> Scene:
    return _scene


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
    global _actor, _scene

    # --- actor-targeted effects ---
    if eff.target in (_actor.id, _actor.name):
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
    global _actor, _scene
    _actor = Actor(**_ACTOR_INIT)
    _scene = Scene(**_SCENE_INIT)
