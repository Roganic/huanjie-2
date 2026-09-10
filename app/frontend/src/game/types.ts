import type { Journey } from '../components/JourneySummary';
import type { ActiveModuleState } from '../types/module';

export interface Message {
  id: number;
  role: "gm" | "player" | "system";
  text: string;
  resolution?: ActionResponse;
  timestamp: number;
}

export type HealthStatus = "loading" | "ok" | "error";
export type GamePhase = "character_creation" | "adventure";
export type AdventurePhase = "exploration" | "combat" | "ended";
export type CharacterClass = "warrior" | "mage" | "rogue";

export interface CheckDetail {
  ability: string;
  modifier: number;
  proficiency_bonus: number;
  advantage: boolean | null;
  roll: number;
  total: number;
  dc: number;
  skill_name?: string | null;
}

export interface SkillCheckDetail {
  skill: string | null;
  ability?: string;
  roll: number;
  modifier: number;
  total: number;
  dc: number;
  success: boolean;
}

export interface Effect {
  target: string;
  field: string;
  delta: number | string;
  description: string;
}

export interface ItemUseDetail {
  item_name: string;
  effect_type: string;
  roll_result: number;
  hp_change: number;
}

export interface ActionResponse {
  feedback?: { summary: string; detail: string };
  action_status?: "executed" | "blocked" | "clarification" | "read_only";
  adjudication?: { name: string; kind: string; risk: string; stakes: string; time_cost: number };
  world_events?: { id: string; title: string; narration: string }[];
  gm_narration?: string;
  gm?: { mode: string; notice?: string };
  action_summary: string;
  resolution_type: "auto_success" | "check";
  check: CheckDetail | null;
  skill_check: SkillCheckDetail | null;
  item_use: ItemUseDetail | null;
  outcome: "success" | "failure";
  effects: Effect[];
  narration: string;
  scene_progression: string;
  gm_prompt: string;
}

export interface AbilityScores {
  str: number;
  dex: number;
  con: number;
  int: number;
  wis: number;
  cha: number;
}

export interface InventoryItem {
  id: string;
  name: string;
  type: "weapon" | "armor";
  description?: string;
  damage_dice?: string;
  attack_ability?: string;
  base_ac?: number;
}

export interface EquippedItems {
  weapon: InventoryItem | null;
  armor: InventoryItem | null;
}

export interface SpellSlot {
  level: number;
  max: number;
  current: number;
}

export interface Actor {
  id: string;
  name: string;
  character_class?: CharacterClass | null;
  abilities: AbilityScores;
  proficiency_bonus: number;
  level?: number;
  hp: number;
  hp_max: number;
  ac?: number;
  description: string;
  conditions?: string[];
  skills?: { name: string; ability: string; proficient: boolean; modifier: number }[];
  experience_points?: number;
  equipped?: EquippedItems;
  spell_slots?: SpellSlot[] | Record<string, number>;
  spell_slots_max?: Record<string, number>;
  class_features?: {
    second_wind_used?: boolean;
    action_surge_used?: boolean;
    sneak_attack_available?: boolean;
  };
}

export interface NPC {
  id: string;
  name: string;
  type: "friendly" | "neutral" | "hostile";
  description: string;
  race?: string;
  occupation?: string;
}

export interface SceneExit {
  direction: string;
  target_scene_id: string;
}

export interface Scene {
  id: string;
  name: string;
  description: string;
  actors: string[];
  npcs: NPC[];
  time?: number;
  exits?: SceneExit[];
}

export interface NarrativeHistoryEntry {
  gm_narration?: string;
  gm_notice?: string;
  action_summary: string;
  resolution_summary: {
    feedback?: ActionResponse["feedback"];
    command_kind?: string;
    player_input?: string;
    action_status?: ActionResponse["action_status"];
    adjudication?: ActionResponse["adjudication"];
    world_events?: ActionResponse["world_events"];
    result?: "success" | "failure";
    resolution_type?: "auto_success" | "check";
    outcome?: "success" | "failure";
    check?: CheckDetail | null;
  };
  narration_summary: string;
  narration: string;
  scene_progression: string;
  gm_prompt: string;
  created_at: number;
}

export interface BootstrapState {
  journey?: Journey | null;
  play_status?: { mode: string; label: string; reason: string; can_explore: boolean; can_rest: boolean; rest_reason: string; can_restart: boolean };
  session_id: string;
  phase: GamePhase;
  game_phase: AdventurePhase;
  actor: Actor | null;
  scene: Scene;
  narrative_history: NarrativeHistoryEntry[];
  action_history: { action: string; result: string; narrative_summary: string }[];
  active_module?: ActiveModuleState | null;
}

// ---------------------------------------------------------------------------
// Combat Types
// ---------------------------------------------------------------------------

export type CombatStatus = "active" | "victory" | "defeat" | "escaped";
export type CombatActionType = string;
export interface AvailableCombatAction {
  id: string; name: string; target: "self" | "enemy" | "none"; cost: string;
  available: boolean; disabled_reason?: string; description: string;
}

export interface CombatParticipant {
  id: string;
  name: string;
  hp: number;
  hp_max: number;
  ac: number;
  initiative: number;
  initiative_roll?: number;
  speed?: number;
  is_player: boolean;
  conditions: string[];
}

export interface CombatLogEntry {
  actor_id: string;
  action_type: string;
  target_id?: string;
  hit?: boolean;
  damage?: number;
  narrative: string;
  timestamp: number;
}

export interface CombatState {
  combat_id: string;
  round_number: number;
  turn_index: number;
  participants: CombatParticipant[];
  initiative_order: string[];
  current_actor_id: string;
  scene: Scene;
  status: CombatStatus;
  log: CombatLogEntry[];
  available_actions?: AvailableCombatAction[];
  actions_remaining?: number;
  bonus_action_available?: boolean;
}

export interface LevelUpInfo {
  old_level: number;
  new_level: number;
  hp_increase: number;
  new_proficiency_bonus: number;
}

export interface CombatActionResult {
  gm_narration?: string;
  gm?: { mode: string; notice?: string };
  action_type: CombatActionType;
  actor_id: string;
  target_id?: string;
  hit?: boolean;
  damage?: number;
  effects: Effect[];
  narrative: string;
  outcome?: string;
  available_actions?: AvailableCombatAction[];
  combat_state: CombatState;
  xp_gained?: number;
  level_up?: LevelUpInfo;
}



export interface TimelineEntry {
  id: number;
  type: "action" | "check" | "system" | "scene";
  title: string;
  outcome?: "success" | "failure";
  details?: string;
  timestamp: number;
  expanded?: boolean;
}

export interface CharacterDraft {
  name: string;
  characterClass: CharacterClass;
  abilities: AbilityScores;
  abilityGeneration: "standard_array" | "random_4d6" | "manual";
}

export interface SaveFile {
  save_id: string;
  save_name: string;
  character_name: string | null;
  class: string | null;
  character_level: number | null;
  hp: number | null;
  hp_max: number | null;
  scene_name: string | null;
  saved_at: string;
}

export interface QuestView { id: string; name: string; status_label: string; objective: string; reward: string }
export interface ChallengeChoice { approach_id?: string; consequence_id?: string }
export interface Challenge {
  id: string; name: string; description: string; stakes: string; check_kind: string; dc: number; blocked_reason: string;
  approaches?: { id: string; name: string; description: string; dc: number }[];
  consequences?: { id: string; name: string; stakes: string }[];
}

export interface Guidance {
  challenges: Challenge[];
  relationships: { name: string; value: number }[];
  location: string;
  objective: string;
  npcs: { id: string; name: string; intent: string }[];
  interactions: { id: string; name: string; intent: string }[];
  objects: { id: string; name: string; intent: string; status: string; reason: string; skill: string | null; dc: number | null; time_cost: number; rule_hint: string }[];
  moves: { target_scene_id: string; label: string }[];
  clues: string[];
  danger: string;
  enemy_count: number;
  targets: { id: string; name: string; hostile: boolean; attackable: boolean }[];
  quest: QuestView | null;
  quests: QuestView[];
}


export interface EventState { pending: { id: string; title: string; remaining: number; clock: string; waiting_for_scene: boolean; waiting_for_conditions: boolean; has_consequences?: boolean; priority?: string }[]; resolved: { id: string; title: string; status: string; reason: string }[] }
