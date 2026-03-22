"""Fixed bootstrap state for the V1 prototype.

Provides a single hardcoded actor and scene so that the frontend can
fetch initial game state from the backend instead of using local mocks.
This module will eventually be replaced by proper session / persistence.
"""

from __future__ import annotations

from .models.state import AbilityScores, Actor, BootstrapState, Scene

# ---------------------------------------------------------------------------
# Fixed actor — roughly a level-1 fighter-type character
# ---------------------------------------------------------------------------

BOOTSTRAP_ACTOR = Actor(
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

# ---------------------------------------------------------------------------
# Fixed scene — the classic starting tavern
# ---------------------------------------------------------------------------

BOOTSTRAP_SCENE = Scene(
    id="tavern-01",
    name="The Rusty Lantern",
    description=(
        "A dimly-lit tavern at a crossroads village. The smell of stale ale "
        "mixes with wood smoke. A few locals nurse their drinks in silence."
    ),
    actors=["aldric-01"],
)

# ---------------------------------------------------------------------------
# Composite bootstrap payload
# ---------------------------------------------------------------------------

BOOTSTRAP_STATE = BootstrapState(
    actor=BOOTSTRAP_ACTOR,
    scene=BOOTSTRAP_SCENE,
)


def get_bootstrap_state() -> BootstrapState:
    """Return the current bootstrap state.

    Trivial today; will become a lookup by session later.
    """
    return BOOTSTRAP_STATE
