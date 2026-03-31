import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import "./App.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  id: number;
  role: "gm" | "player" | "system";
  text: string;
  resolution?: ActionResponse;
  timestamp: number;
}

type HealthStatus = "loading" | "ok" | "error";

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
  abilities: AbilityScores;
  proficiency_bonus: number;
  hp: number;
  hp_max: number;
  ac?: number;
  description: string;
  conditions?: string[];
}

interface Scene {
  id: string;
  name: string;
  description: string;
  actors: string[];
  environment?: string[];
  time?: number;
}

interface BootstrapState {
  actor: Actor;
  scene: Scene;
}

interface TimelineEntry {
  id: number;
  type: "action" | "check" | "system";
  title: string;
  outcome?: "success" | "failure";
  details?: string;
  timestamp: number;
  expanded?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ABILITY_LABELS: Record<string, string> = {
  str: "力量",
  dex: "敏捷",
  con: "体质",
  int: "智力",
  wis: "感知",
  cha: "魅力",
};

const ABILITY_KEYS: (keyof AbilityScores)[] = ["str", "dex", "con", "int", "wis", "cha"];

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

// ---------------------------------------------------------------------------
// Utility Functions
// ---------------------------------------------------------------------------

function getModifier(score: number): number {
  return Math.floor((score - 10) / 2);
}

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
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function ResolutionCard({ res }: { res: ActionResponse }) {
  const isCheck = res.resolution_type === "check";
  const outcomeClass = res.outcome === "success" ? "outcome-success" : "outcome-failure";
  const outcomeLabel = res.outcome === "success" ? "成功" : "失败";

  return (
    <div className="resolution-card">
      <div className={`outcome-badge ${outcomeClass}`}>
        {isCheck ? "检定" : "自动成功"} — {outcomeLabel}
      </div>

      {isCheck && res.check && (
        <div className="check-details">
          <span className="check-ability">
            {ABILITY_LABELS[res.check.ability] ?? res.check.ability}
          </span>
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
            <span className="check-adv">
              {res.check.advantage ? "优势" : "劣势"}
            </span>
          )}
        </div>
      )}

      {res.effects.length > 0 && (
        <div className="effects-list">
          {res.effects.map((e, i) => (
            <div 
              key={i} 
              className={`effect-item ${typeof e.delta === 'number' && e.delta > 0 ? 'positive' : typeof e.delta === 'number' && e.delta < 0 ? 'negative' : ''}`}
            >
              {e.description}
            </div>
          ))}
        </div>
      )}

      <div className="narration">{res.narration}</div>
    </div>
  );
}

function HealthDot({ status }: { status: HealthStatus }) {
  const label =
    status === "loading"
      ? "连接中…"
      : status === "ok"
        ? "后端已连接"
        : "后端离线";
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
          <span className={`hp-current ${changed ? 'changed' : ''} ${hp > (previousHp ?? hp) ? 'flash-positive' : isDamaged ? 'flash-negative' : ''}`}>
            {hp}
          </span>
          <span className="hp-separator">/</span>
          <span className="hp-max">{max}</span>
        </span>
      </div>
      <div className="hp-bar-container">
        <div 
          className={`hp-bar ${status} ${isDamaged ? 'damaged' : ''}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function AbilityScore({ 
  ability, 
  score, 
  changed 
}: { 
  ability: string; 
  score: number; 
  changed?: boolean;
}) {
  const modifier = getModifier(score);
  return (
    <div className={`stat-box ${changed ? 'changed' : ''}`}>
      <div className="stat-name">{ABILITY_LABELS[ability]} {ABILITY_ICONS[ability]}</div>
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
    <span className={`status-effect ${type} ${isNew ? 'new' : ''}`}>
      {icon} {name}
    </span>
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
        <div className="character-avatar">🧙</div>
        <div className="character-info">
          <div className="character-name">{actor.name}</div>
          <div className="character-level">熟练加值 +{actor.proficiency_bonus}</div>
        </div>
        {actor.ac !== undefined && (
          <div className="ac-display" title="护甲等级">
            <span className="ac-label">AC</span>
            <span className="ac-value">{actor.ac}</span>
          </div>
        )}
      </div>
      
      <HpBar 
        hp={actor.hp} 
        max={actor.hp_max} 
        previousHp={previousActor?.hp}
      />
      
      {actor.conditions && actor.conditions.length > 0 && (
        <div className="status-effects">
          {actor.conditions.map((condition, i) => (
            <StatusEffect key={i} name={condition} isNew={newConditions?.includes(condition)} />
          ))}
        </div>
      )}
    </div>
  );
}

function SceneCard({ scene, previousScene }: { scene: Scene; previousScene?: Scene | null }) {
  const isPlayer = (name: string) => name === "玩家" || name.includes("Aldric");
  const timeChanged = previousScene !== undefined && previousScene !== null && previousScene.time !== scene.time;
  
  return (
    <div className="scene-card">
      <div className="scene-name">{scene.name}</div>
      <p className="scene-desc">{scene.description}</p>
      
      {scene.time !== undefined && (
        <div className={`scene-time ${timeChanged ? 'changed' : ''}`}>
          <span className="scene-time-label">⏱️ 场景时间</span>
          <span className="scene-time-value">{scene.time}</span>
        </div>
      )}
      
      {scene.environment && scene.environment.length > 0 && (
        <div className="scene-actors">
          <div className="scene-actors-label">环境要素</div>
          <div className="actor-tags">
            {scene.environment.map((env, i) => (
              <span key={i} className="actor-tag">{env}</span>
            ))}
          </div>
        </div>
      )}
      
      {scene.actors.length > 0 && (
        <div className="scene-actors">
          <div className="scene-actors-label">在场角色</div>
          <div className="actor-tags">
            {scene.actors.map((actor, i) => (
              <span key={i} className={`actor-tag ${isPlayer(actor) ? 'player' : ''}`}>
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
  if (!current || !previous) {
    return { newConditions: [], removedConditions: [], hasChanges: false };
  }

  const currConds = current.actor.conditions ?? [];
  const prevConds = previous.actor.conditions ?? [];
  const newConditions = currConds.filter((c) => !prevConds.includes(c));
  const removedConditions = prevConds.filter((c) => !currConds.includes(c));
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
          <span className={`change-item ${diff.hpDelta > 0 ? 'positive' : 'negative'}`}>
            {diff.hpDelta > 0 ? '+' : ''}{diff.hpDelta} HP
          </span>
        )}
        {diff.timeDelta !== undefined && (
          <span className="change-item time">
            {diff.timeDelta > 0 ? '+' : ''}{diff.timeDelta} 时间
          </span>
        )}
        {diff.newConditions.map((c, i) => (
          <span key={`+${c}-${i}`} className="change-item positive">
            + {c}
          </span>
        ))}
        {diff.removedConditions.map((c, i) => (
          <span key={`-${c}-${i}`} className="change-item removed">
            - {c}
          </span>
        ))}
      </div>
    </div>
  );
}

function TimelineItem({ 
  entry, 
  onToggle 
}: { 
  entry: TimelineEntry; 
  onToggle: (id: number) => void;
}) {
  const outcomeClass = entry.outcome === "success" 
    ? "success" 
    : entry.outcome === "failure" 
      ? "failure" 
      : "info";
  
  return (
    <div className={`timeline-item ${outcomeClass} ${entry.expanded ? 'expanded' : ''}`}>
      <div className="timeline-dot" />
      <div className="timeline-content">
        <div className="timeline-header" onClick={() => onToggle(entry.id)}>
          <span className="timeline-title">
            {entry.outcome === "success" && "✓ "}
            {entry.outcome === "failure" && "✗ "}
            {entry.title}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span className="timeline-time">{formatTime(entry.timestamp)}</span>
            {entry.details && (
              <span className="timeline-expand">▼</span>
            )}
          </div>
        </div>
        {entry.expanded && entry.details && (
          <div className="timeline-details">{entry.details}</div>
        )}
      </div>
    </div>
  );
}

function Timeline({ 
  entries, 
  onToggle 
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
        <TimelineItem 
          key={entry.id} 
          entry={entry} 
          onToggle={onToggle}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [health, setHealth] = useState<HealthStatus>("loading");
  const [sending, setSending] = useState(false);
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
  const [previousBootstrap, setPreviousBootstrap] = useState<BootstrapState | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const messagesEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Health check on mount + periodic refresh
  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const res = await fetch("/api/health");
        if (!cancelled) setHealth(res.ok ? "ok" : "error");
      } catch {
        if (!cancelled) setHealth("error");
      }
    };

    check();
    const id = setInterval(check, 15_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Fetch bootstrap state on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/state/bootstrap");
        if (!res.ok) return;
        const data: BootstrapState = await res.json();
        if (!cancelled) setBootstrap(data);
      } catch {
        // Bootstrap fetch failed; UI will show loading placeholder
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const addToTimeline = useCallback((entry: Omit<TimelineEntry, "id" | "timestamp">) => {
    setTimeline((prev) => [
      {
        ...entry,
        id: Date.now(),
        timestamp: Date.now(),
      },
      ...prev.slice(0, 49), // Keep last 50 entries
    ]);
  }, []);

  const toggleTimelineEntry = useCallback((id: number) => {
    setTimeline((prev) =>
      prev.map((entry) =>
        entry.id === id ? { ...entry, expanded: !entry.expanded } : entry
      )
    );
  }, []);

  const stateDiff = useMemo(() => computeStateDiff(bootstrap, previousBootstrap), [bootstrap, previousBootstrap]);
  const newConditions = useMemo(() => stateDiff.newConditions, [stateDiff]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const playerMsg: Message = { 
      id: Date.now(), 
      role: "player", 
      text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, playerMsg]);
    setInput("");
    setSending(true);

    // Add to timeline
    addToTimeline({
      type: "action",
      title: `行动: ${text.slice(0, 30)}${text.length > 30 ? "..." : ""}`,
      details: text,
    });

    try {
      const res = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scene_id: bootstrap?.scene.id ?? "tavern-01",
          actor: bootstrap?.actor.name ?? "Aldric",
          intent: text,
          approach: text,
        }),
      });

      if (!res.ok) {
        const errText = await res.text();
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now(),
            role: "system",
            text: `请求失败 (${res.status}): ${errText}`,
            timestamp: Date.now(),
          },
        ]);
        addToTimeline({
          type: "system",
          title: `请求失败 (${res.status})`,
          outcome: "failure",
          details: errText,
        });
        return;
      }

      const data: ActionResponse = await res.json();

      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "gm",
          text: data.narration,
          resolution: data,
          timestamp: Date.now(),
        },
      ]);

      // Add resolution to timeline
      if (data.resolution_type === "check" && data.check) {
        const c = data.check;
        const abilityName = ABILITY_LABELS[c.ability] ?? c.ability;
        addToTimeline({
          type: "check",
          title: `${abilityName}检定 DC${c.dc}`,
          outcome: data.outcome,
          details: `掷骰: d20=${c.roll} 调整值:${c.modifier >= 0 ? '+' : ''}${c.modifier}${c.proficiency_bonus > 0 ? `+${c.proficiency_bonus}` : ''} = ${c.total}`,
        });
      } else {
        addToTimeline({
          type: "action",
          title: "自动成功",
          outcome: "success",
        });
      }

      // Store previous state for animation
      setPreviousBootstrap(bootstrap);

      // Re-fetch authoritative state so the status panel reflects any
      // mutations applied by the backend (HP, conditions, time, etc.)
      try {
        const stateRes = await fetch("/api/state/bootstrap");
        if (stateRes.ok) {
          const freshState: BootstrapState = await stateRes.json();
          setBootstrap(freshState);
        }
      } catch {
        // State refresh failed; status panel keeps previous values
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "system",
          text: `网络错误: ${errorMsg}`,
          timestamp: Date.now(),
        },
      ]);
      addToTimeline({
        type: "system",
        title: "网络错误",
        outcome: "failure",
        details: errorMsg,
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <h1>幻界</h1>
        <div className="header-right">
          <HealthDot status={health} />
          <span className="subtitle">AI 跑团原型</span>
        </div>
      </header>

      {/* Sidebar - Scene Panel */}
      <aside className="sidebar">
        <section>
          <h2>当前场景</h2>
          {bootstrap ? (
            <SceneCard scene={bootstrap.scene} previousScene={previousBootstrap?.scene ?? null} />
          ) : (
            <div className="sidebar-loading">加载中…</div>
          )}
        </section>
        <section>
          <h2>角色</h2>
          {bootstrap ? (
            <ul>
              <li className="active">{bootstrap.actor.name}</li>
            </ul>
          ) : (
            <div className="sidebar-loading">加载中…</div>
          )}
        </section>
      </aside>

      {/* Chat */}
      <main className="chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="empty-hint">输入一个行动开始冒险…</div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.role}`}>
              <div className="role">
                {m.role === "gm"
                  ? "GM"
                  : m.role === "player"
                    ? "玩家"
                    : "系统"}
              </div>
              {m.resolution ? <ResolutionCard res={m.resolution} /> : m.text}
            </div>
          ))}
          <div ref={messagesEnd} />
        </div>
        <div className="input-bar">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={sending ? "裁定中…" : "输入你的行动…"}
            disabled={sending}
          />
          <button onClick={send} disabled={sending}>
            {sending ? "…" : "发送"}
          </button>
        </div>
      </main>

      {/* Status Panel */}
      <aside className="status-panel">
        {bootstrap ? (
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
                    score={bootstrap.actor.abilities[key]}
                    changed={previousBootstrap?.actor.abilities[key] !== bootstrap.actor.abilities[key]}
                  />
                ))}
              </div>
            </section>

            {bootstrap.actor.conditions && bootstrap.actor.conditions.length > 0 && (
              <section>
                <h2>状态效果</h2>
                <div className="status-effects">
                  {bootstrap.actor.conditions.map((condition, i) => (
                    <StatusEffect key={i} name={condition} isNew={newConditions.includes(condition)} />
                  ))}
                </div>
              </section>
            )}

            <section>
              <h2>场景时间</h2>
              <div className={`scene-time-display ${stateDiff.timeDelta !== undefined ? 'changed' : ''}`}>
                <span className="scene-time-display-value">{bootstrap.scene.time ?? 0}</span>
                <span className="scene-time-display-unit">ticks</span>
              </div>
            </section>

            <RecentChanges diff={stateDiff} />
          </>
        ) : (
          <section>
            <h2>状态</h2>
            <div className="sidebar-loading">加载中…</div>
          </section>
        )}

        <section>
          <h2>行动历史</h2>
          <Timeline entries={timeline} onToggle={toggleTimelineEntry} />
        </section>
      </aside>
    </div>
  );
}

export default App;
