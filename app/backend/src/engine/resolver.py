"""Action resolution engine.

Implements the V1 core loop step 2-3:
  GM judges whether the action is auto-success or needs a check,
  then the rules engine returns a structured result.
"""

from __future__ import annotations

from ..models.action import (
    ActionRequest,
    ActionResponse,
    CheckDetail,
    Effect,
    Outcome,
    ResolutionType,
)
from .dice import roll_d20

# ---------------------------------------------------------------------------
# Stub ability data — will be replaced by real character state later
# ---------------------------------------------------------------------------

DEFAULT_ABILITY_MODIFIERS: dict[str, int] = {
    "str": 2,
    "dex": 1,
    "con": 1,
    "int": 0,
    "wis": 1,
    "cha": -1,
}

DEFAULT_PROFICIENCY_BONUS = 2

# ---------------------------------------------------------------------------
# DC tiers (rules-core: "先压缩成少量稳定档位，例如 10 / 15 / 20")
# ---------------------------------------------------------------------------

DC_EASY = 10
DC_MEDIUM = 15
DC_HARD = 20

# ---------------------------------------------------------------------------
# Auto-success: only truly trivial, zero-risk actions skip the roll.
# Each phrase must be specific enough to avoid matching non-trivial variants
# like "open the locked chest" or "talk the guard into letting us pass".
# ---------------------------------------------------------------------------

AUTO_SUCCESS_PHRASES = [
    "look around",
    "look at",
    "walk to",
    "walk over",
    "sit down",
    "stand up",
    "put down",
    "pick up",        # picking up an uncontested item, not pick a lock
]

# If any of these words appear alongside a phrase match, the action is
# probably non-trivial and should NOT auto-succeed.
AUTO_SUCCESS_DISQUALIFIERS = [
    "locked", "trapped", "guard", "convince", "persuade", "deceive",
    "lie", "trick", "sneak", "steal", "force", "break", "dangerous",
    "difficult", "careful", "secret", "hidden",
]

# ---------------------------------------------------------------------------
# Simple ability inference from approach text
# ---------------------------------------------------------------------------

ABILITY_HINTS: dict[str, list[str]] = {
    "str": ["push", "lift", "force", "break", "climb", "grapple", "shove"],
    "dex": ["dodge", "sneak", "hide", "pick", "steal", "acrobat", "tumble"],
    "con": ["endure", "resist", "hold breath", "withstand", "tough"],
    "int": ["recall", "investigate", "analyze", "decipher", "study", "know"],
    "wis": ["perceive", "sense", "insight", "track", "notice", "spot", "listen"],
    "cha": ["persuade", "deceive", "intimidate", "perform", "charm", "bluff"],
}


def _infer_ability(approach: str) -> str:
    """Guess the most relevant ability from approach text."""
    lower = approach.lower()
    for ability, keywords in ABILITY_HINTS.items():
        for kw in keywords:
            if kw in lower:
                return ability
    return "str"


def _is_auto_success(intent: str, approach: str) -> bool:
    """Return True only for genuinely trivial, zero-risk actions.

    Requires a known trivial phrase AND the absence of any disqualifier
    that would indicate uncertainty or opposition.
    """
    lower = f"{intent} {approach}".lower()
    has_trivial_phrase = any(phrase in lower for phrase in AUTO_SUCCESS_PHRASES)
    if not has_trivial_phrase:
        return False
    has_disqualifier = any(dq in lower for dq in AUTO_SUCCESS_DISQUALIFIERS)
    return not has_disqualifier


def _pick_dc(intent: str) -> int:
    """Assign a DC tier based on simple keyword heuristics."""
    lower = intent.lower()
    if any(w in lower for w in ["hard", "difficult", "dangerous", "impossible"]):
        return DC_HARD
    if any(w in lower for w in ["careful", "tricky", "complex"]):
        return DC_MEDIUM
    return DC_MEDIUM  # default to medium


def _narration_stub(action_summary: str, outcome: Outcome) -> str:
    """Generate a minimal narration placeholder."""
    if outcome == Outcome.SUCCESS:
        return f"{action_summary} — and it works."
    return f"{action_summary} — but it doesn't go as planned."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_action(req: ActionRequest) -> ActionResponse:
    """Resolve a player action into a structured result.

    Flow:
      1. Determine if auto-success or check needed
      2. If check: roll d20 + modifier + proficiency vs DC
      3. Build structured response with narration stub
    """
    action_summary = f"{req.actor} attempts to {req.intent} by {req.approach}"

    # --- auto-success path ---
    if _is_auto_success(req.intent, req.approach):
        return ActionResponse(
            action_summary=action_summary,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            check=None,
            outcome=Outcome.SUCCESS,
            effects=[],
            narration=_narration_stub(action_summary, Outcome.SUCCESS),
        )

    # --- check path ---
    ability = req.ability or _infer_ability(req.approach)
    modifier = DEFAULT_ABILITY_MODIFIERS.get(ability, 0)
    prof = DEFAULT_PROFICIENCY_BONUS
    dc = req.dc or _pick_dc(req.intent)
    advantage = req.advantage

    roll = roll_d20(advantage)
    total = roll + modifier + prof
    outcome = Outcome.SUCCESS if total >= dc else Outcome.FAILURE

    check = CheckDetail(
        ability=ability,
        modifier=modifier,
        proficiency_bonus=prof,
        advantage=advantage,
        roll=roll,
        total=total,
        dc=dc,
    )

    effects: list[Effect] = []
    if outcome == Outcome.FAILURE:
        effects.append(
            Effect(
                target=req.actor,
                field="narrative_state",
                delta="setback",
                description="The failed attempt may attract attention or waste time.",
            )
        )

    return ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=check,
        outcome=outcome,
        effects=effects,
        narration=_narration_stub(action_summary, outcome),
    )
