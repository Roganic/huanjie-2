import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

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
type CharacterClass = "warrior" | "mage" | "rogue";

interface CheckDetail {
  ability: string;
  modifier: number;
  proficiency_bonus: number;
  advantage: boolean | null;
  roll: number;
  total: number;
  dc: number;
}

interface Effect {
  target: string;
  field: string;
  delta: number | string;
  description: string;
}

interface ActionResponse {
  action_summary: string;
  resolution_type: "auto_success" | "check";
  check: CheckDetail | null;
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
}

interface Scene {
  id: string;
  name: string;
  description: string;
  actors: string[];
  time?: number;
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
  actor: Actor | null;
  scene: Scene;
  narrative_history: NarrativeHistoryEntry[];
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

type Skill = {
  name: string;
  ability: keyof AbilityScores;
  proficient: boolean;
};

const SKILLS: Skill[] = [
  { name: "杂技", ability: "dex", proficient: false },
  { name: "运动", ability: "str", proficient: false },
  { name: "欺骗", ability: "cha", proficient: false },
  { name: "历史", ability: "int", proficient: false },
  { name: "威吓", ability: "cha", proficient: false },
  { name: "洞察", ability: "wis", proficient: true },
  { name: "调查", ability: "int", proficient: false },
  { name: "医药", ability: "wis", proficient: false },
  { name: "自然", ability: "int", proficient: false },
  { name: "察觉", ability: "wis", proficient: true },
  { name: "表演", ability: "cha", proficient: false },
  { name: "说服", ability: "cha", proficient: false },
  { name: "宗教", ability: "int", proficient: false },
  { name: "巧手", ability: "dex", proficient: true },
  { name: "隐匿", ability: "dex", proficient: true },
  { name: "生存", ability: "wis", proficient: false },
];

const CLASS_SKILLS: Record<CharacterClass, string[]> = {
  warrior: ["运动", "威吓", "察觉", "生存"],
  mage: ["历史", "调查", "奥秘", "宗教"],
  rogue: ["杂技", "欺骗", "洞察", "巧手", "隐匿"],
};

// Arcana skill for mage class proficiency
const EXTRA_SKILLS: Skill[] = [
  { name: "奥秘", ability: "int", proficient: false },
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

function NarrationBlock({
  text,
  variant = "result",
}: {
  text: string;
  variant?: "result" | "progression" | "gm_prompt";
}) {
  const paragraphs = text.split("\n").filter((paragraph) => paragraph.trim() !== "");
  const icon = variant === "progression" ? "🕯️" : variant === "gm_prompt" ? "🎯" : "📖";
  const label = variant === "progression" ? "场景波动" : variant === "gm_prompt" ? "GM 提示" : "行动结果";

  return (
    <div className={`narration-block ${variant}`}>
      <div className="narration-header">
        <span className="narration-icon">{icon}</span>
        <span className="narration-label">{label}</span>
      </div>
      <div className="narration-content">
        {paragraphs.map((paragraph, index) => (
          <p key={index} className="narration-paragraph">
            {paragraph}
          </p>
        ))}
      </div>
    </div>
  );
}

function LoadingNarration() {
  return (
    <div className="narration-block loading">
      <div className="narration-header">
        <span className="narration-icon">🎲</span>
        <span className="narration-label">GM 正在叙述</span>
      </div>
      <div className="narration-skeleton">
        <div className="skeleton-line" />
        <div className="skeleton-line short" />
        <div className="skeleton-line medium" />
      </div>
    </div>
  );
}

function StreamingNarrationCard({
  preview,
}: {
  preview: StreamingPreview;
}) {
  const hasNarration = preview.narration.trim().length > 0;
  const hasProgression = preview.scene_progression.trim().length > 0;
  const hasPrompt = preview.gm_prompt.trim().length > 0;

  return (
    <div className="resolution-card">
      {!hasNarration && !hasProgression && !hasPrompt && <LoadingNarration />}
      {hasNarration && <NarrationBlock text={preview.narration} variant="result" />}
      {hasProgression && <NarrationBlock text={preview.scene_progression} variant="progression" />}
      {hasPrompt && <NarrationBlock text={preview.gm_prompt} variant="gm_prompt" />}
      {preview.interrupted && (
        <div className="effects-list">
          <div className="effect-item negative">叙事流已中断，已保留收到的片段。可以重试本次行动。</div>
        </div>
      )}
    </div>
  );
}

function ResolutionCard({ res }: { res: ActionResponse }) {
  const isCheck = res.resolution_type === "check";
  const outcomeClass = res.outcome === "success" ? "outcome-success" : "outcome-failure";
  const outcomeLabel = res.outcome === "success" ? "成功" : "失败";

  return (
    <div className="resolution-card">
      <div className="system-info-section">
        <div className={`outcome-badge ${outcomeClass}`}>
          {isCheck ? "检定" : "自动成功"} - {outcomeLabel}
        </div>

        {isCheck && res.check && (
          <div className="check-details">
            <span className="check-ability">{ABILITY_LABELS[res.check.ability] ?? res.check.ability}</span>
            <span className="check-roll">
              d20={res.check.roll}
              {res.check.modifier >= 0 ? "+" : ""}
              {res.check.modifier}
              {res.check.proficiency_bonus > 0 && `+${res.check.proficiency_bonus}`}
              {" = "}
              <strong>{res.check.total}</strong>
            </span>
            <span className="check-dc">DC {res.check.dc}</span>
            {res.check.advantage !== null && (
              <span className="check-adv">{res.check.advantage ? "优势" : "劣势"}</span>
            )}
          </div>
        )}

        {res.effects.length > 0 && (
          <div className="effects-list">
            {res.effects.map((effect, index) => (
              <div
                key={index}
                className={`effect-item ${
                  typeof effect.delta === "number" && effect.delta > 0
                    ? "positive"
                    : typeof effect.delta === "number" && effect.delta < 0
                      ? "negative"
                      : ""
                }`}
              >
                {effect.description}
              </div>
            ))}
          </div>
        )}
      </div>

      <NarrationBlock text={res.narration} variant="result" />
      <NarrationBlock text={res.scene_progression} variant="progression" />
      <NarrationBlock text={res.gm_prompt} variant="gm_prompt" />
    </div>
  );
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
  const profBonus = actor.proficiency_bonus;
  const classProfSkills = CLASS_SKILLS[actor.character_class ?? "warrior"] ?? [];
  
  // Merge standard skills with extra skills (e.g., Arcana for mages)
  const allSkills = [...SKILLS, ...EXTRA_SKILLS];

  if (compact) {
    // Show only proficient skills (class proficiencies)
    const proficientSkills = allSkills.filter(
      (s) => classProfSkills.includes(s.name)
    );
    return (
      <div className="skills-list-compact">
        {proficientSkills.map((skill) => {
          const abilityMod = getModifier(actor.abilities[skill.ability]);
          const total = abilityMod + profBonus;
          return (
            <div key={skill.name} className="skill-item-compact proficient">
              <span className="skill-name">{skill.name}</span>
              <span className="skill-bonus">{formatModifier(total)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="skills-list">
      {allSkills.map((skill) => {
        const abilityMod = getModifier(actor.abilities[skill.ability]);
        const isProficient = classProfSkills.includes(skill.name);
        const total = abilityMod + (isProficient ? profBonus : 0);
        return (
          <div key={skill.name} className={`skill-item ${isProficient ? "proficient" : ""}`}>
            <span className="skill-dot">{isProficient ? "●" : "○"}</span>
            <span className="skill-name">{skill.name}</span>
            <span className="skill-ability">({ABILITY_LABELS[skill.ability]})</span>
            <span className="skill-bonus">{formatModifier(total)}</span>
          </div>
        );
      })}
    </div>
  );
}

function MiniCharacterCard({ actor }: { actor: Actor }) {
  const hpPercent = Math.round((actor.hp / actor.hp_max) * 100);
  let hpStatus: "high" | "medium" | "low" = "high";
  if (hpPercent <= 30) hpStatus = "low";
  else if (hpPercent <= 60) hpStatus = "medium";

  return (
    <div className="mini-character-card">
      <div className="mini-char-main">
        <div className="mini-char-avatar">{actor.character_class === "warrior" ? "⚔️" : actor.character_class === "mage" ? "🔮" : "🗡️"}</div>
        <div className="mini-char-info">
          <div className="mini-char-name">{actor.name}</div>
          <div className="mini-char-class">{actor.character_class ? CLASS_LABELS[actor.character_class] : "冒险者"}</div>
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
  return (
    <div className="character-card">
      <div className="character-header">
        <div className="character-avatar">
          {actor.character_class === "warrior" ? "⚔️" : actor.character_class === "mage" ? "🔮" : "🗡️"}
        </div>
        <div className="character-info">
          <div className="character-name">{actor.name}</div>
          <div className="character-level">
            {actor.character_class ? CLASS_LABELS[actor.character_class] : "冒险者"} Lv.{actor.level ?? 1} · 熟练加值 +{actor.proficiency_bonus}
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

      {actor.conditions && actor.conditions.length > 0 && (
        <div className="status-effects">
          {actor.conditions.map((condition, index) => (
            <StatusEffect key={index} name={condition} isNew={newConditions?.includes(condition)} />
          ))}
        </div>
      )}
    </div>
  );
}

function SceneCard({ scene, playerName, previousScene }: { scene: Scene; playerName?: string; previousScene?: Scene | null }) {
  const timeChanged = previousScene !== undefined && previousScene !== null && previousScene.time !== scene.time;

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
              <h3>职业技能</h3>
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

  // Base HP from hit die (max value) - matches backend CLASS_HIT_DICE
  const classBaseHp: Record<CharacterClass, number> = { warrior: 10, mage: 6, rogue: 8 };
  
  // Calculate CON modifier and final HP
  const conMod = getModifier(draft.abilities.con);
  const baseHp = classBaseHp[draft.characterClass];
  const hp = baseHp + conMod;

  // Calculate AC based on abilities and class
  const dexMod = getModifier(draft.abilities.dex);
  let ac: number;
  if (draft.characterClass === "mage") {
    ac = 10 + dexMod;  // Unarmored
  } else if (draft.characterClass === "rogue") {
    ac = 11 + dexMod;  // Leather armor
  } else {
    ac = 16;  // Warrior with heavy armor (no DEX bonus)
  }

  // Calculate skills with proficiency bonus
  const profBonus = 2;
  const classProfSkills = CLASS_SKILLS[draft.characterClass];
  const allSkills = [...SKILLS, ...EXTRA_SKILLS];
  const skills = allSkills.map(skill => {
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
        items.push({
          id: baseId + 1,
          type: "check",
          title: `${ABILITY_LABELS[check.ability] ?? check.ability}检定 DC${check.dc}`,
          outcome: entry.resolution_summary.outcome,
          details: `掷骰: d20=${check.roll} 调整值:${check.modifier >= 0 ? "+" : ""}${check.modifier}${
            check.proficiency_bonus > 0 ? `+${check.proficiency_bonus}` : ""
          } = ${check.total}`,
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
  const messagesEnd = useRef<HTMLDivElement>(null);

  const actorPreview = useMemo(() => createPreviewActor(creationDraft), [creationDraft]);
  const stateDiff = useMemo(() => computeStateDiff(bootstrap, previousBootstrap), [bootstrap, previousBootstrap]);
  const newConditions = useMemo(() => stateDiff.newConditions, [stateDiff]);
  const inAdventure = bootstrap?.phase === "adventure" && bootstrap.actor !== null;

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, streamingPreview]);

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

      // Backend ignores abilities when ability_generation is standard_array.
      // To respect the player's allocation, send as manual with the chosen abilities.
      if (creationDraft.abilityGeneration === "standard_array") {
        body.ability_generation = "manual";
        body.abilities = creationDraft.abilities;
      } else {
        body.abilities = creationDraft.abilities;
      }

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
        addToTimeline({
          type: "check",
          title: `${abilityName}检定 DC${check.dc}`,
          outcome: data.outcome,
          details: `掷骰: d20=${check.roll} 调整值:${check.modifier >= 0 ? "+" : ""}${check.modifier}${
            check.proficiency_bonus > 0 ? `+${check.proficiency_bonus}` : ""
          } = ${check.total}`,
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
          <button className="header-button" onClick={resetSession} disabled={resetting || sending || creatingCharacter}>
            {resetting ? "重置中…" : "重置"}
          </button>
          <HealthDot status={health} />
          <span className="subtitle">
            {inAdventure ? "AI 跑团原型" : "角色创建阶段"}
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
            />
          ) : (
            <div className="sidebar-loading">加载中…</div>
          )}
        </section>
        <section>
          <h2>{inAdventure ? "角色" : "职业预览"}</h2>
          {inAdventure && bootstrap?.actor ? (
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
        {inAdventure ? (
          <>
            <div className="messages">
              {messages.length === 0 && <div className="empty-hint">输入一个行动开始冒险…</div>}
              {messages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                  <div className="role">
                    {message.role === "gm" ? "GM" : message.role === "player" ? "玩家" : "系统"}
                  </div>
                  {message.resolution ? (
                    <ResolutionCard res={message.resolution} />
                  ) : message.streamingPreview ? (
                    <StreamingNarrationCard preview={message.streamingPreview} />
                  ) : (
                    message.text
                  )}
                </div>
              ))}
              {sending && streamingPreview && (
                <div className="message gm loading">
                  <div className="role">GM</div>
                  <StreamingNarrationCard preview={streamingPreview} />
                </div>
              )}
              <div ref={messagesEnd} />
            </div>
            <div className="input-bar">
              <input
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && send()}
                placeholder={sending ? "裁定中…" : "输入你的行动…"}
                disabled={sending}
              />
              <button onClick={send} disabled={sending}>
                {sending ? "…" : "发送"}
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
    </div>
  );
}

export default App;
