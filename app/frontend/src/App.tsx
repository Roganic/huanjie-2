import { useEffect, useRef, useState } from "react";
import "./App.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  id: number;
  role: "gm" | "player" | "system";
  text: string;
  resolution?: ActionResponse;
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
  description: string;
}

interface Scene {
  id: string;
  name: string;
  description: string;
  actors: string[];
}

interface BootstrapState {
  actor: Actor;
  scene: Scene;
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

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function ResolutionCard({ res }: { res: ActionResponse }) {
  const isCheck = res.resolution_type === "check";
  const outcomeClass =
    res.outcome === "success" ? "outcome-success" : "outcome-failure";
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
            {res.check.proficiency_bonus > 0 &&
              `+${res.check.proficiency_bonus}`}
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
            <div key={i} className="effect-item">
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

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [health, setHealth] = useState<HealthStatus>("loading");
  const [sending, setSending] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
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

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const playerMsg: Message = { id: Date.now(), role: "player", text };
    setMessages((prev) => [...prev, playerMsg]);
    setInput("");
    setSending(true);

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
          },
        ]);
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
        },
      ]);

      if (data.resolution_type === "check" && data.check) {
        const c = data.check;
        const abilityName = ABILITY_LABELS[c.ability] ?? c.ability;
        setLog((prev) => [
          ...prev,
          `${abilityName}检定 DC${c.dc} → ${c.total} ${data.outcome === "success" ? "成功" : "失败"}`,
        ]);
      } else {
        setLog((prev) => [...prev, `自动成功: ${text.slice(0, 20)}`]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "system",
          text: `网络错误: ${err instanceof Error ? err.message : String(err)}`,
        },
      ]);
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

      {/* Sidebar */}
      <aside className="sidebar">
        <section>
          <h2>场景</h2>
          {bootstrap ? (
            <>
              <ul>
                <li className="active">{bootstrap.scene.name}</li>
              </ul>
              <p className="scene-desc">{bootstrap.scene.description}</p>
            </>
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
              <h2>状态</h2>
              <div className="stat-row">
                <span className="label">姓名</span>
                <span className="value">{bootstrap.actor.name}</span>
              </div>
              <div className="stat-row">
                <span className="label">HP</span>
                <span className="value">{bootstrap.actor.hp} / {bootstrap.actor.hp_max}</span>
              </div>
              <div className="stat-row">
                <span className="label">熟练加值</span>
                <span className="value">+{bootstrap.actor.proficiency_bonus}</span>
              </div>
            </section>

            <section>
              <h2>属性</h2>
              {ABILITY_KEYS.map((key) => (
                <div key={key} className="stat-row">
                  <span className="label">{ABILITY_LABELS[key]}</span>
                  <span className="value">{bootstrap.actor.abilities[key]}</span>
                </div>
              ))}
            </section>
          </>
        ) : (
          <section>
            <h2>状态</h2>
            <div className="sidebar-loading">加载中…</div>
          </section>
        )}

        <section>
          <h2>事件日志</h2>
          {log.length === 0 && <div className="log-entry">暂无事件</div>}
          {log.map((entry, i) => (
            <div key={i} className="log-entry">
              {entry}
            </div>
          ))}
        </section>
      </aside>
    </div>
  );
}

export default App;
