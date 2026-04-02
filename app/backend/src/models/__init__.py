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
from .module import (
    ActiveModuleState,
    ModuleDefinition,
    Quest,
    StoryNode,
    StoryTrigger,
)
from .state import (
    Actor,
    BootstrapState,
    CharacterCard,
    CharacterCreateRequest,
    CharacterSkill,
    ClassFeatures,
    GamePhase,
    HP,
    NarrativeHistoryEntry,
    Scene,
)

__all__ = [
    # Module models
    "ActiveModuleState",
    "ModuleDefinition",
    "Quest",
    "StoryNode",
    "StoryTrigger",
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
    "ClassFeatures",
    "GamePhase",
    "HP",
    "NarrativeHistoryEntry",
    "Scene",
]
