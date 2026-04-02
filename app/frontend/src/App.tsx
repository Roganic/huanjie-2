import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import MapPanel from "./components/MapPanel";

interface Message {
  id: number;
  role: "gm" | "player" | "system";
  text: string;
  resolution?: ActionResponse;
  streamingPreview?: StreamingPreview;
  timestamp: number;
}

type HealthStatus = "loading" | "ok" | "error";
type GamePhase = "character_creation" | "adventure";
type AdventurePhase = "exploration" | "combat" | "ended";
type CharacterClass = "warrior" | "mage" | "rogue";

interface CheckDetail {
  ability: string;
  modifier: number;
  proficiency_bonus: number;
  advantage: boolean | null;
  roll: number;
  total: number;
  dc: number;
  skill_name?: string | null;
}

interface SkillCheckDetail {
  skill: string | null;
  ability?: string;
  roll: number;
  modifier: number;
  total: number;
  dc: number;
  success: boolean;
}

interface Effect {
  target: string;
  field: string;
  delta: number | string;
  description: string;
}

interface ItemUseDetail {
  item_name: string;
  effect_type: string;
  roll_result: number;
  hp_change: number;
}

interface ActionResponse {
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

interface StreamingPreview {
  narration: string;
  scene_progression: string;
  gm_prompt: string;
  interrupted?: boolean;
}

interface AbilityScores {
  str: number;
  dex: number;
  con: number;
  int: number;
  wis: number;
  cha: number;
}

interface InventoryItem {
  id: string;
  name: string;
  type: "weapon" | "armor";
  description?: string;
  damage_dice?: string;
  attack_ability?: string;
  base_ac?: number;
}

interface EquippedItems {
  weapon: InventoryItem | null;
  armor: InventoryItem | null;
}

interface SpellSlot {
  level: number;
  max: number;
  current: number;
}

interface Actor {
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
  spell_slots?: SpellSlot[];
  class_features?: {
    second_wind_used?: boolean;
    action_surge_used?: boolean;
    sneak_attack_available?: boolean;
  };
}

interface NPC {
  id: string;
  name: string;
  type: "friendly" | "neutral" | "hostile";
  description: string;
  race?: string;
  occupation?: string;
}

interface SceneExit {
  direction: string;
  target_scene_id: string;
}

interface Scene {
  id: string;
  name: string;
  description: string;
  actors: string[];
  npcs: NPC[];
  time?: number;
  exits?: SceneExit[];
}

interface NarrativeHistoryEntry {
  action_summary: string;
  resolution_summary: {
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

interface BootstrapState {
  session_id: string;
  phase: GamePhase;
  game_phase: AdventurePhase;
  actor: Actor | null;
  scene: Scene;
  narrative_history: NarrativeHistoryEntry[];
  action_history: { action: string; result: string; narrative_summary: string }[];
}

// ---------------------------------------------------------------------------
// Combat Types
// ---------------------------------------------------------------------------

type CombatStatus = "active" | "victory" | "defeat" | "escaped";
type CombatActionType = "attack" | "defend" | "skill" | "flee";

interface CombatParticipant {
  id: string;
  name: string;
  hp: number;
  hp_max: number;
  ac: number;
  initiative: number;
  is_player: boolean;
  conditions: string[];
}

interface CombatLogEntry {
  actor_id: string;
  action_type: string;
  target_id?: string;
  hit?: boolean;
  damage?: number;
  narrative: string;
  timestamp: number;
}

interface CombatState {
  combat_id: string;
  round_number: number;
  turn_index: number;
  participants: CombatParticipant[];
  initiative_order: string[];
  current_actor_id: string;
  scene: Scene;
  status: CombatStatus;
  log: CombatLogEntry[];
}

interface LevelUpInfo {
  old_level: number;
  new_level: number;
  hp_increase: number;
  new_proficiency_bonus: number;
}

interface CombatActionResult {
  action_type: CombatActionType;
  actor_id: string;
  target_id?: string;
  hit?: boolean;
  damage?: number;
  effects: Effect[];
  narrative: string;
  combat_state: CombatState;
  xp_gained?: number;
  level_up?: LevelUpInfo;
}

interface ProviderOption {
  id: string;
  label: string;
}

interface TimelineEntry {
  id: number;
  type: "action" | "check" | "system" | "scene";
  title: string;
  outcome?: "success" | "failure";
  details?: string;
  timestamp: number;
  expanded?: boolean;
}

interface CharacterDraft {
  name: string;
  characterClass: CharacterClass;
  abilities: AbilityScores;
  abilityGeneration: "standard_array" | "random_4d6" | "manual";
}

interface SaveFile {
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

type Skill = {
  name: string;
  ability: keyof AbilityScores;
  proficient: boolean;
};

const SKILL_LABELS: Record<string, string> = {
  athletics: "运动",
  acrobatics: "杂技",
  sleight_of_hand: "巧手",
  stealth: "隐匿",
  arcana: "奥秘",
  history: "历史",
  investigation: "调查",
  nature: "自然",
  religion: "宗教",
  animal_handling: "驯兽",
  insight: "洞察",
  medicine: "医药",
  perception: "察觉",
  survival: "生存",
  deception: "欺骗",
  intimidation: "威吓",
  performance: "表演",
  persuasion: "说服",
};

const SKILLS: Skill[] = [
  { name: "acrobatics", ability: "dex", proficient: false },
  { name: "animal_handling", ability: "wis", proficient: false },
  { name: "athletics", ability: "str", proficient: false },
  { name: "deception", ability: "cha", proficient: false },
  { name: "history", ability: "int", proficient: false },
  { name: "insight", ability: "wis", proficient: false },
  { name: "intimidation", ability: "cha", proficient: false },
  { name: "investigation", ability: "int", proficient: false },
  { name: "medicine", ability: "wis", proficient: false },
  { name: "nature", ability: "int", proficient: false },
  { name: "perception", ability: "wis", proficient: false },
  { name: "performance", ability: "cha", proficient: false },
  { name: "persuasion", ability: "cha", proficient: false },
  { name: "religion", ability: "int", proficient: false },
  { name: "sleight_of_hand", ability: "dex", proficient: false },
  { name: "stealth", ability: "dex", proficient: false },
  { name: "survival", ability: "wis", proficient: false },
];

const CLASS_SKILLS: Record<CharacterClass, string[]> = {
  warrior: ["athletics", "intimidation", "perception", "survival"],
  mage: ["arcana", "history", "investigation", "insight"],
  rogue: ["acrobatics", "sleight_of_hand", "stealth", "deception", "persuasion"],
};

const EXTRA_SKILLS: Skill[] = [
  { name: "arcana", ability: "int", proficient: false },
];

const ABILITY_LABELS: Record<string, string> = {
  str: "力量",
  dex: "敏捷",
  con: "体质",
  int: "智力",
  wis: "感知",
  cha: "魅力",
};

const ABILITY_KEYS: (keyof AbilityScores)[] = ["str", "dex", "con", "int", "wis", "cha"];

const STANDARD_ARRAY = [15, 14, 13, 12, 10, 8];

const ABILITY_ICONS: Record<string, string> = {
  str: "💪",
  dex: "🏃",
  con: "❤️",
  int: "🧠",
  wis: "👁️",
  cha: "🎭",
};

const STATUS_ICONS: Record<string, string> = {
  健康: "✅",
  受伤: "⚠️",
  中毒: "☠️",
  眩晕: "😵",
  恐惧: "😨",
  激励: "⭐",
  掩护: "🛡️",
};

const PROVIDERS: ProviderOption[] = [
  { id: "", label: "自动" },
  { id: "kimi", label: "Kimi" },
  { id: "openai", label: "OpenAI" },
];

const CLASS_LABELS: Record<CharacterClass, string> = {
  warrior: "战士",
  mage: "法师",
  rogue: "盗贼",
};

const CLASS_SUMMARIES: Record<CharacterClass, string> = {
  warrior: "高 HP、高 AC，适合正面承伤与近战。",
  mage: "高智力，HP 较低，依赖知识与法术叙事。",
  rogue: "高敏捷，中等防护，擅长机动与潜入。",
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const SESSION_STORAGE_KEY = "huanjie.session_id";
const MAX_RESTORED_HISTORY = 10;

function apiUrl(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error(`API path must start with "/": ${path}`);
  }

  return API_BASE_URL ? `${API_BASE_URL}${path}` : `/api${path}`;
}

function getModifier(score: number): number {
  return Math.floor((score - 10) / 2);
}

function roll4d6DropLowest(): number {
  const rolls = Array.from({ length: 4 }, () => Math.floor(Math.random() * 6) + 1);
  rolls.sort((a, b) => a - b);
  return rolls[1] + rolls[2] + rolls[3]; // Sum top 3 (drop lowest)
}

function rollRandomAbilities(): AbilityScores {
  return {
    str: roll4d6DropLowest(),
    dex: roll4d6DropLowest(),
    con: roll4d6DropLowest(),
    int: roll4d6DropLowest(),
    wis: roll4d6DropLowest(),
    cha: roll4d6DropLowest(),
  };
}

function getClassAbilities(characterClass: CharacterClass): AbilityScores {
  const templates: Record<CharacterClass, AbilityScores> = {
    warrior: { str: 15, dex: 13, con: 14, int: 8, wis: 12, cha: 10 },
    mage: { str: 8, dex: 13, con: 12, int: 15, wis: 14, cha: 10 },
    rogue: { str: 10, dex: 15, con: 13, int: 12, wis: 14, cha: 8 },
  };
  return templates[characterClass];
}

// Alias for compatibility with existing code
const getDefaultAbilities = getClassAbilities;

function formatModifier(mod: number): string {
  return mod >= 0 ? `+${mod}` : `${mod}`;
}

function getHpStatus(hp: number, max: number): "high" | "medium" | "low" {
  const ratio = hp / max;
  if (ratio > 0.6) return "high";
  if (ratio > 0.3) return "medium";
  return "low";
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function HealthDot({ status }: { status: HealthStatus }) {
  const label =
    status === "loading" ? "连接中…" : status === "ok" ? "后端已连接" : "后端离线";
  return (
    <span className={`health-dot ${status}`} title={label}>
      <span className="dot" />
      {label}
    </span>
  );
}

function HpBar({ hp, max, previousHp }: { hp: number; max: number; previousHp?: number }) {
  const percentage = Math.max(0, Math.min(100, (hp / max) * 100));
  const status = getHpStatus(hp, max);
  const changed = previousHp !== undefined && previousHp !== hp;
  const isDamaged = changed && hp < (previousHp ?? hp);

  return (
    <div className="hp-section">
      <div className="hp-header">
        <span className="hp-label">生命值</span>
        <span className="hp-values">
          <span
            className={`hp-current ${changed ? "changed" : ""} ${
              hp > (previousHp ?? hp) ? "flash-positive" : isDamaged ? "flash-negative" : ""
            }`}
          >
            {hp}
          </span>
          <span className="hp-separator">/</span>
          <span className="hp-max">{max}</span>
        </span>
      </div>
      <div className="hp-bar-container">
        <div className={`hp-bar ${status} ${isDamaged ? "damaged" : ""}`} style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function AbilityScore({
  ability,
  score,
  changed,
}: {
  ability: string;
  score: number;
  changed?: boolean;
}) {
  const modifier = getModifier(score);
  return (
    <div className={`stat-box ${changed ? "changed" : ""}`}>
      <div className="stat-name">
        {ABILITY_LABELS[ability]} {ABILITY_ICONS[ability]}
      </div>
      <div className="stat-value">{score}</div>
      <div className="stat-modifier">{formatModifier(modifier)}</div>
    </div>
  );
}

function StatusEffect({ name, isNew }: { name: string; isNew?: boolean }) {
  const icon = STATUS_ICONS[name] || "🔹";
  let type = "neutral";
  if (["受伤", "中毒", "眩晕", "恐惧"].includes(name)) type = "debuff";
  if (["健康", "激励", "掩护"].includes(name)) type = "buff";

  return (
    <span className={`status-effect ${type} ${isNew ? "new" : ""}`}>
      {icon} {name}
    </span>
  );
}

function SkillsList({ actor, compact = false }: { actor: Actor; compact?: boolean }) {
  // Prefer backend-provided skills when available; fallback to frontend computation
  const skills = actor.skills && actor.skills.length > 0
    ? actor.skills
    : (() => {
        const profBonus = actor.proficiency_bonus;
        const classProfSkills = CLASS_SKILLS[actor.character_class ?? "warrior"] ?? [];
        const allSkills = [...SKILLS, ...EXTRA_SKILLS];
        return allSkills.map((skill) => {
          const abilityMod = getModifier(actor.abilities[skill.ability]);
          const isProficient = classProfSkills.includes(skill.name);
          return {
            name: skill.name,
            ability: skill.ability,
            proficient: isProficient,
            modifier: abilityMod + (isProficient ? profBonus : 0),
          };
        });
      })();

  if (compact) {
    const proficientSkills = skills.filter((s) => s.proficient);
    return (
      <div className="skills-list-compact">
        {proficientSkills.map((skill) => (
          <div key={skill.name} className="skill-item-compact proficient">
            <span className="skill-name">{SKILL_LABELS[skill.name] ?? skill.name}</span>
            <span className="skill-bonus">{formatModifier(skill.modifier)}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="skills-list">
      {skills.map((skill) => (
        <div key={skill.name} className={`skill-item ${skill.proficient ? "proficient" : ""}`}>
          <span className="skill-dot">{skill.proficient ? "●" : "○"}</span>
          <span className="skill-name">{SKILL_LABELS[skill.name] ?? skill.name}</span>
          <span className="skill-ability">({ABILITY_LABELS[skill.ability]})</span>
          <span className="skill-bonus">{formatModifier(skill.modifier)}</span>
        </div>
      ))}
    </div>
  );
}

// XP thresholds matching the backend
const XP_THRESHOLDS: Record<number, number> = {
  1: 0,
  2: 300,
  3: 900,
  4: 2700,
  5: 6500,
};

function getXpProgress(currentXp: number, level: number): { current: number; needed: number } {
  const currentThreshold = XP_THRESHOLDS[level] ?? 0;
  const nextThreshold = XP_THRESHOLDS[level + 1];
  
  if (nextThreshold === undefined) {
    return { current: currentXp - currentThreshold, needed: 0 };
  }
  
  return {
    current: currentXp - currentThreshold,
    needed: nextThreshold - currentThreshold,
  };
}

function MiniCharacterCard({ actor }: { actor: Actor }) {
  const hpPercent = Math.round((actor.hp / actor.hp_max) * 100);
  let hpStatus: "high" | "medium" | "low" = "high";
  if (hpPercent <= 30) hpStatus = "low";
  else if (hpPercent <= 60) hpStatus = "medium";

  const xp = actor.experience_points ?? 0;
  const level = actor.level ?? 1;

  return (
    <div className="mini-character-card">
      <div className="mini-char-main">
        <div className="mini-char-avatar">{actor.character_class === "warrior" ? "⚔️" : actor.character_class === "mage" ? "🔮" : "🗡️"}</div>
        <div className="mini-char-info">
          <div className="mini-char-name">{actor.name}</div>
          <div className="mini-char-class">{actor.character_class ? CLASS_LABELS[actor.character_class] : "冒险者"} · Lv.{level}</div>
        </div>
      </div>
      <div className="mini-char-stats">
        <div className="mini-stat" title="生命值">
          <span className="mini-stat-icon">❤️</span>
          <span className={`mini-stat-value hp-${hpStatus}`}>{actor.hp}/{actor.hp_max}</span>
        </div>
        <div className="mini-stat" title="护甲等级">
          <span className="mini-stat-icon">🛡️</span>
          <span className="mini-stat-value">{actor.ac}</span>
        </div>
        <div className="mini-stat" title="熟练加值">
          <span className="mini-stat-icon">⭐</span>
          <span className="mini-stat-value">+{actor.proficiency_bonus}</span>
        </div>
        <div className="mini-stat" title="经验值">
          <span className="mini-xp-icon">✨</span>
          <span className="mini-xp-stat">{xp}</span>
        </div>
      </div>
    </div>
  );
}

function XpBar({ current, needed }: { current: number; needed: number }) {
  if (needed === 0) {
    return (
      <div className="xp-section">
        <div className="xp-header">
          <span className="xp-label">经验值 (Max Level)</span>
          <span className="xp-values">
            <span className="xp-current">{current}</span>
          </span>
        </div>
        <div className="xp-bar-container">
          <div className="xp-bar" style={{ width: "100%" }} />
        </div>
      </div>
    );
  }

  const percentage = Math.min(100, Math.max(0, (current / needed) * 100));

  return (
    <div className="xp-section">
      <div className="xp-header">
        <span className="xp-label">经验值</span>
        <span className="xp-values">
          <span className="xp-current">{current}</span>
          <span className="xp-separator">/</span>
          <span className="xp-needed">{needed}</span>
          <span style={{ color: "var(--text-muted)", marginLeft: 4 }}>XP</span>
        </span>
      </div>
      <div className="xp-bar-container">
        <div className="xp-bar" style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function SpellSlotsPanel({ slots, previousSlots }: { slots: SpellSlot[]; previousSlots?: SpellSlot[] }) {
  if (!slots || slots.length === 0) return null;
  
  return (
    <div className="spell-slots-section">
      <div className="spell-slots-header">
        <span className="spell-slots-label">法术槽位</span>
      </div>
      <div className="spell-slots-list">
        {slots.map((slot) => {
          const previousSlot = previousSlots?.find((s) => s.level === slot.level);
          const hasChanged = previousSlot && previousSlot.current !== slot.current;
          const isDepleted = slot.current === 0;
          
          return (
            <div 
              key={slot.level} 
              className={`spell-slot-item ${isDepleted ? 'depleted' : ''} ${hasChanged ? 'changed' : ''}`}
            >
              <span className="spell-slot-level">{slot.level}环</span>
              <span className="spell-slot-values">
                <span className={`spell-slot-current ${hasChanged ? 'changed' : ''}`}>
                  {slot.current}
                </span>
                <span className="spell-slot-separator">/</span>
                <span className="spell-slot-max">{slot.max}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CharacterCard({
  actor,
  previousActor,
  newConditions,
}: {
  actor: Actor;
  previousActor?: Actor | null;
  newConditions?: string[];
}) {
  const xp = actor.experience_points ?? 0;
  const level = actor.level ?? 1;
  const xpProgress = getXpProgress(xp, level);
  const isMage = actor.character_class === "mage";

  return (
    <div className="character-card">
      <div className="character-header">
        <div className="character-avatar">
          {actor.character_class === "warrior" ? "⚔️" : actor.character_class === "mage" ? "🔮" : "🗡️"}
        </div>
        <div className="character-info">
          <div className="character-name">{actor.name}</div>
          <div className="character-level">
            {actor.character_class ? CLASS_LABELS[actor.character_class] : "冒险者"} Lv.{level} · 熟练加值 +{actor.proficiency_bonus}
          </div>
        </div>
        {actor.ac !== undefined && (
          <div className="ac-display" title="护甲等级">
            <span className="ac-label">AC</span>
            <span className="ac-value">{actor.ac}</span>
          </div>
        )}
      </div>

      <HpBar hp={actor.hp} max={actor.hp_max} previousHp={previousActor?.hp} />
      
      <XpBar current={xpProgress.current} needed={xpProgress.needed} />

      {/* Spell Slots - Only for mages */}
      {isMage && actor.spell_slots && actor.spell_slots.length > 0 && (
        <SpellSlotsPanel 
          slots={actor.spell_slots} 
          previousSlots={previousActor?.spell_slots} 
        />
      )}

      {actor.conditions && actor.conditions.length > 0 && (
        <div className="status-effects">
          {actor.conditions.map((condition, index) => (
            <StatusEffect key={index} name={condition} isNew={newConditions?.includes(condition)} />
          ))}
        </div>
      )}
      
      {/* Equipped Items */}
      {(actor.equipped?.weapon || actor.equipped?.armor) && (
        <div className="equipped-items">
          <div className="equipped-label">已装备</div>
          <div className="equipped-list">
            {actor.equipped.weapon && (
              <div className="equipped-item" title={`武器: ${actor.equipped.weapon.name}`}>
                <span className="equipped-icon">⚔️</span>
                <span className="equipped-name">{actor.equipped.weapon.name}</span>
              </div>
            )}
            {actor.equipped.armor && (
              <div className="equipped-item" title={`护甲: ${actor.equipped.armor.name}`}>
                <span className="equipped-icon">🛡️</span>
                <span className="equipped-name">{actor.equipped.armor.name}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SceneCard({ scene, playerName, previousScene, onExitClick }: { scene: Scene; playerName?: string; previousScene?: Scene | null; onExitClick?: (direction: string) => void }) {
  const timeChanged = previousScene !== undefined && previousScene !== null && previousScene.time !== scene.time;

  const npcTypeClass = (type: string) => {
    if (type === "friendly") return "npc-friendly";
    if (type === "hostile") return "npc-hostile";
    return "npc-neutral";
  };

  const npcTypeLabel = (type: string) => {
    if (type === "friendly") return "友好";
    if (type === "hostile") return "敌对";
    return "中立";
  };

  return (
    <div className="scene-card">
      <div className="scene-name">{scene.name}</div>
      <p className="scene-desc">{scene.description}</p>

      {scene.time !== undefined && (
        <div className={`scene-time ${timeChanged ? "changed" : ""}`}>
          <span className="scene-time-label">⏱️ 场景时间</span>
          <span className="scene-time-value">{scene.time}</span>
        </div>
      )}

      {scene.exits && scene.exits.length > 0 && (
        <div className="scene-exits">
          <div className="scene-exits-label">可用出口</div>
          <div className="exit-buttons">
            {scene.exits.map((exit, index) => (
              <button
                key={index}
                className="exit-button"
                onClick={() => onExitClick?.(exit.direction)}
                title={`前往 ${exit.direction}`}
              >
                → {exit.direction}
              </button>
            ))}
          </div>
        </div>
      )}

      {scene.actors.length > 0 && (
        <div className="scene-actors">
          <div className="scene-actors-label">在场角色</div>
          <div className="actor-tags">
            {scene.actors.map((actor, index) => (
              <span key={index} className={`actor-tag ${playerName && actor === playerName ? "player" : ""}`}>
                {actor}
              </span>
            ))}
          </div>
        </div>
      )}

      {scene.npcs && scene.npcs.length > 0 && (
        <div className="scene-npcs">
          <div className="scene-npcs-label">场景 NPC</div>
          <div className="npc-list">
            {scene.npcs.map((npc) => (
              <div key={npc.id} className={`npc-item ${npcTypeClass(npc.type)}`}>
                <span className="npc-name">{npc.name}</span>
                <span className="npc-type">{npcTypeLabel(npc.type)}</span>
                <p className="npc-desc">{npc.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface StateDiff {
  hpDelta?: number;
  newConditions: string[];
  removedConditions: string[];
  timeDelta?: number;
  hasChanges: boolean;
}

function computeStateDiff(current: BootstrapState | null, previous: BootstrapState | null): StateDiff {
  if (!current?.actor || !previous?.actor) {
    return { newConditions: [], removedConditions: [], hasChanges: false };
  }

  const currConditions = current.actor.conditions ?? [];
  const prevConditions = previous.actor.conditions ?? [];
  const newConditions = currConditions.filter((condition) => !prevConditions.includes(condition));
  const removedConditions = prevConditions.filter((condition) => !currConditions.includes(condition));
  const hpDelta = current.actor.hp - previous.actor.hp;
  const timeDelta = (current.scene.time ?? 0) - (previous.scene.time ?? 0);
  const hasChanges = hpDelta !== 0 || newConditions.length > 0 || removedConditions.length > 0 || timeDelta !== 0;

  return {
    hpDelta: hpDelta !== 0 ? hpDelta : undefined,
    newConditions,
    removedConditions,
    timeDelta: timeDelta !== 0 ? timeDelta : undefined,
    hasChanges,
  };
}

function RecentChanges({ diff }: { diff: StateDiff }) {
  if (!diff.hasChanges) return null;

  return (
    <div className="recent-changes">
      <div className="recent-changes-title">最新变化</div>
      <div className="recent-changes-list">
        {diff.hpDelta !== undefined && (
          <span className={`change-item ${diff.hpDelta > 0 ? "positive" : "negative"}`}>
            {diff.hpDelta > 0 ? "+" : ""}
            {diff.hpDelta} HP
          </span>
        )}
        {diff.timeDelta !== undefined && (
          <span className="change-item time">
            {diff.timeDelta > 0 ? "+" : ""}
            {diff.timeDelta} 时间
          </span>
        )}
        {diff.newConditions.map((condition, index) => (
          <span key={`+${condition}-${index}`} className="change-item positive">
            + {condition}
          </span>
        ))}
        {diff.removedConditions.map((condition, index) => (
          <span key={`-${condition}-${index}`} className="change-item removed">
            - {condition}
          </span>
        ))}
      </div>
    </div>
  );
}

function TimelineItem({
  entry,
  onToggle,
}: {
  entry: TimelineEntry;
  onToggle: (id: number) => void;
}) {
  const outcomeClass = entry.outcome === "success" ? "success" : entry.outcome === "failure" ? "failure" : "info";
  const typeClass = `type-${entry.type}`;

  return (
    <div className={`timeline-item ${outcomeClass} ${typeClass} ${entry.expanded ? "expanded" : ""}`}>
      <div className="timeline-dot" />
      <div className="timeline-content">
        <div className="timeline-header" onClick={() => onToggle(entry.id)}>
          <span className="timeline-title">
            {entry.outcome === "success" && "✓ "}
            {entry.outcome === "failure" && "✗ "}
            {entry.title}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span className="timeline-time">{formatTime(entry.timestamp)}</span>
            {entry.details && <span className="timeline-expand">▼</span>}
          </div>
        </div>
        {entry.expanded && entry.details && <div className="timeline-details">{entry.details}</div>}
      </div>
    </div>
  );
}

function Timeline({
  entries,
  onToggle,
}: {
  entries: TimelineEntry[];
  onToggle: (id: number) => void;
}) {
  if (entries.length === 0) {
    return <div className="timeline-empty">暂无行动记录</div>;
  }

  return (
    <div className="timeline">
      {entries.map((entry) => (
        <TimelineItem key={entry.id} entry={entry} onToggle={onToggle} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scrollable Narrative History (shows all records, auto-scrolls)
// ---------------------------------------------------------------------------

interface ScrollableNarrativeHistoryProps {
  messages: Message[];
  streamingPreview: StreamingPreview | null;
  sending: boolean;
  gamePhase?: "exploration" | "combat" | "ended";
  xpGained?: number;
  levelUp?: LevelUpInfo | null;
}

function ScrollableNarrativeHistory({
  messages,
  streamingPreview,
  sending,
  gamePhase,
  xpGained,
  levelUp,
}: ScrollableNarrativeHistoryProps) {
  const gmMessages = messages.filter((m) => m.role === "gm");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, streamingPreview, xpGained, levelUp]);

  const isCombat = gamePhase === "combat";

  return (
    <div className={`narrative-history ${isCombat ? "narrative-combat" : "narrative-exploration"}`}>
      <div className="narrative-history-header">
        <span className="narrative-history-icon">{isCombat ? "⚔️" : "📜"}</span>
        <span className="narrative-history-title">{isCombat ? "战斗叙事" : "探索叙事"}</span>
        {gmMessages.length > 0 && (
          <span className="narrative-history-count">共 {gmMessages.length} 条记录</span>
        )}
      </div>
      <div className="narrative-list">
        {gmMessages.length === 0 && !sending && (
          <div className="narrative-empty">{isCombat ? "战斗进行中…" : "输入一个行动开始冒险…"}</div>
        )}
        {gmMessages.map((message) => (
          <div key={message.id} className={`narrative-item ${isCombat ? "narrative-combat-item" : ""}`}>
            <div className="narrative-text">
              {(message.resolution?.narration || message.text)
                .split("\n")
                .map((line, i) =>
                  line.trim() ? <p key={i}>{line}</p> : null
                )}
            </div>
            {message.resolution && (
              <div className="compact-resolution">
                <div className="compact-resolution-header">
                  <span className={`outcome-badge-sm ${message.resolution.outcome === "success" ? "outcome-success" : "outcome-failure"}`}>
                    {message.resolution.resolution_type === "check" ? "检定" : "自动"} · {message.resolution.outcome === "success" ? "成功" : "失败"}
                  </span>
                  {message.resolution.resolution_type === "check" && message.resolution.check && (
                    <span className="check-summary-sm">
                      {ABILITY_LABELS[message.resolution.check.ability] ?? message.resolution.check.ability} d20={message.resolution.check.roll}
                      {message.resolution.check.modifier >= 0 ? "+" : ""}
                      {message.resolution.check.modifier}
                      {message.resolution.check.proficiency_bonus > 0 ? `+${message.resolution.check.proficiency_bonus}` : ""}
                      {" = "}
                      {message.resolution.check.total} / DC{message.resolution.check.dc}
                    </span>
                  )}
                </div>
                {message.resolution.item_use && (
                  <div className="item-use-sm">
                    <span className="item-use-icon">🧪</span>
                    <span className="item-use-name">{message.resolution.item_use.item_name}</span>
                    <span className={`item-use-effect ${message.resolution.item_use.hp_change > 0 ? "positive" : message.resolution.item_use.hp_change < 0 ? "negative" : ""}`}>
                      {message.resolution.item_use.effect_type === "heal" ? "恢复" : ""} {message.resolution.item_use.hp_change} HP
                    </span>
                    <span className="item-use-roll">(roll: {message.resolution.item_use.roll_result})</span>
                  </div>
                )}
                {message.resolution.effects.length > 0 && (
                  <div className="effects-sm">
                    {message.resolution.effects.map((eff, index) => (
                      <span
                        key={index}
                        className={`effect-tag-sm ${
                          typeof eff.delta === "number" && eff.delta > 0
                            ? "positive"
                            : typeof eff.delta === "number" && eff.delta < 0
                              ? "negative"
                              : ""
                        }`}
                      >
                        {eff.description}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        
        {/* XP Gained Notification */}
        {!sending && xpGained !== undefined && xpGained > 0 && (
          <div className="narrative-item xp-gained-item">
            <div className="xp-gained-notification">
              <span className="xp-gained-icon">✨</span>
              <span className="xp-gained-text">+{xpGained} XP</span>
            </div>
          </div>
        )}
        
        {/* Level Up Notification */}
        {!sending && levelUp && (
          <div className="narrative-item level-up-item">
            <div className="level-up-notification-narrative">
              <span className="level-up-narrative-icon">🎊</span>
              <div className="level-up-narrative-content">
                <div className="level-up-narrative-title">升至 {levelUp.new_level} 级！</div>
                <div className="level-up-narrative-details">
                  HP +{levelUp.hp_increase} · 熟练加值 +{levelUp.new_proficiency_bonus}
                </div>
              </div>
            </div>
          </div>
        )}
        
        {sending && streamingPreview && (
          <div className={`narrative-item streaming ${isCombat ? "narrative-combat-item" : ""}`}>
            <div className="narrative-text">
              {streamingPreview.narration
                .split("\n")
                .map((line, i) =>
                  line.trim() ? <p key={i}>{line}</p> : null
                )}
            </div>
            <div className="streaming-indicator">
              <span className={`streaming-dot ${isCombat ? "combat-dot" : ""}`} />
              GM 正在叙述…
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combat Screen Components
// ---------------------------------------------------------------------------

interface CombatScreenProps {
  combat: CombatState;
  actor: Actor | null;
  combatNarrative: string;
  isNarrativeStreaming: boolean;
  selectedTarget: string | null;
  onTargetChange: (targetId: string) => void;
  selectedWeapon: string;
  onWeaponChange: (weapon: string) => void;
  onAction: (actionType: CombatActionType) => void;
  onClassFeatureAction: (feature: "second_wind" | "action_surge") => void;
  onFlee: () => void;
  loading: boolean;
}

function CombatScreen({
  combat,
  actor,
  combatNarrative,
  isNarrativeStreaming,
  selectedTarget,
  onTargetChange,
  selectedWeapon,
  onWeaponChange,
  onAction,
  onClassFeatureAction,
  onFlee,
  loading,
}: CombatScreenProps) {
  const currentParticipant = combat.participants.find((p) => p.id === combat.current_actor_id);
  const isPlayerTurn = currentParticipant?.is_player ?? false;
  const enemies = combat.participants.filter((p) => !p.is_player && p.hp > 0);
  const weapons = ["longsword", "shortsword", "dagger", "shortbow"];

  // Sort participants by initiative for initiative order display
  const sortedParticipants = [...combat.participants].sort((a, b) => b.initiative - a.initiative);

  const getHpStatus = (hp: number, max: number): "high" | "medium" | "low" => {
    const ratio = hp / max;
    if (ratio > 0.6) return "high";
    if (ratio > 0.3) return "medium";
    return "low";
  };

  return (
    <div className="combat-screen">
      {/* Combat Header with Round Info */}
      <div className="combat-header">
        <div className="combat-round">⚔️ 第 {combat.round_number} 轮</div>
        <div className={`combat-turn ${isPlayerTurn ? "player-turn" : "enemy-turn"}`}>
          {isPlayerTurn ? "▶ 你的回合" : `⏳ ${currentParticipant?.name} 的回合`}
        </div>
      </div>

      {/* Initiative Order - Clear Turn Order Display */}
      <div className="initiative-order-panel">
        <div className="initiative-order-header">
          <span className="initiative-order-title">先攻顺序</span>
          <span className="initiative-order-hint">按先攻值排序</span>
        </div>
        <div className="initiative-order-list">
          {sortedParticipants.map((participant, index) => {
            const isCurrent = participant.id === combat.current_actor_id;
            const isDefeated = participant.hp <= 0;
            return (
              <div
                key={participant.id}
                className={`initiative-item ${isCurrent ? "current" : ""} ${
                  participant.is_player ? "player" : "enemy"
                } ${isDefeated ? "defeated" : ""}`}
              >
                <div className="initiative-rank">{index + 1}</div>
                <div className="initiative-avatar">{participant.is_player ? "🧙" : "👹"}</div>
                <div className="initiative-info">
                  <div className="initiative-name">
                    {participant.name}
                    {isCurrent && <span className="turn-indicator">▶</span>}
                  </div>
                  <div className="initiative-hp-bar">
                    <div
                      className={`initiative-hp-fill ${getHpStatus(participant.hp, participant.hp_max)}`}
                      style={{ width: `${Math.max(0, (participant.hp / participant.hp_max) * 100)}%` }}
                    />
                  </div>
                </div>
                <div className="initiative-stats">
                  <div className="initiative-value" title="先攻值">
                    {participant.initiative}
                  </div>
                  <div className={`initiative-hp-text ${getHpStatus(participant.hp, participant.hp_max)}`}>
                    {participant.hp}/{participant.hp_max}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Combat Arena - Current Actors */}
      <div className="combat-arena">
        {combat.participants.map((participant) => (
          <div
            key={participant.id}
            className={`combat-actor ${participant.is_player ? "player" : "enemy"} ${
              participant.id === combat.current_actor_id ? "current" : ""
            } ${participant.hp <= 0 ? "defeated" : ""}`}
          >
            <div className="combat-actor-avatar">{participant.is_player ? "🧙" : "👹"}</div>
            <div className="combat-actor-info">
              <div className="combat-actor-name">
                {participant.name}
                {participant.id === combat.current_actor_id && (
                  <span className="current-turn-badge">当前</span>
                )}
              </div>
              <div className="combat-actor-stats">
                <span className="combat-actor-ac" title="护甲等级">🛡️ {participant.ac}</span>
              </div>
              <div className="combat-actor-hp-bar">
                <div
                  className={`combat-actor-hp-fill ${getHpStatus(participant.hp, participant.hp_max)}`}
                  style={{ width: `${Math.max(0, (participant.hp / participant.hp_max) * 100)}%` }}
                />
              </div>
              <div className={`combat-actor-hp-text ${getHpStatus(participant.hp, participant.hp_max)}`}>
                HP: {participant.hp}/{participant.hp_max}
              </div>
            </div>
            {participant.conditions.length > 0 && (
              <div className="combat-actor-conditions">
                {participant.conditions.map((c) => (
                  <span key={c} className="condition-tag">
                    {c}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="combat-narrative">
        {isNarrativeStreaming || combatNarrative ? (
          <div className="narration-block">
            <div className="narration-header">
              <span className="narration-icon">⚔️</span>
              <span className="narration-label">战斗叙事</span>
            </div>
            <div className="narration-content">
              <p className="narration-paragraph">{combatNarrative}</p>
              {isNarrativeStreaming && <span className="streaming-cursor">▌</span>}
            </div>
          </div>
        ) : (
          <div className="combat-hint">选择行动并点击执行</div>
        )}
      </div>

      {isPlayerTurn && (
        <div className="combat-actions">
          <div className="combat-action-row">
            <label>目标:</label>
            <select
              value={selectedTarget || ""}
              onChange={(e) => onTargetChange(e.target.value)}
              disabled={loading}
            >
              {enemies.map((enemy) => (
                <option key={enemy.id} value={enemy.id}>
                  {enemy.name} (HP: {enemy.hp}/{enemy.hp_max})
                </option>
              ))}
            </select>
          </div>
          <div className="combat-action-row">
            <label>武器:</label>
            <select
              value={selectedWeapon}
              onChange={(e) => onWeaponChange(e.target.value)}
              disabled={loading}
            >
              {weapons.map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
          </div>
          {/* Class feature buttons */}
          {actor?.character_class === "warrior" && (
            <div className="combat-class-features">
              {!actor.class_features?.second_wind_used && (
                <button
                  className="combat-btn second-wind"
                  onClick={() => onClassFeatureAction("second_wind")}
                  disabled={loading}
                  title="恢复 1d10 + 等级 生命值"
                >
                  ❤️ Second Wind
                </button>
              )}
              {!actor.class_features?.action_surge_used && (
                <button
                  className="combat-btn action-surge"
                  onClick={() => onClassFeatureAction("action_surge")}
                  disabled={loading}
                  title="额外获得一次行动"
                >
                  ⚡ Action Surge
                </button>
              )}
            </div>
          )}
          {actor?.character_class === "rogue" && (
            <div className="combat-class-features">
              <span className={`sneak-attack-badge ${actor.class_features?.sneak_attack_available ? "available" : "unavailable"}`}>
                🗡️ 偷袭 {actor.class_features?.sneak_attack_available ? "可用" : "已用"}
              </span>
            </div>
          )}
          <div className="combat-action-buttons">
            <button
              className="combat-btn attack"
              onClick={() => onAction("attack")}
              disabled={loading}
            >
              {loading ? "执行中…" : "⚔️ 攻击"}
            </button>
            <button
              className="combat-btn defend"
              onClick={() => onAction("defend")}
              disabled={loading}
            >
              🛡️ 防御
            </button>
            <button className="combat-btn flee" onClick={onFlee} disabled={loading}>
              🏃 逃跑
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface CombatEndScreenProps {
  combat: CombatState;
  onReturn: () => void;
  xpGained?: number;
  levelUp?: LevelUpInfo | null;
}

function CombatEndScreen({ combat, onReturn, xpGained, levelUp }: CombatEndScreenProps) {
  const isVictory = combat.status === "victory";
  const isEscape = combat.status === "escaped";

  return (
    <div className="combat-end-screen">
      <div className={`combat-result ${combat.status}`}>
        <div className="combat-result-icon">{isVictory ? "🏆" : isEscape ? "🏃" : "💀"}</div>
        <h2>
          {isVictory ? "🎉 战斗胜利！" : isEscape ? "🏃 成功逃脱" : "💀 战斗失败"}
        </h2>
        <p className="combat-result-description">
          {isVictory 
            ? "你成功击败了所有敌人！" 
            : isEscape 
              ? "你成功逃离了战斗。" 
              : "你在战斗中倒下了…"}
        </p>
        
        {/* XP Gained */}
        {isVictory && xpGained !== undefined && xpGained > 0 && (
          <div className="xp-gained-badge" style={{ marginBottom: 16 }}>
            获得 {xpGained} XP
          </div>
        )}
        
        {/* Level Up Notification */}
        {levelUp && (
          <div className="level-up-notification">
            <span className="level-up-icon">🎊</span>
            <div className="level-up-content">
              <div className="level-up-title">升级！Lv.{levelUp.old_level} → Lv.{levelUp.new_level}</div>
              <div className="level-up-details">
                HP +{levelUp.hp_increase} · 熟练加值 +{levelUp.new_proficiency_bonus}
              </div>
            </div>
          </div>
        )}
        
        <div className="combat-result-stats">
          <div className="result-stat">
            <span className="result-stat-label">战斗轮数</span>
            <span className="result-stat-value">{combat.round_number}</span>
          </div>
          <div className="result-stat">
            <span className="result-stat-label">存活着</span>
            <span className="result-stat-value">
              {combat.participants.filter(p => p.hp > 0).length}/{combat.participants.length}
            </span>
          </div>
        </div>
        <div className="combat-result-participants">
          {combat.participants.map((p) => (
            <div key={p.id} className={`result-participant ${p.is_player ? "player" : "enemy"}`}>
              <div className="result-participant-info">
                <span className="result-participant-avatar">{p.is_player ? "🧙" : "👹"}</span>
                <span className="result-participant-name">{p.name}</span>
              </div>
              <div className={`result-participant-status ${p.hp <= 0 ? "defeated" : "survived"}`}>
                {p.hp <= 0 ? (
                  <>
                    <span className="status-icon">💀</span>
                    <span>倒下</span>
                  </>
                ) : (
                  <>
                    <span className="status-icon">❤️</span>
                    <span>{p.hp}/{p.hp_max} HP</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
        {isVictory && (
          <div className="auto-return-hint">
            3秒后自动返回探索…
          </div>
        )}
        <button className="return-btn" onClick={onReturn}>
          {isVictory ? "继续冒险 →" : "返回"}
        </button>
      </div>
    </div>
  );
}

function CharacterCreationScreen({
  draft,
  actorPreview,
  pending,
  error,
  onNameChange,
  onClassChange,
  onAbilityChange,
  onAbilityGenerationChange,
  onRollAbilities,
  onSubmit,
}: {
  draft: CharacterDraft;
  actorPreview: Actor | null;
  pending: boolean;
  error: string | null;
  onNameChange: (value: string) => void;
  onClassChange: (value: CharacterClass) => void;
  onAbilityChange: (ability: keyof AbilityScores, value: number) => void;
  onAbilityGenerationChange: (method: "standard_array" | "random_4d6" | "manual") => void;
  onRollAbilities: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="creation-shell">
      <div className="creation-panel">
        <div className="creation-hero">
          <span className="creation-eyebrow">角色创建</span>
          <h2>先决定你是谁，再让故事开始。</h2>
          <p>
            选择职业，输入角色名，然后选择属性生成方式。可以使用标准数组、随机 4d6 取三规则，或手动输入。
          </p>
        </div>

        <div className="creation-form">
          <label className="creation-field">
            <span>角色名</span>
            <input
              value={draft.name}
              onChange={(event) => onNameChange(event.target.value)}
              placeholder="例如：莱娜、阿尔德、暮刃"
              disabled={pending}
            />
          </label>

          <div className="creation-field">
            <span>职业</span>
            <div className="class-grid">
              {(["warrior", "mage", "rogue"] as CharacterClass[]).map((characterClass) => (
                <button
                  key={characterClass}
                  type="button"
                  className={`class-card ${draft.characterClass === characterClass ? "selected" : ""}`}
                  onClick={() => onClassChange(characterClass)}
                  disabled={pending}
                >
                  <div className="class-card-title">{CLASS_LABELS[characterClass]}</div>
                  <div className="class-card-body">{CLASS_SUMMARIES[characterClass]}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="creation-field">
            <span>属性生成方式</span>
            <div className="ability-generation-options">
              <button
                type="button"
                className={`ability-gen-btn ${draft.abilityGeneration === "standard_array" ? "selected" : ""}`}
                onClick={() => onAbilityGenerationChange("standard_array")}
                disabled={pending}
              >
                <div className="ability-gen-title">标准数组</div>
                <div className="ability-gen-desc">15 / 14 / 13 / 12 / 10 / 8</div>
              </button>
              <button
                type="button"
                className={`ability-gen-btn ${draft.abilityGeneration === "random_4d6" ? "selected" : ""}`}
                onClick={() => onAbilityGenerationChange("random_4d6")}
                disabled={pending}
              >
                <div className="ability-gen-title">4d6 取三</div>
                <div className="ability-gen-desc">掷骰随机生成</div>
              </button>
              <button
                type="button"
                className={`ability-gen-btn ${draft.abilityGeneration === "manual" ? "selected" : ""}`}
                onClick={() => onAbilityGenerationChange("manual")}
                disabled={pending}
              >
                <div className="ability-gen-title">手动输入</div>
                <div className="ability-gen-desc">自定义数值</div>
              </button>
            </div>
          </div>

          <div className="creation-field">
            <div className="ability-inputs-header">
              <span>属性值</span>
              {draft.abilityGeneration === "standard_array" && (
                <span className="ability-array-hint">
                  将 15 / 14 / 13 / 12 / 10 / 8 分配到六个属性
                </span>
              )}
              {draft.abilityGeneration === "random_4d6" && (
                <button
                  type="button"
                  className="roll-abilities-btn"
                  onClick={onRollAbilities}
                  disabled={pending}
                  title="重新掷骰"
                >
                  🎲 重新掷骰
                </button>
              )}
            </div>
            <div className="ability-inputs-grid">
              {ABILITY_KEYS.map((key) => (
                <div key={key} className="ability-input-box">
                  <label className="ability-input-label">
                    {ABILITY_LABELS[key]} {ABILITY_ICONS[key]}
                  </label>
                  {draft.abilityGeneration === "standard_array" ? (
                    <select
                      value={draft.abilities[key]}
                      onChange={(e) => onAbilityChange(key, parseInt(e.target.value))}
                      disabled={pending}
                      className="ability-input"
                    >
                      {STANDARD_ARRAY.map((val) => {
                        const usedByAnother = ABILITY_KEYS.some(
                          (otherKey) => otherKey !== key && draft.abilities[otherKey] === val
                        );
                        return (
                          <option key={val} value={val} disabled={usedByAnother}>
                            {val}
                          </option>
                        );
                      })}
                    </select>
                  ) : (
                    <input
                      type="number"
                      min={3}
                      max={18}
                      value={draft.abilities[key]}
                      onChange={(e) => onAbilityChange(key, parseInt(e.target.value) || 10)}
                      disabled={pending}
                      className="ability-input"
                    />
                  )}
                  <span className="ability-modifier">
                    {formatModifier(getModifier(draft.abilities[key]))}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {error && <div className="creation-error">{error}</div>}

          <button className="creation-submit" onClick={onSubmit} disabled={pending || !draft.name.trim()}>
            {pending ? "创建中…" : "开始冒险"}
          </button>
        </div>
      </div>

      <div className="creation-preview">
        {actorPreview ? (
          <>
            <CharacterCard actor={actorPreview} />
            <div className="creation-preview-section">
              <h3>属性值</h3>
              <div className="stats-grid">
                {ABILITY_KEYS.map((key) => (
                  <AbilityScore key={key} ability={key} score={actorPreview.abilities[key]} />
                ))}
              </div>
            </div>
            <div className="creation-preview-section">
              <h3>技能熟练</h3>
              <SkillsList actor={actorPreview} compact />
            </div>
          </>
        ) : (
          <div className="sidebar-loading">输入姓名并选择职业后查看预览。</div>
        )}
      </div>
    </div>
  );
}

function createPreviewActor(draft: CharacterDraft): Actor | null {
  const trimmedName = draft.name.trim();
  if (!trimmedName) return null;

  // Hit dice match backend CLASS_HIT_DICE
  const classHitDie: Record<CharacterClass, number> = { warrior: 10, mage: 6, rogue: 8 };

  // Calculate HP: hit die max + CON modifier (matches backend)
  const conMod = getModifier(draft.abilities.con);
  const hp = classHitDie[draft.characterClass] + conMod;

  // Calculate AC based on abilities
  const dexMod = getModifier(draft.abilities.dex);
  let ac = 16;
  if (draft.characterClass === "mage") {
    ac = 10 + dexMod;
  } else if (draft.characterClass === "rogue") {
    ac = 11 + dexMod;
  }

  // Compute skills to match backend logic
  const profBonus = 2;
  const classProfSkills = CLASS_SKILLS[draft.characterClass] ?? [];
  const allSkills = [...SKILLS, ...EXTRA_SKILLS];
  const skills = allSkills.map((skill) => {
    const abilityMod = getModifier(draft.abilities[skill.ability]);
    const isProficient = classProfSkills.includes(skill.name);
    return {
      name: skill.name,
      ability: skill.ability,
      proficient: isProficient,
      modifier: abilityMod + (isProficient ? profBonus : 0),
    };
  });

  return {
    id: `preview-${draft.characterClass}`,
    name: trimmedName,
    character_class: draft.characterClass,
    abilities: draft.abilities,
    proficiency_bonus: profBonus,
    hp,
    hp_max: hp,
    ac,
    description: CLASS_SUMMARIES[draft.characterClass],
    conditions: [],
    skills,
  };
}

interface ParsedStreamEvent {
  event: string;
  data: unknown;
}

function parseStreamEvent(block: string): ParsedStreamEvent | null {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) return null;

  let event = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }

  if (dataLines.length === 0) return null;

  try {
    return {
      event,
      data: JSON.parse(dataLines.join("\n")),
    };
  } catch {
    return null;
  }
}

function getStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(SESSION_STORAGE_KEY);
}

function storeSessionId(sessionId: string | null) {
  if (typeof window === "undefined") return;

  if (sessionId) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    return;
  }

  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

function buildSessionHeaders(sessionId?: string | null, extraHeaders?: HeadersInit): HeadersInit {
  const headers = new Headers(extraHeaders);
  if (sessionId) {
    headers.set("X-Session-Id", sessionId);
  }
  return headers;
}

function restoreMessagesFromHistory(history: NarrativeHistoryEntry[]): Message[] {
  return history.slice(-MAX_RESTORED_HISTORY).flatMap((entry, index) => {
    const baseId = entry.created_at || Date.now() + index * 10;
    return [
      {
        id: baseId,
        role: "player" as const,
        text: entry.action_summary,
        timestamp: baseId,
      },
      {
        id: baseId + 1,
        role: "gm" as const,
        text: `${entry.narration}\n\n${entry.scene_progression}\n\n${entry.gm_prompt}`.trim(),
        resolution: {
          action_summary: entry.action_summary,
          resolution_type: entry.resolution_summary.resolution_type ?? "auto_success",
          check: entry.resolution_summary.check ?? null,
          skill_check: null,
          item_use: null,
          outcome: entry.resolution_summary.outcome ?? "success",
          effects: [],
          narration: entry.narration,
          scene_progression: entry.scene_progression,
          gm_prompt: entry.gm_prompt,
        },
        timestamp: baseId + 1,
      },
    ];
  });
}

function restoreTimelineFromHistory(history: NarrativeHistoryEntry[]): TimelineEntry[] {
  return history
    .slice(-MAX_RESTORED_HISTORY)
    .flatMap((entry, index) => {
      const baseId = entry.created_at || Date.now() + index * 10;
      const items: TimelineEntry[] = [
        {
          id: baseId,
          type: "action",
          title: entry.action_summary,
          outcome: entry.resolution_summary.outcome,
          timestamp: baseId,
        },
      ];

      if (entry.resolution_summary.resolution_type === "check" && entry.resolution_summary.check) {
        const check = entry.resolution_summary.check;
        const abilityName = ABILITY_LABELS[check.ability] ?? check.ability;
        const skillName = check.skill_name;
        const isSkillCheck = skillName !== null && skillName !== undefined;
        
        const title = isSkillCheck && skillName
          ? `${SKILL_LABELS[skillName] ?? skillName}检定 DC${check.dc}`
          : `${abilityName}检定 DC${check.dc}`;
        
        const totalModifier = check.modifier + check.proficiency_bonus;
        const modifierText = totalModifier >= 0 ? `+${totalModifier}` : `${totalModifier}`;
        
        let rollIndicator = "";
        if (check.roll === 20) {
          rollIndicator = "【大成功!】";
        } else if (check.roll === 1) {
          rollIndicator = "【大失败!】";
        }
        
        const details = `掷出 ${check.roll}${rollIndicator} ${modifierText} = ${check.total} vs DC ${check.dc} — ${entry.resolution_summary.outcome === "success" ? "成功" : "失败"}`;
        
        items.push({
          id: baseId + 1,
          type: "check",
          title,
          outcome: entry.resolution_summary.outcome,
          details,
          timestamp: baseId + 1,
        });
      }

      items.push(
        {
          id: baseId + 2,
          type: "scene",
          title: "场景推进",
          details: entry.scene_progression,
          timestamp: baseId + 2,
        },
        {
          id: baseId + 3,
          type: "scene",
          title: "GM 提示",
          details: entry.gm_prompt,
          timestamp: baseId + 3,
        },
      );

      return items;
    })
    .sort((left, right) => right.timestamp - left.timestamp);
}

function App() {
  const [sessionId, setSessionId] = useState<string | null>(() => getStoredSessionId());
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [health, setHealth] = useState<HealthStatus>("loading");
  const [sending, setSending] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [creatingCharacter, setCreatingCharacter] = useState(false);
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
  const [previousBootstrap, setPreviousBootstrap] = useState<BootstrapState | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>(PROVIDERS[0].id);
  const [streamingPreview, setStreamingPreview] = useState<StreamingPreview | null>(null);
  const [creationDraft, setCreationDraft] = useState<CharacterDraft>({
    name: "",
    characterClass: "warrior",
    abilities: { str: 15, dex: 14, con: 13, int: 12, wis: 10, cha: 8 },
    abilityGeneration: "standard_array",
  });
  const [creationError, setCreationError] = useState<string | null>(null);
  // Combat state
  const [combat, setCombat] = useState<CombatState | null>(null);
  // Save/Load state
  const [showLoadDialog, setShowLoadDialog] = useState(false);
  const [savesList, setSavesList] = useState<SaveFile[]>([]);
  const [loadingSaves, setLoadingSaves] = useState(false);
  const [loadingGame, setLoadingGame] = useState(false);
  const [combatLoading, setCombatLoading] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [selectedWeapon, setSelectedWeapon] = useState<string>("longsword");
  const [combatNarrative, setCombatNarrative] = useState<string>("");
  const [isCombatNarrativeStreaming, setIsCombatNarrativeStreaming] = useState(false);
  const [lastCombatXp, setLastCombatXp] = useState<number | undefined>(undefined);
  const [lastCombatLevelUp, setLastCombatLevelUp] = useState<LevelUpInfo | null>(null);
  // Map state
  const [showMap, setShowMap] = useState(false);

  const actorPreview = useMemo(() => createPreviewActor(creationDraft), [creationDraft]);
  const stateDiff = useMemo(() => computeStateDiff(bootstrap, previousBootstrap), [bootstrap, previousBootstrap]);
  const newConditions = useMemo(() => stateDiff.newConditions, [stateDiff]);
  const inAdventure = bootstrap?.phase === "adventure" && bootstrap.actor !== null;
  const gamePhase = bootstrap?.game_phase ?? "exploration";
  const inCombat = gamePhase === "combat";
  const combatEnded = gamePhase === "ended";



  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const response = await fetch(apiUrl("/health"));
        if (!cancelled) setHealth(response.ok ? "ok" : "error");
      } catch {
        if (!cancelled) setHealth("error");
      }
    };

    check();
    const intervalId = setInterval(check, 15_000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const storedSessionId = getStoredSessionId();
        const response = await fetch(apiUrl("/state/bootstrap"), {
          headers: buildSessionHeaders(storedSessionId),
        });

        if (!response.ok) {
          if (response.status === 404 && storedSessionId) {
            storeSessionId(null);
            setSessionId(null);

            const fallbackResponse = await fetch(apiUrl("/state/bootstrap"));
            if (!fallbackResponse.ok) return;
            const fallbackData: BootstrapState = await fallbackResponse.json();
            if (!cancelled) {
              setSessionId(fallbackData.session_id);
              storeSessionId(fallbackData.session_id);
              setBootstrap(fallbackData);
              setMessages([]);
              setTimeline([]);
            }
          }
          return;
        }

        const data: BootstrapState = await response.json();
        if (!cancelled) {
          setSessionId(data.session_id);
          storeSessionId(data.session_id);
          setBootstrap(data);
          setMessages(restoreMessagesFromHistory(data.narrative_history));
          setTimeline(restoreTimelineFromHistory(data.narrative_history));
        }
      } catch {
        // Keep loading placeholder.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const addToTimeline = (entry: Omit<TimelineEntry, "id" | "timestamp">) => {
    setTimeline((previous) => [
      { ...entry, id: Date.now() + Math.floor(Math.random() * 1000), timestamp: Date.now() },
      ...previous.slice(0, 49),
    ]);
  };

  const toggleTimelineEntry = (id: number) => {
    setTimeline((previous) =>
      previous.map((entry) => (entry.id === id ? { ...entry, expanded: !entry.expanded } : entry)),
    );
  };

  const recoverExpiredSession = async (message?: string) => {
    const response = await fetch(apiUrl("/state/bootstrap"));
    if (!response.ok) {
      throw new Error(`会话恢复失败 (${response.status})`);
    }

    const state: BootstrapState = await response.json();
    setSessionId(state.session_id);
    storeSessionId(state.session_id);
    setPreviousBootstrap(null);
    setBootstrap(state);
    setTimeline([]);
    setInput("");
    setStreamingPreview(null);
    setMessages(
      message
        ? [{ id: Date.now(), role: "system", text: message, timestamp: Date.now() }]
        : [],
    );
    return state;
  };

  const refreshState = async (overrideSessionId?: string) => {
    const sid = overrideSessionId ?? sessionId;
    const response = await fetch(apiUrl("/state"), {
      headers: buildSessionHeaders(sid),
    });
    if (!response.ok) {
      if (response.status === 404) {
        storeSessionId(null);
        setSessionId(null);
        return recoverExpiredSession("上一次会话已失效，已为你创建新会话。请重新创建角色。");
      }
      throw new Error(`状态同步失败 (${response.status})`);
    }
    const state: BootstrapState = await response.json();
    setSessionId(state.session_id);
    storeSessionId(state.session_id);
    setBootstrap(state);
    setMessages(restoreMessagesFromHistory(state.narrative_history));
    setTimeline(restoreTimelineFromHistory(state.narrative_history));
    return state;
  };

  const resetSession = async () => {
    if (resetting) return;

    setResetting(true);
    setCreationError(null);

    try {
      const response = await fetch(apiUrl("/reset"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId),
      });
      if (!response.ok) {
        if (response.status === 404) {
          storeSessionId(null);
          setSessionId(null);
          await recoverExpiredSession("会话已过期，已进入新的建角流程。");
          return;
        }
        throw new Error(await response.text());
      }
      const state: BootstrapState = await response.json();
      setPreviousBootstrap(null);
      setSessionId(state.session_id);
      storeSessionId(state.session_id);
      setBootstrap(state);
      setMessages([]);
      setTimeline([]);
      setInput("");
      // Clear combat state
      setCombat(null);
      setCombatNarrative("");
      setSelectedTarget(null);
      setIsCombatNarrativeStreaming(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `重置失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setResetting(false);
    }
  };

  const saveGame = async () => {
    if (saving) return;

    setSaving(true);
    try {
      const response = await fetch(apiUrl("/save"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId),
      });
      if (!response.ok) {
        if (response.status === 404) {
          storeSessionId(null);
          setSessionId(null);
          await recoverExpiredSession("会话已过期，已创建新会话。");
          return;
        }
        throw new Error(await response.text());
      }
      const result = await response.json();
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `游戏已存档 (${new Date(result.timestamp).toLocaleString("zh-CN")})`, timestamp: Date.now() },
      ]);
      addToTimeline({
        type: "system",
        title: "游戏存档",
        details: `存档时间: ${new Date(result.timestamp).toLocaleString("zh-CN")}`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `存档失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setSaving(false);
    }
  };

  const fetchSavesList = async () => {
    setLoadingSaves(true);
    try {
      const response = await fetch(apiUrl("/saves"));
      if (!response.ok) {
        throw new Error(`获取存档列表失败 (${response.status})`);
      }
      const data = await response.json();
      setSavesList(data.saves || []);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `获取存档列表失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setLoadingSaves(false);
    }
  };

  const openLoadDialog = async () => {
    await fetchSavesList();
    setShowLoadDialog(true);
  };

  const loadGame = async (saveId: string) => {
    if (loadingGame) return;

    setLoadingGame(true);
    try {
      const response = await fetch(apiUrl("/load"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ save_id: saveId }),
      });
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("存档文件不存在");
        } else if (response.status === 400) {
          const errorText = await response.text();
          throw new Error(`存档文件损坏: ${errorText}`);
        }
        throw new Error(`读档失败 (${response.status})`);
      }
      const data: BootstrapState = await response.json();
      
      // Update session and state
      setSessionId(data.session_id);
      storeSessionId(data.session_id);
      setBootstrap(data);
      setPreviousBootstrap(null);
      setMessages(restoreMessagesFromHistory(data.narrative_history));
      setTimeline(restoreTimelineFromHistory(data.narrative_history));
      setCombat(null);
      setCombatNarrative("");
      setSelectedTarget(null);
      setIsCombatNarrativeStreaming(false);
      setShowLoadDialog(false);
      
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `存档已加载，欢迎回来，${data.actor?.name || "冒险者"}！`, timestamp: Date.now() },
      ]);
      addToTimeline({
        type: "system",
        title: "读取存档",
        details: `角色: ${data.actor?.name || "未知"}, 场景: ${data.scene.name}`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((previous) => [
        ...previous,
        { id: Date.now(), role: "system", text: `读档失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setLoadingGame(false);
    }
  };

  const createCharacter = async () => {
    if (creatingCharacter) return;

    const name = creationDraft.name.trim();
    if (!name) {
      setCreationError("请输入角色名。");
      return;
    }

    setCreatingCharacter(true);
    setCreationError(null);

    try {
      // Validate standard array composition before submission
      if (creationDraft.abilityGeneration === "standard_array") {
        const values = Object.values(creationDraft.abilities).sort((a, b) => a - b);
        const expected = [8, 10, 12, 13, 14, 15];
        if (JSON.stringify(values) !== JSON.stringify(expected)) {
          setCreationError("标准数组模式下，六个属性必须恰好是 15、14、13、12、10、8 各一次。");
          setCreatingCharacter(false);
          return;
        }
      }

      const body: Record<string, unknown> = {
        name,
        character_class: creationDraft.characterClass,
        ability_generation: creationDraft.abilityGeneration,
      };

      // Backend ignores abilities when ability_generation is standard_array or random_4d6.
      // To respect the player's chosen/rolled abilities, send as manual with the chosen abilities.
      if (creationDraft.abilityGeneration === "standard_array" || creationDraft.abilityGeneration === "random_4d6") {
        body.ability_generation = "manual";
      }
      body.abilities = creationDraft.abilities;

      const response = await fetch(apiUrl("/character/create"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, { "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        if (response.status === 404) {
          storeSessionId(null);
          setSessionId(null);
          await recoverExpiredSession("会话已过期，已进入新的建角流程。");
          setCreationError("原会话已失效，请重新确认角色后开始。");
          return;
        }
        throw new Error(await response.text());
      }

      const newSessionId = response.headers.get("X-Session-Id") || sessionId;
      // The create endpoint returns a CharacterCard; fetch fresh bootstrap state to enter adventure.
      const state = await refreshState(newSessionId ?? undefined);
      setPreviousBootstrap(null);
      setMessages([
        {
          id: Date.now(),
          role: "system",
          text: `角色 ${name} 已创建，故事从 ${state.scene.name} 开始。`,
          timestamp: Date.now(),
        },
      ]);

      const genMethodLabel = {
        standard_array: "标准数组",
        random_4d6: "4d6 取三",
        manual: "手动输入",
      }[creationDraft.abilityGeneration];

      setTimeline([
        {
          id: Date.now(),
          type: "system",
          title: `创建角色：${name}`,
          details: `${CLASS_LABELS[creationDraft.characterClass]} · ${genMethodLabel}`,
          timestamp: Date.now(),
        },
      ]);
    } catch (error) {
      setCreationError(error instanceof Error ? error.message : String(error));
    } finally {
      setCreatingCharacter(false);
    }
  };

  const handleClassChange = (characterClass: CharacterClass) => {
    setCreationDraft((prev) => {
      const newAbilities =
        prev.abilityGeneration === "standard_array"
          ? getDefaultAbilities(characterClass)
          : prev.abilities;
      return { ...prev, characterClass, abilities: newAbilities };
    });
  };

  const handleAbilityGenerationChange = (method: "standard_array" | "random_4d6" | "manual") => {
    setCreationDraft((prev) => {
      let newAbilities = prev.abilities;
      if (method === "standard_array") {
        newAbilities = getDefaultAbilities(prev.characterClass);
      } else if (method === "random_4d6") {
        newAbilities = rollRandomAbilities();
      }
      return { ...prev, abilityGeneration: method, abilities: newAbilities };
    });
  };

  const handleAbilityChange = (ability: keyof AbilityScores, value: number) => {
    const clamped = Math.max(3, Math.min(18, value));
    setCreationDraft((prev) => ({
      ...prev,
      abilities: { ...prev.abilities, [ability]: clamped },
    }));
  };

  const handleRollAbilities = () => {
    setCreationDraft((prev) => ({
      ...prev,
      abilities: rollRandomAbilities(),
    }));
  };

  const handleExitClick = (direction: string) => {
    // Auto-fill movement command to input
    const movementCommands = ["前往", "去", "走向", "进入"];
    const command = movementCommands[Math.floor(Math.random() * movementCommands.length)];
    setInput(`${command}${direction}`);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    if (!inAdventure || !bootstrap?.actor) {
      setMessages((previous) => [
        ...previous,
        {
          id: Date.now(),
          role: "system",
          text: "请先创建角色后再提交行动。",
          timestamp: Date.now(),
        },
      ]);
      return;
    }

    const playerMessage: Message = {
      id: Date.now(),
      role: "player",
      text,
      timestamp: Date.now(),
    };
    setMessages((previous) => [...previous, playerMessage]);
    setInput("");
    setSending(true);
    setStreamingPreview({ narration: "", scene_progression: "", gm_prompt: "" });
    let partialPreview: StreamingPreview = { narration: "", scene_progression: "", gm_prompt: "" };

    addToTimeline({
      type: "action",
      title: `行动: ${text.slice(0, 30)}${text.length > 30 ? "..." : ""}`,
      details: text,
    });

    try {
      const response = await fetch(apiUrl("/action"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        }),
        body: JSON.stringify({
          scene_id: bootstrap.scene.id,
          actor: bootstrap.actor.name,
          intent: text,
          approach: text,
          provider: selectedProvider || undefined,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        if (response.status === 404) {
          storeSessionId(null);
          setSessionId(null);
          await recoverExpiredSession("会话已过期，已进入新的建角流程。");
          return;
        }
        setStreamingPreview(null);
        setMessages((previous) => [
          ...previous,
          {
            id: Date.now(),
            role: "system",
            text: `请求失败 (${response.status}): ${errorText}`,
            timestamp: Date.now(),
          },
        ]);
        addToTimeline({
          type: "system",
          title: `请求失败 (${response.status})`,
          outcome: "failure",
          details: errorText,
        });
        return;
      }

      if (!response.body) {
        throw new Error("后端未返回可读流。");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let completedResponse: ActionResponse | null = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";

        for (const block of blocks) {
          const parsed = parseStreamEvent(block);
          if (!parsed) continue;

          if (parsed.event === "chunk") {
            const payload = parsed.data as { field?: string; delta?: string };
            if (!payload.field || payload.delta === undefined) continue;

            if (payload.field === "narration") {
              partialPreview = { ...partialPreview, narration: partialPreview.narration + payload.delta };
            } else if (payload.field === "scene_progression") {
              partialPreview = {
                ...partialPreview,
                scene_progression: partialPreview.scene_progression + payload.delta,
              };
            } else if (payload.field === "gm_prompt") {
              partialPreview = {
                ...partialPreview,
                gm_prompt: partialPreview.gm_prompt + payload.delta,
              };
            }

            setStreamingPreview((previous) => {
              const next = previous ?? { narration: "", scene_progression: "", gm_prompt: "" };
              if (payload.field === "narration") {
                return { ...next, narration: next.narration + payload.delta };
              }
              if (payload.field === "scene_progression") {
                return { ...next, scene_progression: next.scene_progression + payload.delta };
              }
              if (payload.field === "gm_prompt") {
                return { ...next, gm_prompt: next.gm_prompt + payload.delta };
              }
              return next;
            });
            continue;
          }

          if (parsed.event === "error") {
            const payload = parsed.data as { message?: string };
            throw new Error(payload.message || "叙事流发生错误。");
          }

          if (parsed.event === "complete") {
            completedResponse = parsed.data as ActionResponse;
          }
        }
      }

      if (buffer.trim()) {
        const parsed = parseStreamEvent(buffer);
        if (parsed?.event === "complete") {
          completedResponse = parsed.data as ActionResponse;
        }
      }

      if (!completedResponse) {
        throw new Error("叙事流提前结束，未收到完成事件。");
      }

      const data = completedResponse;
      setStreamingPreview(null);
      setMessages((previous) => [
        ...previous,
        {
          id: Date.now(),
          role: "gm",
          text: `${data.narration}\n\n${data.scene_progression}\n\n${data.gm_prompt}`,
          resolution: data,
          timestamp: Date.now(),
        },
      ]);

      if (data.resolution_type === "check" && data.check) {
        const check = data.check;
        const abilityName = ABILITY_LABELS[check.ability] ?? check.ability;
        
        // Check for skill check (has skill_name or skill_check field)
        const skillName = data.skill_check?.skill ?? check.skill_name;
        const isSkillCheck = skillName !== null && skillName !== undefined;
        
        // Build skill check display text
        let title: string;
        let details: string;
        
        if (isSkillCheck && skillName) {
          const skillLabel = SKILL_LABELS[skillName] ?? skillName;
          title = `${skillLabel}检定 DC${check.dc}`;
        } else {
          title = `${abilityName}检定 DC${check.dc}`;
        }
        
        // Calculate total modifier (ability + proficiency)
        const totalModifier = check.modifier + check.proficiency_bonus;
        const modifierText = totalModifier >= 0 ? `+${totalModifier}` : `${totalModifier}`;
        
        // Determine special roll (natural 20 or 1)
        let rollIndicator = "";
        if (check.roll === 20) {
          rollIndicator = "【大成功!】";
        } else if (check.roll === 1) {
          rollIndicator = "【大失败!】";
        }
        
        details = `掷出 ${check.roll}${rollIndicator} ${modifierText} = ${check.total} vs DC ${check.dc} — ${data.outcome === "success" ? "成功" : "失败"}`;
        
        addToTimeline({
          type: "check",
          title,
          outcome: data.outcome,
          details,
        });
      } else {
        addToTimeline({
          type: "action",
          title: "自动成功",
          outcome: "success",
        });
      }

      addToTimeline({
        type: "scene",
        title: "场景推进",
        details: data.scene_progression,
      });

      addToTimeline({
        type: "scene",
        title: "GM 提示",
        details: data.gm_prompt,
      });

      setPreviousBootstrap(bootstrap);
      await refreshState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((previous) => {
        const nextMessages = [...previous];
        if (partialPreview.narration || partialPreview.scene_progression || partialPreview.gm_prompt) {
          nextMessages.push({
            id: Date.now(),
            role: "gm",
            text: `${partialPreview.narration}\n\n${partialPreview.scene_progression}\n\n${partialPreview.gm_prompt}`.trim(),
            streamingPreview: { ...partialPreview, interrupted: true },
            timestamp: Date.now(),
          });
        }
        nextMessages.push({
          id: Date.now() + 1,
          role: "system",
          text: `网络错误: ${message}`,
          timestamp: Date.now(),
        });
        return nextMessages;
      });
      setStreamingPreview(null);
      addToTimeline({
        type: "system",
        title: "网络错误",
        outcome: "failure",
        details: message,
      });
    } finally {
      setSending(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Combat Functions
  // ---------------------------------------------------------------------------

  const startCombat = async () => {
    if (!sessionId || combatLoading) return;
    setCombatLoading(true);
    try {
      const response = await fetch(apiUrl("/combat/start"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, { "Content-Type": "application/json" }),
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      const data = await response.json();
      setCombat(data);
      setSelectedTarget(data.participants.find((p: CombatParticipant) => !p.is_player)?.id || null);
      addToTimeline({
        type: "system",
        title: "战斗开始",
        details: `遭遇战开始，${data.participants.length} 名参与者`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", text: `战斗启动失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setCombatLoading(false);
    }
  };

  const executeClassFeatureAction = async (feature: "second_wind" | "action_surge") => {
    if (!sessionId || combatLoading) return;
    setCombatLoading(true);
    try {
      const response = await fetch(apiUrl("/action"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, {
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          scene_id: bootstrap?.scene.id || "combat",
          actor: bootstrap?.actor?.name || "",
          intent: feature,
          approach: "",
        }),
      });
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      const data = await response.json();
      addToTimeline({
        type: "action",
        title: feature === "second_wind" ? "Second Wind" : "Action Surge",
        outcome: "success",
        details: data.narration || "",
      });
      await refreshState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", text: message, timestamp: Date.now() },
      ]);
    } finally {
      setCombatLoading(false);
    }
  };

  const executeCombatAction = async (actionType: CombatActionType) => {
    if (!sessionId || !combat || combatLoading) return;
    if (combat.current_actor_id !== combat.participants.find((p) => p.is_player)?.id) {
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", text: "还不是你的回合", timestamp: Date.now() },
      ]);
      return;
    }
    setCombatLoading(true);
    setCombatNarrative("");
    setIsCombatNarrativeStreaming(true);
    try {
      const response = await fetch(apiUrl("/combat/action"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        }),
        body: JSON.stringify({
          action_type: actionType,
          target_id: selectedTarget,
          weapon: selectedWeapon,
        }),
      });
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      if (!response.body) {
        throw new Error("后端未返回可读流");
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalResult: CombatActionResult | null = null;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const parsed = parseStreamEvent(block);
          if (!parsed) continue;
          if (parsed.event === "chunk") {
            const payload = parsed.data as { field?: string; delta?: string };
            if (payload.field === "narrative" && payload.delta) {
              setCombatNarrative((prev) => prev + payload.delta);
            }
          } else if (parsed.event === "complete") {
            finalResult = parsed.data as CombatActionResult;
          }
        }
      }
      if (buffer.trim()) {
        const parsed = parseStreamEvent(buffer);
        if (parsed?.event === "complete") {
          finalResult = parsed.data as CombatActionResult;
        }
      }
      if (finalResult) {
        setCombat(finalResult.combat_state);
        // Capture XP and level-up info
        if (finalResult.xp_gained !== undefined) {
          setLastCombatXp(finalResult.xp_gained);
        }
        if (finalResult.level_up) {
          setLastCombatLevelUp(finalResult.level_up);
        }
        addToTimeline({
          type: "action",
          title: `战斗: ${actionType}`,
          outcome: finalResult.hit ? "success" : "failure",
          details: finalResult.hit
            ? `命中，造成 ${finalResult.damage} 点伤害`
            : "未命中",
        });
        // Refresh bootstrap state to get updated game_phase
        await refreshState();
        // If combat ended, show result and auto-return to exploration after delay
        if (finalResult.combat_state.status !== "active") {
          const isVictory = finalResult.combat_state.status === "victory";
          addToTimeline({
            type: "system",
            title: isVictory ? "战斗胜利" : "战斗结束",
            details: `战斗在 ${finalResult.combat_state.round_number} 轮后结束`,
          });
          // Auto-return to exploration after showing victory/defeat screen for 3 seconds
          if (isVictory) {
            setTimeout(() => {
              returnToAdventure();
              // Add victory message to chat
              setMessages((prev) => [
                ...prev,
                {
                  id: Date.now(),
                  role: "system",
                  text: finalResult.level_up 
                    ? `🎉 战斗胜利！你成功击败了所有敌人，升级到 Lv.${finalResult.level_up.new_level}！`
                    : "🎉 战斗胜利！你成功击败了所有敌人，继续你的冒险吧。",
                  timestamp: Date.now(),
                },
              ]);
            }, 3000);
          }
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", text: `战斗行动失败: ${message}`, timestamp: Date.now() },
      ]);
    } finally {
      setCombatLoading(false);
      setIsCombatNarrativeStreaming(false);
    }
  };

  const endCombat = async (reason: "flee" | "surrender" | "victory" | "defeat") => {
    if (!sessionId || !combat) return;
    try {
      const response = await fetch(apiUrl("/combat/end"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ reason }),
      });
      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }
      const data = await response.json();
      setCombat(null);
      // Refresh bootstrap state to get updated game_phase
      await refreshState();
      addToTimeline({
        type: "system",
        title: "战斗结束",
        details: `结果: ${data.status}`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "system", text: `结束战斗失败: ${message}`, timestamp: Date.now() },
      ]);
    }
  };

  const returnToAdventure = async () => {
    setCombat(null);
    setCombatNarrative("");
    setSelectedTarget(null);
    setLastCombatXp(undefined);
    setLastCombatLevelUp(null);
    await refreshState();
  };

  // Combat state is now managed by backend via game_phase
  // Local combat state is only used for combat UI details when in combat

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>幻界</h1>
          {inAdventure && bootstrap?.actor && (
            <MiniCharacterCard actor={bootstrap.actor} />
          )}
        </div>
        <div className="header-right">
          <div className="model-selector">
            <span className="model-selector-label">🧠 模型</span>
            <select
              value={selectedProvider}
              onChange={(event) => setSelectedProvider(event.target.value)}
              disabled={sending || creatingCharacter}
              title="选择叙事生成模型"
            >
              {PROVIDERS.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.label}
                </option>
              ))}
            </select>
          </div>
          <button className="header-button" onClick={saveGame} disabled={saving || sending || creatingCharacter || inCombat} title={inCombat ? "战斗中无法存档" : undefined}>
            {saving ? "存档中…" : "保存游戏"}
          </button>
          <button className="header-button" onClick={openLoadDialog} disabled={loadingSaves || sending || creatingCharacter}>
            {loadingSaves ? "加载中…" : "读取存档"}
          </button>
          <button className="header-button" onClick={resetSession} disabled={resetting || sending || creatingCharacter}>
            {resetting ? "重置中…" : "重置"}
          </button>
          {inAdventure && (
            <button 
              className="header-button map-button" 
              onClick={() => setShowMap(true)}
              disabled={sending || creatingCharacter}
              title="打开地图"
            >
              🗺️ 地图
            </button>
          )}
          {inCombat && <span className="combat-badge">⚔️ 战斗中</span>}
          <HealthDot status={health} />
          <span className="subtitle">
            {inCombat ? `第 ${combat?.round_number} 轮` : inAdventure ? "AI 跑团原型" : "角色创建阶段"}
          </span>
        </div>
      </header>

      <aside className="sidebar">
        <section>
          <h2>{inAdventure ? "当前场景" : "创建说明"}</h2>
          {bootstrap ? (
            <SceneCard
              scene={bootstrap.scene}
              playerName={bootstrap.actor?.id}
              previousScene={previousBootstrap?.scene ?? null}
              onExitClick={handleExitClick}
            />
          ) : (
            <div className="sidebar-loading">加载中…</div>
          )}
        </section>
        <section>
          <h2>{inCombat ? "战斗参与者" : inAdventure ? "角色" : "职业预览"}</h2>
          {inCombat && combat ? (
            <div className="combat-participants">
              {combat.initiative_order.map((participantId) => {
                const participant = combat.participants.find((p) => p.id === participantId);
                if (!participant) return null;
                const isCurrentTurn = participantId === combat.current_actor_id;
                const isPlayer = participant.is_player;
                return (
                  <div
                    key={participantId}
                    className={`combat-participant ${isCurrentTurn ? "current" : ""} ${isPlayer ? "player" : "enemy"}`}
                  >
                    <div className="combat-participant-initiative">{participant.initiative}</div>
                    <div className="combat-participant-info">
                      <div className="combat-participant-name">
                        {participant.name} {isCurrentTurn && "▶"}
                      </div>
                      <div className="combat-participant-hp">
                        HP: {participant.hp}/{participant.hp_max}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : inAdventure && bootstrap?.actor ? (
            <ul>
              <li className="active">{bootstrap.actor.name}</li>
            </ul>
          ) : actorPreview ? (
            <ul>
              <li className="active">{CLASS_LABELS[actorPreview.character_class ?? "warrior"]}</li>
            </ul>
          ) : (
            <div className="sidebar-loading">选择职业后查看。</div>
          )}
        </section>
      </aside>

      <main className="chat">
        {inCombat && combat ? (
          <CombatScreen
            combat={combat}
            actor={bootstrap?.actor || null}
            combatNarrative={combatNarrative}
            isNarrativeStreaming={isCombatNarrativeStreaming}
            selectedTarget={selectedTarget}
            onTargetChange={setSelectedTarget}
            selectedWeapon={selectedWeapon}
            onWeaponChange={setSelectedWeapon}
            onAction={executeCombatAction}
            onClassFeatureAction={executeClassFeatureAction}
            onFlee={() => endCombat("flee")}
            loading={combatLoading}
          />
        ) : combatEnded && combat ? (
          <CombatEndScreen
            combat={combat}
            onReturn={returnToAdventure}
            xpGained={lastCombatXp}
            levelUp={lastCombatLevelUp}
          />
        ) : inAdventure ? (
          <>
            <ScrollableNarrativeHistory
              messages={messages}
              streamingPreview={streamingPreview}
              sending={sending}
              gamePhase={gamePhase}
              xpGained={lastCombatXp}
              levelUp={lastCombatLevelUp}
            />
            <div className="input-bar">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && send()}
                placeholder={sending ? "裁定中…" : "输入你的行动（或先创建角色）…"}
                disabled={sending}
              />
              <button onClick={send} disabled={sending}>
                {sending ? "…" : "发送"}
              </button>
              <button
                className="combat-start-btn"
                onClick={startCombat}
                disabled={combatLoading || sending}
                title="开始战斗"
              >
                ⚔️ 战斗
              </button>
            </div>
          </>
        ) : (
          <CharacterCreationScreen
            draft={creationDraft}
            actorPreview={actorPreview}
            pending={creatingCharacter}
            error={creationError}
            onNameChange={(value) => setCreationDraft((previous) => ({ ...previous, name: value }))}
            onClassChange={handleClassChange}
            onAbilityChange={handleAbilityChange}
            onAbilityGenerationChange={handleAbilityGenerationChange}
            onRollAbilities={handleRollAbilities}
            onSubmit={createCharacter}
          />
        )}
      </main>

      <aside className="status-panel">
        {inAdventure && bootstrap?.actor ? (
          <>
            <section>
              <h2>角色状态</h2>
              <CharacterCard
                actor={bootstrap.actor}
                previousActor={previousBootstrap?.actor ?? null}
                newConditions={newConditions}
              />
            </section>

            <section>
              <h2>属性值</h2>
              <div className="stats-grid">
                {ABILITY_KEYS.map((key) => (
                  <AbilityScore
                    key={key}
                    ability={key}
                    score={bootstrap.actor!.abilities[key]}
                    changed={previousBootstrap?.actor?.abilities[key] !== bootstrap.actor!.abilities[key]}
                  />
                ))}
              </div>
            </section>

            <section>
              <h2>技能</h2>
              <SkillsList actor={bootstrap.actor} compact />
            </section>

            {bootstrap.actor.conditions && bootstrap.actor.conditions.length > 0 && (
              <section>
                <h2>状态效果</h2>
                <div className="status-effects">
                  {bootstrap.actor.conditions.map((condition, index) => (
                    <StatusEffect key={index} name={condition} isNew={newConditions.includes(condition)} />
                  ))}
                </div>
              </section>
            )}

            <section>
              <h2>场景时间</h2>
              <div className={`scene-time-display ${stateDiff.timeDelta !== undefined ? "changed" : ""}`}>
                <span className="scene-time-display-value">{bootstrap.scene.time ?? 0}</span>
                <span className="scene-time-display-unit">ticks</span>
              </div>
            </section>

            <RecentChanges diff={stateDiff} />
          </>
        ) : (
          <section>
            <h2>建角预览</h2>
            {actorPreview ? (
              <>
                <CharacterCard actor={actorPreview} />
                <div className="creation-preview-section">
                  <h3>属性值</h3>
                  <div className="stats-grid">
                    {ABILITY_KEYS.map((key) => (
                      <AbilityScore key={key} ability={key} score={actorPreview.abilities[key]} />
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="sidebar-loading">创建角色后，这里会显示实时状态。</div>
            )}
          </section>
        )}

        <section>
          <h2>{inAdventure ? "行动历史" : "创建记录"}</h2>
          <Timeline entries={timeline} onToggle={toggleTimelineEntry} />
        </section>
      </aside>

      {/* Load Game Dialog */}
      {showLoadDialog && (
        <div className="load-dialog-overlay" onClick={() => setShowLoadDialog(false)}>
          <div className="load-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="load-dialog-header">
              <h2>📂 读取存档</h2>
              <button className="close-btn" onClick={() => setShowLoadDialog(false)}>✕</button>
            </div>
            <div className="load-dialog-content">
              {loadingSaves ? (
                <div className="loading-saves">加载存档列表中…</div>
              ) : savesList.length === 0 ? (
                <div className="no-saves">暂无存档</div>
              ) : (
                <div className="saves-list">
                  {savesList.map((save) => (
                    <div key={save.save_id} className="save-item">
                      <div className="save-info">
                        <div className="save-name">{save.save_name}</div>
                        <div className="save-details">
                          {save.character_name ? (
                            <span className="save-character">
                              {save.character_name}
                              {save.class && ` · ${CLASS_LABELS[save.class as CharacterClass] || save.class}`}
                              {save.character_level !== null && ` Lv.${save.character_level}`}
                              {save.hp !== null && save.hp_max !== null && ` · HP ${save.hp}/${save.hp_max}`}
                            </span>
                          ) : (
                            <span className="save-no-character">未创建角色</span>
                          )}
                          {save.scene_name && (
                            <span className="save-scene"> 📍 {save.scene_name}</span>
                          )}
                        </div>
                        <div className="save-time">
                          {new Date(save.saved_at).toLocaleString("zh-CN")}
                        </div>
                      </div>
                      <button
                        className="load-btn"
                        onClick={() => loadGame(save.save_id)}
                        disabled={loadingGame}
                      >
                        {loadingGame ? "加载中…" : "读取"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Map Panel */}
      <MapPanel
        apiUrl={apiUrl}
        sessionId={sessionId}
        buildSessionHeaders={buildSessionHeaders}
        currentSceneId={bootstrap?.scene?.id ?? ""}
        isVisible={showMap}
        onClose={() => setShowMap(false)}
      />
    </div>
  );
}

export default App;
