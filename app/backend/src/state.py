"""Session-scoped mutable state store for the V1 prototype."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import uuid
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models.action import CombatState, Effect
from .scene import SceneData, get_default_exploration_scene, get_scene_by_id
from .models.state import (
    AbilityScores,
    Actor,
    AdventurePhase,
    BootstrapState,
    CharacterCard,
    CharacterClass,
    CharacterEquipped,
    CharacterCreateRequest,
    CharacterSkill,
    ClassFeatures,
    DEFAULT_ARMORS,
    DEFAULT_CONSUMABLES,
    DEFAULT_WEAPONS,
    EquippedItems,
    GamePhase,
    HP,
    InventoryItem,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
    Skill,
    SpellSlot,
)
from .npc.dialogue_state import (
    NPCDialogueState,
    get_all_npc_dialogue_counts,
    get_all_npc_dialogue_states,
    reset_session_npc_states,
)

_CHARACTER_CREATION_SCENE_INIT = dict(
    id="character-creation-01",
    name="命运启程",
    description=(
        "你站在冒险开始前的门槛上。先决定自己的姓名、道路与天赋，"
        "随后故事才会真正展开。"
    ),
    actors=[],
)

def _get_adventure_scene_init() -> dict:
    """Get the initial adventure scene with NPCs."""
    # Use new scene_map system for exits
    from .scene_map import get_default_scene_node, VILLAGE_SQUARE_NODE
    
    scene = get_default_exploration_scene()
    node = get_default_scene_node()
    
    result = {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
        "actors": [],
        "npcs": [npc.model_dump(mode="json") for npc in scene.npcs],
    }
    
    # Use new scene_map exits
    if node and node.exits:
        result["exits"] = [
            {"direction": exit_info.direction, "target_scene_id": exit_info.target_scene_id}
            for exit_info in node.exits
        ]
    else:
        result["exits"] = []
    
    return result


_ADVENTURE_SCENE_INIT = _get_adventure_scene_init()

_CLASS_TEMPLATES: dict[CharacterClass, dict[str, object]] = {
    CharacterClass.WARRIOR: {
        "description": "久经沙场的前线战士，信奉钢铁与意志。",
        "abilities": AbilityScores(**{
            "str": 15,
            "dex": 13,
            "con": 14,
            "int": 8,
            "wis": 12,
            "cha": 10,
        }),
        "hp": 10,
        "ac": 16,
    },
    CharacterClass.MAGE: {
        "description": "博学的施法者，以知识和意志驾驭危险。",
        "abilities": AbilityScores(**{
            "str": 8,
            "dex": 13,
            "con": 12,
            "int": 15,
            "wis": 14,
            "cha": 10,
        }),
        "hp": 6,
        "ac": 12,
    },
    CharacterClass.ROGUE: {
        "description": "身手敏捷的机会主义者，靠时机与神经存活。",
        "abilities": AbilityScores(**{
            "str": 10,
            "dex": 15,
            "con": 13,
            "int": 12,
            "wis": 14,
            "cha": 8,
        }),
        "hp": 8,
        "ac": 14,
    },
}

_SKILL_DEFINITIONS: list[dict[str, str]] = [
    {"name": "athletics", "ability": "str"},
    {"name": "acrobatics", "ability": "dex"},
    {"name": "sleight_of_hand", "ability": "dex"},
    {"name": "stealth", "ability": "dex"},
    {"name": "arcana", "ability": "int"},
    {"name": "history", "ability": "int"},
    {"name": "investigation", "ability": "int"},
    {"name": "nature", "ability": "int"},
    {"name": "religion", "ability": "int"},
    {"name": "animal_handling", "ability": "wis"},
    {"name": "insight", "ability": "wis"},
    {"name": "medicine", "ability": "wis"},
    {"name": "perception", "ability": "wis"},
    {"name": "survival", "ability": "wis"},
    {"name": "deception", "ability": "cha"},
    {"name": "intimidation", "ability": "cha"},
    {"name": "performance", "ability": "cha"},
    {"name": "persuasion", "ability": "cha"},
]

_CLASS_SKILL_PROFICIENCIES: dict[CharacterClass, set[str]] = {
    CharacterClass.WARRIOR: {"athletics", "intimidation", "perception", "survival"},
    CharacterClass.MAGE: {"arcana", "history", "investigation", "insight"},
    CharacterClass.ROGUE: {"acrobatics", "sleight_of_hand", "stealth", "deception", "persuasion"},
}

_ENEMY_INIT = dict(
    id="goblin-01",
    name="哥布林斥候",
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
    ac=12,
    description="一只瘦小的哥布林，手持锈迹斑斑的匕首。",
)

_COMBAT_SCENE_INIT = dict(
    id="combat-01",
    name="森林伏击",
    description="狭窄的林间小道，一只哥布林从灌木丛中窜出。",
    actors=["goblin-01"],
)

MAX_STORED_NARRATIVE_HISTORY = 50
MAX_SCENE_HISTORY = 10
DEFAULT_PROMPT_HISTORY_ENTRIES = 5
DEFAULT_PROMPT_HISTORY_CHARS = 1800
DEFAULT_SESSION_ID = "default-session"
SESSION_TTL_SECONDS = max(60, int(os.getenv("SESSION_TTL_SECONDS", "43200")))
SESSION_STORE_DIR = Path(
    os.getenv("SESSION_STATE_DIR", Path(tempfile.gettempdir()) / "huanjie-2-sessions")
)
SESSION_STORE_DIR.mkdir(parents=True, exist_ok=True)

_CURRENT_SESSION_ID: ContextVar[str | None] = ContextVar("current_session_id", default=None)
_SESSION_LOCK = threading.RLock()

# Module-level combat state for agent orchestration
_combat_state: CombatState | None = None


def get_combat_state() -> CombatState:
    global _combat_state
    if _combat_state is None:
        _combat_state = CombatState()
    return _combat_state


def start_combat_session() -> None:
    global _combat_state
    _combat_state = CombatState(is_active=True)


def end_combat_session(outcome: str) -> None:
    global _combat_state
    if _combat_state is not None:
        _combat_state.is_active = False
        _combat_state.combat_ended = True
        _combat_state.outcome = outcome


def advance_combat_round() -> None:
    global _combat_state
    if _combat_state is not None:
        _combat_state.round_number += 1


def update_combatant_hp(combatant_id: str, hp: int) -> None:
    global _combat_state
    if _combat_state is None:
        _combat_state = CombatState()
    _combat_state.combatant_hp[combatant_id] = hp


class SessionData(BaseModel):
    session_id: str
    phase: GamePhase = GamePhase.CHARACTER_CREATION
    game_phase: AdventurePhase = AdventurePhase.EXPLORATION
    actor: Actor | None = None
    enemy: Actor = Field(default_factory=lambda: Actor(**_ENEMY_INIT))
    scene: Scene = Field(default_factory=lambda: Scene(**_CHARACTER_CREATION_SCENE_INIT))
    narrative_history: list[NarrativeHistoryEntry] = Field(default_factory=list)
    scene_history: list[SceneHistoryEntry] = Field(default_factory=list)
    npc_dialogue_states: dict[str, NPCDialogueState] = Field(
        default_factory=dict,
        description="NPC dialogue states by NPC ID"
    )
    explored_nodes: list[str] = Field(
        default_factory=list,
        description="List of scene IDs that have been explored by the player"
    )
    updated_at: float = Field(default_factory=time.time)


_sessions: dict[str, SessionData] = {}


def set_current_session(session_id: str) -> Token[str | None]:
    return _CURRENT_SESSION_ID.set(session_id)


def reset_current_session(token: Token[str | None]) -> None:
    _CURRENT_SESSION_ID.reset(token)


def create_session() -> BootstrapState:
    session_id = uuid.uuid4().hex
    with _SESSION_LOCK:
        session = _create_fresh_session(session_id)
        _sessions[session_id] = session
        _persist_session(session)
    return _bootstrap_from_session(session)


def session_exists(session_id: str) -> bool:
    try:
        _get_session(session_id, create_if_missing=False)
    except KeyError:
        return False
    return True


def get_bootstrap_state(session_id: str | None = None) -> BootstrapState:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return _bootstrap_from_session(session)


def require_bootstrap_state(session_id: str) -> BootstrapState:
    session = _get_session(session_id, create_if_missing=False)
    return _bootstrap_from_session(session)


def get_actor(session_id: str | None = None) -> Actor | None:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).actor


def get_enemy(session_id: str | None = None) -> Actor:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).enemy


def get_actor_by_id_or_name(target: str, session_id: str | None = None) -> Optional[Actor]:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    target_lower = target.lower()
    for actor in [session.actor, session.enemy]:
        if actor is None:
            continue
        if actor.id.lower() == target_lower or actor.name.lower() == target_lower:
            return actor
    return None


def get_scene(session_id: str | None = None) -> Scene:
    return _get_session(_resolve_session_id(session_id), create_if_missing=True).scene


def get_narrative_history(session_id: str | None = None) -> list[NarrativeHistoryEntry]:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return list(session.narrative_history)


def get_scene_history(session_id: str | None = None) -> list[SceneHistoryEntry]:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return list(session.scene_history)


def append_scene_history(
    entry: SceneHistoryEntry,
    session_id: str | None = None,
) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        session.scene_history = [
            *session.scene_history,
            entry,
        ][-MAX_SCENE_HISTORY:]
        _save_session(session)


def append_narrative_history(
    entry: NarrativeHistoryEntry,
    session_id: str | None = None,
) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        session.narrative_history = [
            *session.narrative_history,
            entry,
        ][-MAX_STORED_NARRATIVE_HISTORY:]
        _save_session(session)
        
        # Persist to save file for session restoration after restart
        try:
            from . import game_state
            game_state.save_current_game(session_id=resolved_session_id)
        except Exception:
            # Don't fail action if save fails
            pass


def append_action_history(
    entry: dict,
    session_id: str | None = None,
) -> None:
    """Append an action to the narrative history.
    
    This is a simplified wrapper that creates a NarrativeHistoryEntry
    from a dictionary.
    """
    from datetime import datetime
    
    narrative_entry = NarrativeHistoryEntry(
        action_summary=entry.get("action", ""),
        resolution_summary={
            "result": entry.get("result", ""),
            "narrative_summary": entry.get("narrative_summary", ""),
        },
        narration_summary=entry.get("narrative_summary", ""),
        narration=entry.get("narrative_summary", ""),
        created_at=int(datetime.now().timestamp() * 1000),
    )
    append_narrative_history(narrative_entry, session_id)


def get_action_history(session_id: str | None = None) -> list[dict]:
    """Get action history for a session.
    
    Returns a list of action entries with action, result, and narrative_summary.
    """
    history = get_narrative_history(session_id=session_id)
    return [
        {
            "action": entry.action_summary,
            "result": entry.resolution_summary.get("result", ""),
            "narrative_summary": entry.narration_summary,
        }
        for entry in history
    ]


def get_narrative_context(
    max_entries: int = DEFAULT_PROMPT_HISTORY_ENTRIES,
    max_chars: int = DEFAULT_PROMPT_HISTORY_CHARS,
    session_id: str | None = None,
) -> list[NarrativeHistoryEntry]:
    history = get_narrative_history(session_id=session_id)
    selected: list[NarrativeHistoryEntry] = []
    current_chars = 0

    for entry in reversed(history[-max_entries:]):
        entry_chars = len(entry.model_dump_json())
        if selected and current_chars + entry_chars > max_chars:
            break
        selected.append(entry)
        current_chars += entry_chars

    selected.reverse()
    return selected


def set_combat_scene(session_id: str | None = None) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        actors = ["goblin-01"]
        if session.actor is not None:
            actors.insert(0, session.actor.id)
        # Use combat scene from scene system with NPCs
        from .scene import COMBAT_ENCOUNTER_SCENE
        session.scene = Scene(
            id=COMBAT_ENCOUNTER_SCENE.id,
            name=COMBAT_ENCOUNTER_SCENE.name,
            description=COMBAT_ENCOUNTER_SCENE.description,
            actors=actors,
            npcs=COMBAT_ENCOUNTER_SCENE.npcs,
            time=session.scene.time,  # Preserve time from previous scene
            exits=COMBAT_ENCOUNTER_SCENE.exits,
        )
        session.game_phase = AdventurePhase.COMBAT
        _save_session(session)


def set_exploration_phase(session_id: str | None = None) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        session.game_phase = AdventurePhase.EXPLORATION
        _save_session(session)


def switch_scene(scene_id: str, session_id: str | None = None) -> bool:
    """Switch to a different scene.
    
    Args:
        scene_id: The ID of the scene to switch to
        session_id: The session ID (uses current session if None)
        
    Returns:
        True if scene was switched, False if scene_id not found
    """
    from .scene import get_scene_by_id
    from .scene_map import get_scene_node
    
    scene_data = get_scene_by_id(scene_id)
    if scene_data is None:
        return False
    
    # Get scene node from new scene_map for exits
    scene_node = get_scene_node(scene_id)
    
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        # Preserve the player actor in the actors list
        actors = [session.actor.id] if session.actor else []
        
        # Get exits from scene_map node if available
        exits = scene_node.to_scene_exit_list() if scene_node else scene_data.exits
        
        session.scene = Scene(
            id=scene_data.id,
            name=scene_data.name,
            description=scene_data.description,
            actors=actors,
            npcs=scene_data.npcs,
            time=session.scene.time,  # Preserve time from previous scene
            exits=exits,  # Include exits for navigation
        )
        
        # Add new scene to explored nodes
        if scene_id not in session.explored_nodes:
            session.explored_nodes = [*session.explored_nodes, scene_id]
        
        _save_session(session)
    return True


def get_game_phase(session_id: str | None = None) -> AdventurePhase:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return session.game_phase


def check_and_update_combat_status(session_id: str | None = None) -> bool:
    """Check if combat should end (all enemies defeated) and update phase accordingly.
    
    Returns True if phase was changed to exploration (combat ended), False otherwise.
    """
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if session.game_phase != AdventurePhase.COMBAT:
            return False
        
        # Check if enemy is defeated (HP <= 0 or has 'defeated' condition)
        enemy_defeated = session.enemy.hp <= 0 or "defeated" in session.enemy.conditions
        
        if enemy_defeated:
            session.game_phase = AdventurePhase.EXPLORATION
            _save_session(session)
            return True
        return False


def has_character(session_id: str | None = None) -> bool:
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return session.actor is not None and session.phase == GamePhase.ADVENTURE


def _roll_4d6_drop_lowest() -> AbilityScores:
    """Roll 4d6, drop the lowest, repeat 6 times for ability scores."""
    import random

    def roll_one() -> int:
        rolls = sorted([random.randint(1, 6) for _ in range(4)])
        return sum(rolls[1:])  # Drop lowest

    return AbilityScores(**{
        "str": roll_one(),
        "dex": roll_one(),
        "con": roll_one(),
        "int": roll_one(),
        "wis": roll_one(),
        "cha": roll_one(),
    })


def _build_skills(abilities: AbilityScores, character_class: CharacterClass, proficiency_bonus: int) -> list[Skill]:
    proficiencies = _CLASS_SKILL_PROFICIENCIES.get(character_class, set())
    skills: list[Skill] = []
    for definition in _SKILL_DEFINITIONS:
        ability = definition["ability"]
        name = definition["name"]
        proficient = name in proficiencies
        ability_mod = abilities.modifier(ability)
        modifier = ability_mod + (proficiency_bonus if proficient else 0)
        skills.append(Skill(name=name, ability=ability, proficient=proficient, modifier=modifier))
    return skills


def _get_starting_equipment(character_class: CharacterClass) -> tuple[InventoryItem, InventoryItem]:
    """Get starting weapon and armor for a character class."""
    if character_class == CharacterClass.WARRIOR:
        weapon = InventoryItem.from_weapon(DEFAULT_WEAPONS["longsword"])
        armor = InventoryItem.from_armor(DEFAULT_ARMORS["chain_mail"])
    elif character_class == CharacterClass.MAGE:
        weapon = InventoryItem.from_weapon(DEFAULT_WEAPONS["quarterstaff"])
        armor = InventoryItem.from_armor(DEFAULT_ARMORS["robe"])
    else:  # ROGUE
        weapon = InventoryItem.from_weapon(DEFAULT_WEAPONS["shortsword"])
        armor = InventoryItem.from_armor(DEFAULT_ARMORS["leather"])
    return weapon, armor


def _calculate_ac_with_armor(abilities: AbilityScores, armor_item: InventoryItem | None) -> int:
    """Calculate AC based on equipped armor and abilities."""
    if armor_item is None:
        # Unarmored: 10 + DEX modifier
        return 10 + abilities.modifier("dex")
    
    base_ac = armor_item.base_ac or 10
    
    if not armor_item.add_dex_modifier:
        # Heavy armor: use base AC only
        return base_ac
    
    # Light/medium armor: add DEX modifier (with optional cap)
    dex_mod = abilities.modifier("dex")
    if armor_item.max_dex_bonus is not None:
        dex_mod = min(dex_mod, armor_item.max_dex_bonus)
    
    return base_ac + dex_mod


def create_character(
    req: CharacterCreateRequest,
    session_id: str | None = None,
) -> BootstrapState:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        template = _CLASS_TEMPLATES[req.character_class]
        base_hp = int(template["hp"])
        actor_id = f"{req.character_class.value}-{req.name.strip().lower().replace(' ', '-')}"

        # Determine ability scores based on generation method
        if req.ability_generation == "manual" and req.abilities is not None:
            abilities = req.abilities
        elif req.ability_generation == "random_4d6":
            abilities = _roll_4d6_drop_lowest()
        else:  # standard_array (default)
            abilities = template["abilities"]

        # Calculate HP: base + CON modifier
        con_mod = abilities.modifier("con")
        hp = base_hp + con_mod

        # Get starting equipment for the class
        weapon, armor = _get_starting_equipment(req.character_class)
        # Give every character a healing potion to start with
        potion = InventoryItem.from_consumable(DEFAULT_CONSUMABLES["healing_potion"])
        inventory = [weapon, armor, potion]
        equipped = EquippedItems(weapon=weapon, armor=armor)

        # Calculate AC based on equipped armor
        ac = _calculate_ac_with_armor(abilities, armor)

        skills = _build_skills(abilities, req.character_class, proficiency_bonus=2)

        # Initialize spell slots for mages (2 1st-level slots at level 1)
        spell_slots: list[SpellSlot] = []
        if req.character_class == CharacterClass.MAGE:
            spell_slots = [
                SpellSlot(level=1, max=2, current=2),
            ]

        # Initialize class features based on class
        class_features = ClassFeatures()
        if req.character_class == CharacterClass.WARRIOR:
            class_features = ClassFeatures(second_wind_used=False, action_surge_used=False)
        elif req.character_class == CharacterClass.ROGUE:
            class_features = ClassFeatures(sneak_attack_available=True)

        session.actor = Actor(
            id=actor_id,
            name=req.name.strip(),
            character_class=req.character_class,
            abilities=abilities,
            proficiency_bonus=2,
            level=1,
            experience_points=0,
            hp=hp,
            hp_max=hp,
            ac=ac,
            description=str(template["description"]),
            skills=skills,
            inventory=inventory,
            equipped=equipped,
            spell_slots=spell_slots,
            class_features=class_features,
        )
        session.phase = GamePhase.ADVENTURE
        # Initialize scene with NPCs from scene system
        scene_data = get_default_exploration_scene()
        session.scene = Scene(
            id=scene_data.id,
            name=scene_data.name,
            description=scene_data.description,
            actors=[session.actor.id],
            npcs=scene_data.npcs,
            exits=scene_data.exits,
        )
        session.enemy = Actor(**_ENEMY_INIT)
        session.narrative_history = []
        session.scene_history = []
        # Initialize explored nodes with current scene
        session.explored_nodes = [scene_data.id]
        _save_session(session)
        
        # Persist to save file for session restoration after restart
        try:
            from . import game_state
            game_state.save_current_game(session_id=resolved_session_id)
        except Exception:
            # Don't fail character creation if save fails
            pass
    return get_bootstrap_state(session_id=resolved_session_id)


def _inventory_item_to_dict(item: InventoryItem) -> dict:
    """Convert an inventory item to a dictionary for API response."""
    result = {
        "id": item.id,
        "name": item.name,
        "type": item.type.value,
        "description": item.description,
    }
    if item.damage_dice:
        result["damage_dice"] = item.damage_dice
    if item.attack_ability:
        result["attack_ability"] = item.attack_ability
    if item.base_ac is not None:
        result["base_ac"] = item.base_ac
    return result


def get_character_card(session_id: str | None = None) -> CharacterCard | None:
    actor = get_actor(session_id=session_id)
    if actor is None:
        return None
    
    # Build equipped items dict
    equipped_dict = CharacterEquipped()
    if actor.equipped.weapon:
        equipped_dict.weapon = _inventory_item_to_dict(actor.equipped.weapon)
    if actor.equipped.armor:
        equipped_dict.armor = _inventory_item_to_dict(actor.equipped.armor)
    
    # Build spell slots info
    spell_slots_info = [
        {"level": slot.level, "max": slot.max, "current": slot.current}
        for slot in actor.spell_slots
    ]

    return CharacterCard(
        name=actor.name,
        class_=actor.character_class.value if actor.character_class else "",
        level=actor.level,
        experience_points=actor.experience_points,
        proficiency_bonus=actor.proficiency_bonus,
        attributes={
            "str": {
                "score": actor.abilities.str_,
                "modifier": actor.abilities.modifier("str"),
            },
            "dex": {
                "score": actor.abilities.dex,
                "modifier": actor.abilities.modifier("dex"),
            },
            "con": {
                "score": actor.abilities.con,
                "modifier": actor.abilities.modifier("con"),
            },
            "int": {
                "score": actor.abilities.int_,
                "modifier": actor.abilities.modifier("int"),
            },
            "wis": {
                "score": actor.abilities.wis,
                "modifier": actor.abilities.modifier("wis"),
            },
            "cha": {
                "score": actor.abilities.cha,
                "modifier": actor.abilities.modifier("cha"),
            },
        },
        hp=HP(current=actor.hp, max=actor.hp_max),
        ac=actor.ac,
        skills=[
            CharacterSkill(
                name=skill.name,
                ability=skill.ability,
                proficient=skill.proficient,
                modifier=skill.modifier,
            )
            for skill in actor.skills
        ],
        inventory=[_inventory_item_to_dict(item) for item in actor.inventory],
        equipped=equipped_dict,
        spell_slots=spell_slots_info,
    )


def apply_effects(effects: list[Effect], session_id: str | None = None) -> None:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        for effect in effects:
            _apply_one(session, effect)
        _save_session(session)


def equip_item_for_actor(item_name: str, session_id: str | None = None) -> dict:
    """Equip an item from the actor's inventory.
    
    Args:
        item_name: The name of the item to equip
        session_id: The session ID (uses current session if None)
        
    Returns:
        A dictionary with the result:
        - success: True if equipped successfully
        - item: The equipped item info (if success)
        - previous_item: The previously equipped item (if any)
        - ac: The new AC value
        - error: Error message (if not success)
    """
    from .equipment import equip_item, ItemNotFoundError, InvalidItemTypeError
    
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if session.actor is None:
            return {"success": False, "error": "No character found"}
        
        try:
            updated_actor, equipped_item, previous_item = equip_item(session.actor, item_name)
            session.actor = updated_actor
            _save_session(session)
            
            # Persist to save file
            try:
                from . import game_state
                game_state.save_current_game(session_id=resolved_session_id)
            except Exception:
                pass
            
            return {
                "success": True,
                "item": {
                    "id": equipped_item.id,
                    "name": equipped_item.name,
                    "type": equipped_item.type.value,
                },
                "previous_item": {
                    "id": previous_item.id,
                    "name": previous_item.name,
                    "type": previous_item.type.value,
                } if previous_item else None,
                "ac": updated_actor.ac,
            }
        except ItemNotFoundError as e:
            return {"success": False, "error": str(e)}
        except InvalidItemTypeError as e:
            return {"success": False, "error": str(e)}


def unequip_item_from_actor(slot: str, session_id: str | None = None) -> dict:
    """Unequip an item from a specific slot.
    
    Args:
        slot: The slot to unequip ("weapon" or "armor")
        session_id: The session ID (uses current session if None)
        
    Returns:
        A dictionary with the result:
        - success: True if unequipped successfully
        - removed_item: The removed item info (if any)
        - ac: The new AC value
        - error: Error message (if not success)
    """
    from .equipment import unequip_item
    
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if session.actor is None:
            return {"success": False, "error": "No character found"}
        
        try:
            updated_actor, removed_item = unequip_item(session.actor, slot)
            session.actor = updated_actor
            _save_session(session)
            
            # Persist to save file
            try:
                from . import game_state
                game_state.save_current_game(session_id=resolved_session_id)
            except Exception:
                pass
            
            return {
                "success": True,
                "removed_item": {
                    "id": removed_item.id,
                    "name": removed_item.name,
                    "type": removed_item.type.value,
                } if removed_item else None,
                "ac": updated_actor.ac,
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}


def get_actor_equipment(session_id: str | None = None) -> dict:
    """Get the actor's current equipment information.
    
    Args:
        session_id: The session ID (uses current session if None)
        
    Returns:
        A dictionary with weapon and armor information
    """
    from .equipment import format_equipment_for_response
    
    actor = get_actor(session_id=session_id)
    if actor is None:
        return {"weapon": None, "armor": None}
    
    return format_equipment_for_response(actor)


def reset_state(session_id: str | None = None) -> BootstrapState:
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _create_fresh_session(resolved_session_id)
        _sessions[resolved_session_id] = session
        _persist_session(session)
        # Reset NPC dialogue states for the session
        reset_session_npc_states(resolved_session_id)
    return _bootstrap_from_session(session)


def _apply_one(session: SessionData, eff: Effect) -> None:
    actor = session.actor
    enemy = session.enemy
    scene = session.scene

    if actor is not None and eff.target in (actor.id, actor.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            session.actor = actor.model_copy(
                update={"hp": max(0, min(actor.hp_max, actor.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in actor.conditions:
                session.actor = actor.model_copy(
                    update={"conditions": [*actor.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            session.actor = actor.model_copy(
                update={"conditions": [c for c in actor.conditions if c != eff.delta]}
            )
        elif eff.field == "spell_slot_consumed" and isinstance(eff.delta, int):
            # Spell slot already consumed by spell resolver, this is just for tracking
            pass
        elif eff.field == "inventory_remove" and isinstance(eff.delta, str):
            # Remove consumed item from inventory
            if session.actor is not None:
                new_inventory = [
                    item for item in actor.inventory
                    if item.name.lower() != eff.delta.lower()
                ]
                session.actor = actor.model_copy(
                    update={"inventory": new_inventory}
                )
        elif eff.field == "spell_slots_restored":
            # Spell slots already restored by rest resolver, this is just for tracking
            pass
        return

    if eff.target in (enemy.id, enemy.name):
        if eff.field == "hp" and isinstance(eff.delta, int):
            session.enemy = enemy.model_copy(
                update={"hp": max(0, min(enemy.hp_max, enemy.hp + eff.delta))}
            )
        elif eff.field == "conditions_add" and isinstance(eff.delta, str):
            if eff.delta not in enemy.conditions:
                session.enemy = enemy.model_copy(
                    update={"conditions": [*enemy.conditions, eff.delta]}
                )
        elif eff.field == "conditions_remove" and isinstance(eff.delta, str):
            session.enemy = enemy.model_copy(
                update={"conditions": [c for c in enemy.conditions if c != eff.delta]}
            )
        return

    if eff.target == scene.id and eff.field == "time" and isinstance(eff.delta, int):
        session.scene = scene.model_copy(update={"time": scene.time + eff.delta})
        return

    if eff.target == scene.id and eff.field == "flags" and isinstance(eff.delta, str):
        if eff.delta not in scene.flags:
            session.scene = scene.model_copy(update={"flags": [*scene.flags, eff.delta]})
        return


def _bootstrap_from_session(session: SessionData) -> BootstrapState:
    # Build scene with NPC dialogue counts
    scene_npcs_with_counts = []
    for npc in session.scene.npcs:
        # Get dialogue count from session's npc_dialogue_states
        dialogue_count = 0
        if npc.id in session.npc_dialogue_states:
            dialogue_count = session.npc_dialogue_states[npc.id].dialogue_count
        # Create NPC copy with dialogue_count
        npc_with_count = npc.model_copy(update={"dialogue_count": dialogue_count})
        scene_npcs_with_counts.append(npc_with_count)
    
    # Create scene copy with updated NPCs
    scene_with_counts = session.scene.model_copy(update={"npcs": scene_npcs_with_counts})
    
    return BootstrapState(
        session_id=session.session_id,
        phase=session.phase,
        game_phase=session.game_phase,
        actor=session.actor,
        scene=scene_with_counts,
        narrative_history=list(session.narrative_history),
        scene_history=list(session.scene_history),
    )


def _resolve_session_id(session_id: str | None) -> str:
    return session_id or _CURRENT_SESSION_ID.get() or DEFAULT_SESSION_ID


def _session_file(session_id: str) -> Path:
    return SESSION_STORE_DIR / f"{session_id}.json"


def _create_fresh_session(session_id: str) -> SessionData:
    """Create a fresh session, with default character for default session (backward compatibility)."""
    session = SessionData(session_id=session_id)

    # For the default session, create the legacy Aldric character automatically
    # to maintain backward compatibility with tests that expect him to exist
    if session_id == DEFAULT_SESSION_ID:
        # Create Aldric with specific abilities matching legacy tests' expectations
        # CON 14 -> HP 12 (10 + 2), STR 16 -> +3 modifier
        abilities = AbilityScores(**{
            "str": 16, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 8,
        })
        actor_id = "aldric-01"
        con_mod = abilities.modifier("con")  # (14-10)//2 = 2
        hp = 10 + con_mod  # Warrior base 10 + CON mod = 12

        # Get starting equipment for warrior
        weapon, armor = _get_starting_equipment(CharacterClass.WARRIOR)
        potion = InventoryItem.from_consumable(DEFAULT_CONSUMABLES["healing_potion"])
        inventory = [weapon, armor, potion]
        equipped = EquippedItems(weapon=weapon, armor=armor)

        # Calculate AC based on equipped armor
        ac = _calculate_ac_with_armor(abilities, armor)

        # Build skills for warrior
        warrior_skills = _build_skills(abilities, CharacterClass.WARRIOR, proficiency_bonus=2)

        session.actor = Actor(
            id=actor_id,
            name="Aldric",
            character_class=CharacterClass.WARRIOR,
            abilities=abilities,
            proficiency_bonus=2,
            level=1,
            experience_points=0,
            hp=hp,
            hp_max=hp,
            ac=ac,
            description="久经沙场的前线战士，信奉钢铁与意志。",
            skills=warrior_skills,
            inventory=inventory,
            equipped=equipped,
            class_features=ClassFeatures(second_wind_used=False, action_surge_used=False),
        )
        session.phase = GamePhase.ADVENTURE
        # Scene with actor in actors list for backward compatibility
        scene_data = get_default_exploration_scene()
        session.scene = Scene(
            id=scene_data.id,
            name=scene_data.name,
            description=scene_data.description,
            actors=[actor_id],
            npcs=scene_data.npcs,
            exits=scene_data.exits,
        )
        # Initialize explored nodes for default session
        session.explored_nodes = [scene_data.id]

    return session


def _get_session(session_id: str, create_if_missing: bool) -> SessionData:
    with _SESSION_LOCK:
        session = _sessions.get(session_id)
        if session is None:
            session = _load_session(session_id)
            if session is not None:
                _sessions[session_id] = session

        if session is None:
            if not create_if_missing:
                raise KeyError(session_id)
            session = _create_fresh_session(session_id)
            _sessions[session_id] = session
            _persist_session(session)
            return session

        if _is_expired(session):
            _delete_session(session_id)
            if not create_if_missing:
                raise KeyError(session_id)
            session = _create_fresh_session(session_id)
            _sessions[session_id] = session
            _persist_session(session)
            return session

        session.updated_at = time.time()
        _persist_session(session)
        return session


def _load_session(session_id: str) -> SessionData | None:
    session_file = _session_file(session_id)
    if not session_file.exists():
        return None

    data = json.loads(session_file.read_text(encoding="utf-8"))
    session = SessionData.model_validate(data)
    if _is_expired(session):
        session_file.unlink(missing_ok=True)
        return None
    return session


def _save_session(session: SessionData) -> None:
    session.updated_at = time.time()
    _persist_session(session)


def _persist_session(session: SessionData) -> None:
    _session_file(session.session_id).write_text(
        json.dumps(
            session.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    _session_file(session_id).unlink(missing_ok=True)


def add_items_to_inventory(items: list[InventoryItem], session_id: str | None = None) -> None:
    """Add items to the actor's inventory."""
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if session.actor is not None:
            new_inventory = [*session.actor.inventory, *items]
            session.actor = session.actor.model_copy(update={"inventory": new_inventory})
        _save_session(session)


def remove_item_from_inventory(item_name: str, session_id: str | None = None) -> bool:
    """Remove an item from the actor's inventory by name.
    
    Returns True if an item was removed, False otherwise.
    """
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if session.actor is None:
            _save_session(session)
            return False
        new_inventory = [
            item for item in session.actor.inventory
            if item.name.lower() != item_name.lower()
        ]
        removed = len(new_inventory) < len(session.actor.inventory)
        session.actor = session.actor.model_copy(update={"inventory": new_inventory})
        _save_session(session)
        return removed


def use_second_wind(session_id: str | None = None) -> dict:
    """Use Second Wind class feature.
    
    Returns:
        Dict with success, hp_healed, new_hp, error
    """
    import random
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        actor = session.actor
        if actor is None:
            return {"success": False, "error": "No character found"}
        if actor.character_class != CharacterClass.WARRIOR:
            return {"success": False, "error": "Second Wind is only available to warriors"}
        if actor.class_features.second_wind_used:
            return {"success": False, "error": "Second Wind already used this rest"}
        
        # Heal: 1d10 + warrior level
        roll = random.randint(1, 10)
        hp_healed = roll + (actor.level or 1)
        new_hp = min(actor.hp_max, actor.hp + hp_healed)
        
        new_features = ClassFeatures(
            second_wind_used=True,
            action_surge_used=actor.class_features.action_surge_used,
            sneak_attack_available=actor.class_features.sneak_attack_available,
        )
        session.actor = actor.model_copy(
            update={"hp": new_hp, "class_features": new_features}
        )
        _save_session(session)
        return {
            "success": True,
            "hp_healed": hp_healed,
            "new_hp": new_hp,
            "roll": roll,
        }


def use_action_surge(session_id: str | None = None) -> dict:
    """Use Action Surge class feature.
    
    Returns:
        Dict with success, extra_action_available, error
    """
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        actor = session.actor
        if actor is None:
            return {"success": False, "error": "No character found"}
        if actor.character_class != CharacterClass.WARRIOR:
            return {"success": False, "error": "Action Surge is only available to warriors"}
        if actor.class_features.action_surge_used:
            return {"success": False, "error": "Action Surge already used this rest"}
        
        new_features = ClassFeatures(
            second_wind_used=actor.class_features.second_wind_used,
            action_surge_used=True,
            sneak_attack_available=actor.class_features.sneak_attack_available,
        )
        session.actor = actor.model_copy(
            update={"class_features": new_features}
        )
        _save_session(session)
        return {
            "success": True,
            "extra_action_available": True,
        }


def reset_class_features(session_id: str | None = None) -> None:
    """Reset all class feature uses (called on short/long rest)."""
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        actor = session.actor
        if actor is None:
            return
        
        new_features = ClassFeatures()
        if actor.character_class == CharacterClass.WARRIOR:
            new_features = ClassFeatures(second_wind_used=False, action_surge_used=False)
        elif actor.character_class == CharacterClass.ROGUE:
            new_features = ClassFeatures(sneak_attack_available=True)
        
        session.actor = actor.model_copy(update={"class_features": new_features})
        _save_session(session)


def _is_expired(session: SessionData) -> bool:
    return (time.time() - session.updated_at) > SESSION_TTL_SECONDS

# ---------------------------------------------------------------------------
# NPC Dialogue State Functions
# ---------------------------------------------------------------------------

def record_npc_dialogue(
    npc_id: str,
    npc_name: str,
    speaker: str,
    content: str,
    session_id: str | None = None,
) -> None:
    """Record a dialogue entry for an NPC.
    
    Args:
        npc_id: The NPC's unique ID
        npc_name: The NPC's display name
        speaker: Who spoke ('player' or NPC name)
        content: What was said
        session_id: The session ID (uses current session if None)
    """
    from .npc.dialogue_state import record_dialogue as _record_dialogue
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        dialogue_state = _record_dialogue(npc_id, npc_name, speaker, content, resolved_session_id)
        # Update session's npc_dialogue_states
        session.npc_dialogue_states[npc_id] = dialogue_state
        _save_session(session)


def get_npc_dialogue_count(
    npc_id: str,
    session_id: str | None = None,
) -> int:
    """Get the dialogue count for a specific NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID (uses current session if None)
        
    Returns:
        Number of dialogue interactions (0 if never spoken)
    """
    from .npc.dialogue_state import get_npc_dialogue_count as _get_count
    resolved_session_id = _resolve_session_id(session_id)
    return _get_count(npc_id, resolved_session_id)


def get_npc_dialogue_history(
    npc_id: str,
    session_id: str | None = None,
    max_entries: int = 5,
) -> list:
    """Get dialogue history for a specific NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID (uses current session if None)
        max_entries: Maximum number of entries to return
        
    Returns:
        List of dialogue entries
    """
    from .npc.dialogue_state import get_dialogue_history as _get_history
    resolved_session_id = _resolve_session_id(session_id)
    return _get_history(npc_id, resolved_session_id, max_entries)


def build_npc_dialogue_context_for_prompt(
    npc_id: str,
    npc_name: str,
    session_id: str | None = None,
) -> str:
    """Build dialogue context string for prompt injection.
    
    Args:
        npc_id: The NPC's unique ID
        npc_name: The NPC's display name
        session_id: The session ID (uses current session if None)
        
    Returns:
        Formatted dialogue context string for prompt injection
    """
    from .npc.dialogue_state import build_dialogue_context_for_prompt as _build_context
    resolved_session_id = _resolve_session_id(session_id)
    return _build_context(npc_id, npc_name, resolved_session_id)


def is_first_npc_contact(
    npc_id: str,
    session_id: str | None = None,
) -> bool:
    """Check if this is the first interaction with an NPC.
    
    Args:
        npc_id: The NPC's unique ID
        session_id: The session ID (uses current session if None)
        
    Returns:
        True if this is the first contact, False otherwise
    """
    return get_npc_dialogue_count(npc_id, session_id) == 0
    """
    return get_npc_dialogue_count(npc_id, session_id) == 0


# -----------------------------------------------------------------------------
# Map Exploration Functions
# -----------------------------------------------------------------------------

def get_explored_nodes(session_id: str | None = None) -> list[str]:
    """Get list of explored scene IDs for a session.
    
    Args:
        session_id: The session ID (uses current session if None)
        
    Returns:
        List of scene IDs that have been explored
    """
    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
    return list(session.explored_nodes)


def add_explored_node(scene_id: str, session_id: str | None = None) -> None:
    """Add a scene to the explored nodes list.
    
    Args:
        scene_id: The scene ID to add
        session_id: The session ID (uses current session if None)
    """
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        if scene_id not in session.explored_nodes:
            session.explored_nodes = [*session.explored_nodes, scene_id]
            _save_session(session)


def reset_explored_nodes(session_id: str | None = None) -> None:
    """Clear all explored nodes for a session.
    
    Args:
        session_id: The session ID (uses current session if None)
    """
    resolved_session_id = _resolve_session_id(session_id)
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        session.explored_nodes = []
        _save_session(session)
