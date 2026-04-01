"""Data models for the backend."""

from .action import (
    ActionRequest,
    ActionResponse,
    ActionType,
    AttackDetail,
    CheckDetail,
    DamageDetail,
    Effect,
    Outcome,
    ResolutionType,
    SavingThrowDetail,
)
from .character import (
    AbilityScores,
    Character,
    CharacterClass,
    Equipment,
    Skill,
    SkillDefinition,
)
from .state import (
    Actor,
    BootstrapState,
    CharacterCard,
    CharacterCreateRequest,
    CharacterSkill,
    GamePhase,
    HP,
    NarrativeHistoryEntry,
    Scene,
)

__all__ = [
    # Action models
    "ActionRequest",
    "ActionResponse",
    "ActionType",
    "AttackDetail",
    "CheckDetail",
    "DamageDetail",
    "Effect",
    "Outcome",
    "ResolutionType",
    "SavingThrowDetail",
    # Character models
    "AbilityScores",
    "Character",
    "CharacterClass",
    "Equipment",
    "Skill",
    "SkillDefinition",
    # State models
    "Actor",
    "BootstrapState",
    "CharacterCard",
    "CharacterCreateRequest",
    "CharacterSkill",
    "GamePhase",
    "HP",
    "NarrativeHistoryEntry",
    "Scene",
]
