"""Action resolution engine.

Implements the V1 core loop step 2-3:
  GM judges whether the action is auto-success or needs a check,
  then the rules engine returns a structured result.

V1 Action Types:
- MOVE: Physical repositioning, can auto-succeed if trivial
- INTERACT: Object manipulation, usually needs check if contested/locked
- ATTACK: Hostile actions, always need attack roll vs AC
- SOCIAL: Influence attempts, always need check vs DC
- EXPLORE: Information gathering, usually needs check
"""

from __future__ import annotations

from ..models.action import (
    ActionRequest,
    ActionResponse,
    ActionType,
    CheckDetail,
    Effect,
    Outcome,
    ResolutionType,
)
from ..state import get_actor, get_scene
from .dice import roll_d20

# ---------------------------------------------------------------------------
# DC tiers (rules-core: "先压缩成少量稳定档位，例如 10 / 15 / 20")
# ---------------------------------------------------------------------------

DC_EASY = 10
DC_MEDIUM = 15
DC_HARD = 20

# ---------------------------------------------------------------------------
# Action Type Classification Keywords
# ---------------------------------------------------------------------------

_ACTION_TYPE_KEYWORDS: dict[ActionType, list[str]] = {
    ActionType.MOVE: [
        "walk", "run", "move", "go to", "approach", "retreat", "flee",
        "climb", "jump", "leap", "swim", "crawl", "sneak", "hide",
    ],
    ActionType.ATTACK: [
        "attack", "strike", "hit", "shoot", "stab", "slash", "punch",
        "kick", "shoot", "fire", "throw", "cast", "spell", "harm",
        "fight", "charge", "ambush", "backstab", "sneak attack",
    ],
    ActionType.SOCIAL: [
        "persuade", "convince", "deceive", "lie", "bluff", "intimidate",
        "threaten", "charm", "negotiate", "bargain", "ask", "question",
        "interrogate", "seduce", "mock", "taunt", "insult", "compliment",
        "befriend", "recruit", "calm", "soothe", "persuation",
    ],
    ActionType.EXPLORE: [
        "search", "investigate", "examine", "inspect", "look for",
        "listen", "spot", "perceive", "sense", "scout", "track",
        "find", "locate", "discover", "check for", "look around",
        "study", "analyze", "observe", "watch",
    ],
    ActionType.INTERACT: [
        "open", "close", "pick up", "put down", "grab", "take",
        "use", "activate", "pull", "push", "lift", "carry", "drop",
        "unlock", "lock", "disarm", "trigger", "place", "give",
        "drink", "eat", "consume", "read", "write", "draw",
    ],
}

# ---------------------------------------------------------------------------
# Auto-success rules by action type
# ---------------------------------------------------------------------------

# MOVE actions that are trivial and auto-succeed
_MOVE_AUTO_PHRASES = [
    "walk to", "walk over", "move to", "go to",
    "stand up", "sit down", "turn around",
]

# INTERACT actions that are trivial and auto-succeed
_INTERACT_AUTO_PHRASES = [
    "pick up", "put down", "drop", "hold",
]

# EXPLORE actions that are trivial (basic perception without searching)
_EXPLORE_AUTO_PHRASES = [
    "look around", "look at", "glance",
]

# Words that disqualify an action from auto-success
_AUTO_SUCCESS_DISQUALIFIERS = [
    "locked", "trapped", "guard", "convince", "persuade", "deceive",
    "lie", "trick", "sneak", "steal", "force", "break", "dangerous",
    "difficult", "careful", "secret", "hidden", "enemy", "hostile",
    "opponent", "combat", "battle", "fight", "opposed", "resist",
]

# ---------------------------------------------------------------------------
# Ability inference by action type and keywords
# ---------------------------------------------------------------------------

_ABILITY_HINTS_BY_TYPE: dict[ActionType, dict[str, list[str]]] = {
    ActionType.MOVE: {
        "str": ["climb", "jump", "swim", "force", "break", "swim"],
        "dex": ["sneak", "hide", "tumble", "acrobatic", "quietly"],
        "con": ["endure", "march", "sustain", "long distance"],
    },
    ActionType.ATTACK: {
        "str": ["melee", "slash", "stab", "punch", "kick", "grapple", "shove", "force"],
        "dex": ["shoot", "fire", "throw", "ranged", "bow", "crossbow", "sneak attack"],
        "int": ["spell", "magic", "arcane", "fireball", "lightning"],
        "wis": ["divine", "sacred", "nature", "spiritual"],
        "cha": ["charm", "dominate", "fear", "illusion"],
    },
    ActionType.SOCIAL: {
        "cha": ["persuade", "deceive", "lie", "bluff", "intimidate", "charm", "seduce", "mock", "taunt"],
        "int": ["negotiate", "bargain", "logic", "reason", "debate"],
        "wis": ["insight", "empathize", "read", "calm", "counsel"],
    },
    ActionType.EXPLORE: {
        "int": ["investigate", "examine", "inspect", "study", "analyze", "search"],
        "wis": ["perceive", "sense", "spot", "listen", "feel", "intuit", "track"],
        "dex": ["sneak", "hide", "move silently"],
    },
    ActionType.INTERACT: {
        "str": ["force", "break", "pry", "lift", "push", "pull", "bend"],
        "dex": ["pick", "disarm", "juggle", "manipulate", "delicate"],
        "int": ["decipher", "decode", "puzzle", "mechanism", "device"],
    },
}

# Default ability by action type
_DEFAULT_ABILITY_BY_TYPE: dict[ActionType, str] = {
    ActionType.MOVE: "dex",
    ActionType.ATTACK: "str",
    ActionType.SOCIAL: "cha",
    ActionType.EXPLORE: "wis",
    ActionType.INTERACT: "dex",
    ActionType.UNKNOWN: "str",
}

# ---------------------------------------------------------------------------
# Classification Functions
# ---------------------------------------------------------------------------

def classify_action_type(intent: str, approach: str) -> ActionType:
    """Classify the action type from intent and approach text.
    
    Priority: ATTACK > SOCIAL > EXPLORE > INTERACT > MOVE
    (More specific types are checked first)
    """
    text = f"{intent} {approach}".lower()
    
    # Check in order of specificity (attacks and social are most distinct)
    for action_type in [ActionType.ATTACK, ActionType.SOCIAL, ActionType.EXPLORE, 
                        ActionType.INTERACT, ActionType.MOVE]:
        keywords = _ACTION_TYPE_KEYWORDS.get(action_type, [])
        if any(kw in text for kw in keywords):
            return action_type
    
    return ActionType.UNKNOWN


# ---------------------------------------------------------------------------
# Resolution Rules by Action Type
# ---------------------------------------------------------------------------

def _is_auto_success(action_type: ActionType, intent: str, approach: str) -> bool:
    """Return True only for genuinely trivial, zero-risk actions.
    
    Auto-success rules by type:
    - MOVE: Basic movement without obstacles
    - INTERACT: Simple object manipulation (uncontested, unlocked)
    - EXPLORE: Casual observation without focused search
    - ATTACK: Never auto-success
    - SOCIAL: Never auto-success (always involves another will)
    """
    text = f"{intent} {approach}".lower()
    
    # ATTACK and SOCIAL never auto-succeed
    if action_type in (ActionType.ATTACK, ActionType.SOCIAL):
        return False
    
    # Check for disqualifiers first
    has_disqualifier = any(dq in text for dq in _AUTO_SUCCESS_DISQUALIFIERS)
    if has_disqualifier:
        return False
    
    # MOVE auto-success check
    if action_type == ActionType.MOVE:
        return any(phrase in text for phrase in _MOVE_AUTO_PHRASES)
    
    # INTERACT auto-success check
    if action_type == ActionType.INTERACT:
        return any(phrase in text for phrase in _INTERACT_AUTO_PHRASES)
    
    # EXPLORE auto-success check
    if action_type == ActionType.EXPLORE:
        return any(phrase in text for phrase in _EXPLORE_AUTO_PHRASES)
    
    # UNKNOWN defaults to no auto-success
    return False


def _infer_ability(action_type: ActionType, intent: str, approach: str) -> str:
    """Infer the most relevant ability based on action type and text."""
    text = f"{intent} {approach}".lower()
    
    # Get hints for this action type
    hints = _ABILITY_HINTS_BY_TYPE.get(action_type, {})
    
    # Check hints in priority order (primary abilities first)
    priority_order = ["cha", "wis", "int", "dex", "str", "con"]
    
    for ability in priority_order:
        keywords = hints.get(ability, [])
        if any(kw in text for kw in keywords):
            return ability
    
    # Fall back to default for this action type
    return _DEFAULT_ABILITY_BY_TYPE.get(action_type, "str")


def _pick_dc(action_type: ActionType, intent: str, approach: str) -> int:
    """Assign a DC tier based on action type and keyword heuristics."""
    text = f"{intent} {approach}".lower()
    
    # Hard keywords override everything
    if any(w in text for w in ["hard", "difficult", "dangerous", "impossible", 
                                "extreme", "master", "legendary"]):
        return DC_HARD
    
    # Easy keywords
    if any(w in text for w in ["easy", "simple", "trivial", "obvious", "clear"]):
        return DC_EASY
    
    # Type-specific DC adjustments
    if action_type == ActionType.ATTACK:
        # Attacks default to medium (AC-based), but special attacks might be harder
        if any(w in text for w in ["called shot", "precise", "disarm", "trip"]):
            return DC_HARD
        return DC_MEDIUM
    
    if action_type == ActionType.SOCIAL:
        # Social against hostile targets is harder
        if any(w in text for w in ["hostile", "angry", "enemy", "suspicious", "guards"]):
            return DC_HARD
        if any(w in text for w in ["friendly", "helpful", "ally", "friend"]):
            return DC_EASY
        return DC_MEDIUM
    
    if action_type == ActionType.EXPLORE:
        # Searching for hidden things
        if any(w in text for w in ["hidden", "secret", "concealed", "disguised"]):
            return DC_HARD
        return DC_MEDIUM
    
    if action_type == ActionType.INTERACT:
        # Locked/trapped objects
        if any(w in text for w in ["locked", "trapped", "complex", "magical", "rune"]):
            return DC_HARD
        if any(w in text for w in ["rusty", "old", "simple", "loose"]):
            return DC_EASY
        return DC_MEDIUM
    
    # Default to medium
    return DC_MEDIUM


# ---------------------------------------------------------------------------
# Effect Generation by Action Type
# ---------------------------------------------------------------------------

def _build_effects(
    *,
    action_type: ActionType,
    actor_id: str,
    scene_id: str,
    ability: str,
    outcome: Outcome,
    intent: str,
    approach: str,
) -> list[Effect]:
    """Build concrete, applyable effects based on action type and outcome."""
    effects: list[Effect] = []
    
    # Every check costs one abstract time tick
    effects.append(
        Effect(
            target=scene_id,
            field="time",
            delta=1,
            description="Time passes.",
        )
    )
    
    if outcome == Outcome.FAILURE:
        effects.extend(_build_failure_effects(action_type, actor_id, ability, intent, approach))
    else:
        effects.extend(_build_success_effects(action_type, actor_id, intent, approach))
    
    return effects


def _build_failure_effects(
    action_type: ActionType, 
    actor_id: str, 
    ability: str,
    intent: str,
    approach: str,
) -> list[Effect]:
    """Generate effects for failed actions based on type."""
    effects: list[Effect] = []
    text = f"{intent} {approach}".lower()
    
    if action_type == ActionType.ATTACK:
        # Failed attacks: no damage, possible exposure
        effects.append(
            Effect(
                target=actor_id,
                field="narrative_state",
                delta="exposed",
                description="The missed attack leaves you momentarily vulnerable.",
            )
        )
    
    elif action_type == ActionType.MOVE:
        # Failed movement: might cause falling, noise, or exhaustion
        if any(w in text for w in ["climb", "jump", "leap"]):
            effects.append(
                Effect(
                    target=actor_id,
                    field="hp",
                    delta=-2,
                    description="A fall or stumble causes minor injury.",
                )
            )
        else:
            effects.append(
                Effect(
                    target=actor_id,
                    field="narrative_state",
                    delta="noisy",
                    description="The failed movement makes unwanted noise.",
                )
            )
    
    elif action_type == ActionType.SOCIAL:
        # Failed social: relationship damage, suspicion
        effects.append(
            Effect(
                target=actor_id,
                field="narrative_state",
                delta="suspicious",
                description="The failed social attempt creates tension or suspicion.",
            )
        )
    
    elif action_type == ActionType.EXPLORE:
        # Failed exploration: time waste, missed opportunity
        effects.append(
            Effect(
                target=actor_id,
                field="narrative_state",
                delta="confused",
                description="The search yields nothing useful.",
            )
        )
    
    elif action_type == ActionType.INTERACT:
        # Failed interaction: might break object, trigger trap, or hurt self
        if any(w in text for w in ["lock", "trap", "delicate", "fragile"]):
            effects.append(
                Effect(
                    target=actor_id,
                    field="hp",
                    delta=-1,
                    description="A slip damages you or the object.",
                )
            )
        else:
            effects.append(
                Effect(
                    target=actor_id,
                    field="narrative_state",
                    delta="frustrated",
                    description="The object remains uncooperative.",
                )
            )
    
    # Physical exertion failure causes minor harm
    if ability in ("str", "dex", "con") and action_type != ActionType.ATTACK:
        effects.append(
            Effect(
                target=actor_id,
                field="hp",
                delta=-1,
                description="The failed physical effort causes minor harm.",
            )
        )
    
    return effects


def _build_success_effects(
    action_type: ActionType, 
    actor_id: str,
    intent: str,
    approach: str,
) -> list[Effect]:
    """Generate effects for successful actions based on type."""
    effects: list[Effect] = []
    text = f"{intent} {approach}".lower()
    
    if action_type == ActionType.ATTACK:
        # Successful attacks deal damage
        damage = 3  # Base damage for V1
        if any(w in text for w in ["powerful", "heavy", "strong", "mighty"]):
            damage = 5
        elif any(w in text for w in ["weak", "light", "quick", "fast"]):
            damage = 2
        
        effects.append(
            Effect(
                target="target",  # Placeholder - real target would be specified
                field="hp",
                delta=-damage,
                description=f"The attack hits and deals {damage} damage.",
            )
        )
    
    elif action_type == ActionType.MOVE:
        # Successful movement may grant positioning advantage
        if any(w in text for w in ["sneak", "hide", "quietly", "silently"]):
            effects.append(
                Effect(
                    target=actor_id,
                    field="narrative_state",
                    delta="hidden",
                    description="You move into a concealed position.",
                )
            )
    
    elif action_type == ActionType.SOCIAL:
        # Successful social: relationship improvement, information gained
        effects.append(
            Effect(
                target=actor_id,
                field="narrative_state",
                delta="influential",
                description="Your words have the desired effect.",
            )
        )
    
    elif action_type == ActionType.EXPLORE:
        # Successful exploration: information gained
        effects.append(
            Effect(
                target=actor_id,
                field="narrative_state",
                delta="informed",
                description="You discover useful information.",
            )
        )
    
    elif action_type == ActionType.INTERACT:
        # Successful interaction: object state changed
        if any(w in text for w in ["unlock", "pick", "disarm"]):
            effects.append(
                Effect(
                    target="scene",
                    field="narrative_state",
                    delta="unlocked",
                    description="The mechanism yields to your skill.",
                )
            )
    
    return effects


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

def _build_narration(
    action_summary: str, 
    action_type: ActionType,
    outcome: Outcome,
    check: CheckDetail | None,
) -> str:
    """Generate a contextual narration based on action type and outcome."""
    type_names = {
        ActionType.MOVE: "movement",
        ActionType.ATTACK: "attack",
        ActionType.SOCIAL: "social attempt",
        ActionType.EXPLORE: "exploration",
        ActionType.INTERACT: "interaction",
        ActionType.UNKNOWN: "action",
    }
    
    type_name = type_names.get(action_type, "action")
    
    if outcome == Outcome.SUCCESS:
        if check:
            return f"{action_summary} — your {type_name} succeeds (rolled {check.total} vs DC {check.dc})."
        return f"{action_summary} — the {type_name} succeeds without difficulty."
    else:
        if check:
            return f"{action_summary} — the {type_name} fails (rolled {check.total} vs DC {check.dc})."
        return f"{action_summary} — but the {type_name} doesn't go as planned."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_action(req: ActionRequest) -> ActionResponse:
    """Resolve a player action into a structured result.

    Flow:
      1. Classify action type (or use provided)
      2. Determine if auto-success or check needed (type-specific rules)
      3. If check: roll d20 + modifier + proficiency vs DC
      4. Build type-specific effects and narration
    """
    action_summary = f"{req.actor} attempts to {req.intent} by {req.approach}"
    
    # Step 1: Classify action type
    action_type = req.action_type or classify_action_type(req.intent, req.approach)
    
    # Step 2: Check auto-success (type-specific rules)
    if _is_auto_success(action_type, req.intent, req.approach):
        return ActionResponse(
            action_summary=action_summary,
            action_type=action_type,
            resolution_type=ResolutionType.AUTO_SUCCESS,
            check=None,
            outcome=Outcome.SUCCESS,
            effects=[],
            narration=_build_narration(action_summary, action_type, Outcome.SUCCESS, None),
        )

    # Step 3: Check path
    actor = get_actor()
    scene = get_scene()
    ability = req.ability or _infer_ability(action_type, req.intent, req.approach)
    modifier = actor.abilities.modifier(ability)
    prof = actor.proficiency_bonus
    dc = req.dc or _pick_dc(action_type, req.intent, req.approach)
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

    # Step 4: Build type-specific effects
    effects: list[Effect] = _build_effects(
        action_type=action_type,
        actor_id=actor.id,
        scene_id=scene.id,
        ability=ability,
        outcome=outcome,
        intent=req.intent,
        approach=req.approach,
    )

    return ActionResponse(
        action_summary=action_summary,
        action_type=action_type,
        resolution_type=ResolutionType.CHECK,
        check=check,
        outcome=outcome,
        effects=effects,
        narration=_build_narration(action_summary, action_type, outcome, check),
    )
