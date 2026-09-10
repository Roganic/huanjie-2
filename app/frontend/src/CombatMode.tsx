import { useEffect, useRef, useState } from "react";

interface CombatantState {
  id: string;
  name: string;
  type: "player" | "enemy";
  hp: number;
  hp_max: number;
  ac: number;
  initiative: number;
  status: string;
}

interface CombatStartData {
  session_id: string;
  round_number: number;
  current_turn: string | null;
  turn_order: string[];
  combatants: CombatantState[];
  outcome: "ongoing" | "victory" | "defeat";
  log: string[];
  enemy_start_action?: {
    actor: string;
    hit: boolean;
    damage: number;
    updated_hp: number;
    narrative: string;
  } | null;
}

interface CombatStateData {
  session_id: string;
  round_number: number;
  current_turn: string | null;
  turn_order: string[];
  combatants: CombatantState[];
  outcome: "ongoing" | "victory" | "defeat";
  log: string[];
}

interface CombatActionResponse {
  hit: boolean | null;
  damage: number;
  updated_hp: number;
  narrative: string;
  outcome: string;
  actor: string;
  target: string;
  round_number: number;
  current_turn: string | null;
  turn_order: string[];
  enemy_actions: Array<{
    actor: string;
    hit: boolean;
    damage: number;
    updated_hp: number;
    narrative: string;
  }>;
  combat_ended: boolean;
  victory: boolean;
}

interface LogEntry {
  id: number;
  text: string;
  variant: "player" | "enemy" | "system";
  hit?: boolean | null;
  damage?: number;
}

interface CombatModeProps {
  sessionId: string | null;
  apiUrl: (path: string) => string;
  buildSessionHeaders: (sessionId?: string | null, extraHeaders?: HeadersInit) => HeadersInit;
  refreshState: () => Promise<unknown>;
  onExit: () => void;
}

function useTypewriter(text: string, speed: number = 18) {
  const [frame, setFrame] = useState({ text: "", length: 0 });
  useEffect(() => {
    let length = 0;
    const timer = setInterval(() => {
      length += 1;
      setFrame({ text, length });
      if (length >= text.length) clearInterval(timer);
    }, speed);
    return () => clearInterval(timer);
  }, [text, speed]);
  return frame.text === text ? text.slice(0, frame.length) : "";
}

function TypewriterLine({ text, className }: { text: string; className?: string }) {
  const displayed = useTypewriter(text);
  return (
    <span className={className}>
      {displayed}
      <span className="typewriter-cursor">|</span>
    </span>
  );
}

function LogItem({ entry, isLatest }: { entry: LogEntry; isLatest: boolean }) {
  const content = isLatest ? <TypewriterLine text={entry.text} /> : <span>{entry.text}</span>;
  const variantClass =
    entry.variant === "player" ? "log-player" : entry.variant === "enemy" ? "log-enemy" : "log-system";

  return (
    <div className={`combat-log-entry ${variantClass}`}>
      <div className="combat-log-badges">
        {entry.hit === true && entry.damage !== undefined && entry.damage > 0 && (
          <span className="combat-badge hit">命中 -{entry.damage}</span>
        )}
        {entry.hit === true && entry.damage === 0 && <span className="combat-badge hit">命中</span>}
        {entry.hit === false && <span className="combat-badge miss">未命中</span>}
      </div>
      <div className="combat-log-text">{content}</div>
    </div>
  );
}

export function CombatMode({ sessionId, apiUrl, buildSessionHeaders, refreshState, onExit }: CombatModeProps) {
  const [combatState, setCombatState] = useState<CombatStateData | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<"victory" | "defeat" | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    let mounted = true;
    const start = async () => {
      if (!sessionId) return;
      setPending(true);
      try {
        const response = await fetch(apiUrl("/combat/start"), {
          method: "POST",
          headers: buildSessionHeaders(sessionId),
        });
        if (!response.ok) throw new Error(await response.text());
        const data: CombatStartData = await response.json();
        if (!mounted) return;

        const initialLogs: LogEntry[] = (data.log || []).map((text, idx) => ({
          id: Date.now() + idx,
          text,
          variant: "system",
        }));

        // Handle enemy winning initiative and attacking immediately
        if (data.enemy_start_action) {
          const esa = data.enemy_start_action;
          initialLogs.push({
            id: Date.now() + 1000,
            text: esa.narrative,
            variant: "enemy",
            hit: esa.hit,
            damage: esa.damage,
          });
        }

        setCombatState(data);
        setLogs(initialLogs);
        setError(null);

        // If combat already ended from enemy start action
        if (data.outcome !== "ongoing") {
          const res = data.outcome === "victory" ? "victory" : "defeat";
          setResult(res);
          await refreshState();
          setTimeout(() => onExit(), 2500);
        } else {
          setResult(null);
          await refreshState();
        }
      } catch (e) {
        if (mounted) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mounted) setPending(false);
      }
    };
    start();
    return () => {
      mounted = false;
    };
  }, [sessionId, apiUrl, buildSessionHeaders, refreshState, onExit]);

  const doAction = async (actionType: "attack" | "skill_check") => {
    if (!sessionId || !combatState) return;
    setPending(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/combat/action"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId, { "Content-Type": "application/json" }),
        body: JSON.stringify({ action_type: actionType }),
      });
      if (!response.ok) throw new Error(await response.text());
      const data: CombatActionResponse = await response.json();

      const newLogs: LogEntry[] = [];
      newLogs.push({
        id: Date.now(),
        text: data.narrative,
        variant: "player",
        hit: data.hit,
        damage: data.damage,
      });
      data.enemy_actions.forEach((action, idx) => {
        newLogs.push({
          id: Date.now() + idx + 1,
          text: action.narrative,
          variant: "enemy",
          hit: action.hit,
          damage: action.damage,
        });
      });
      setLogs((prev) => [...prev, ...newLogs]);

      setCombatState((prev) => {
        if (!prev) return null;
        const updatedCombatants = prev.combatants.map((c) => {
          if (c.id === data.target) return { ...c, hp: data.updated_hp };
          // Apply enemy action damage to player combatants (single-player assumption)
          if (c.type === "player" && data.enemy_actions.length > 0) {
            return { ...c, hp: data.enemy_actions[0].updated_hp };
          }
          return c;
        });
        return {
          ...prev,
          round_number: data.round_number,
          current_turn: data.current_turn,
          turn_order: data.turn_order,
          combatants: updatedCombatants,
          outcome: data.combat_ended ? (data.victory ? "victory" : "defeat") : prev.outcome,
        };
      });

      if (data.combat_ended) {
        const res = data.victory ? "victory" : "defeat";
        setResult(res);
        await refreshState();
        setTimeout(() => {
          onExit();
        }, 2500);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const endCombat = async () => {
    if (!sessionId) return;
    setPending(true);
    try {
      const response = await fetch(apiUrl("/combat/end"), {
        method: "POST",
        headers: buildSessionHeaders(sessionId),
      });
      if (!response.ok) throw new Error(await response.text());
      await refreshState();
      onExit();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  const orderedCombatants = combatState
    ? [...combatState.combatants].sort((a, b) => b.initiative - a.initiative)
    : [];

  const playerCombatant = orderedCombatants.find((c) => c.type === "player");
  const isPlayerTurn = combatState?.current_turn === playerCombatant?.id;

  return (
    <div className="combat-mode">
      <div className="combat-header">
        <div className="combat-title">⚔️ 战斗模式</div>
        {combatState && (
          <div className="combat-meta">
            <span className="combat-round">第 {combatState.round_number} 轮</span>
            <span className="combat-turn">
              当前回合:{" "}
              {combatState.current_turn
                ? combatState.combatants.find((c) => c.id === combatState.current_turn)?.name || "未知"
                : "—"}
            </span>
          </div>
        )}
      </div>

      <div className="combat-initiative">
        <div className="initiative-label">先攻顺序</div>
        <div className="initiative-bar">
          {orderedCombatants.map((c) => {
            const isCurrent = combatState?.current_turn === c.id;
            return (
              <div
                key={c.id}
                className={`initiative-chip ${c.type} ${isCurrent ? "current" : ""} ${c.status !== "active" ? "down" : ""}`}
              >
                <span className="initiative-name">{c.name}</span>
                <span className="initiative-score">{c.initiative}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="combat-actors">
        {orderedCombatants.map((c) => {
          const hpPercent = Math.max(0, Math.min(100, (c.hp / c.hp_max) * 100));
          const hpStatus = hpPercent > 60 ? "high" : hpPercent > 30 ? "medium" : "low";
          const isCurrent = combatState?.current_turn === c.id;
          return (
            <div key={c.id} className={`combat-actor-card ${c.type} ${isCurrent ? "current" : ""}`}>
              <div className="combat-actor-header">
                <span className="combat-actor-name">
                  {c.type === "player" ? "🛡️" : "👹"} {c.name}
                </span>
                <span className="combat-actor-ac">AC {c.ac}</span>
              </div>
              <div className="combat-actor-hp">
                <div className="combat-hp-text">
                  <span>HP</span>
                  <span>
                    {c.hp} / {c.hp_max}
                  </span>
                </div>
                <div className="combat-hp-bar-bg">
                  <div className={`combat-hp-bar-fill ${hpStatus}`} style={{ width: `${hpPercent}%` }} />
                </div>
              </div>
              {c.status !== "active" && <div className="combat-actor-status">{c.status}</div>}
            </div>
          );
        })}
      </div>

      <div className="combat-log">
        {logs.length === 0 && <div className="combat-log-empty">战斗日志将显示在这里…</div>}
        {logs.map((entry, idx) => (
          <LogItem key={entry.id} entry={entry} isLatest={idx === logs.length - 1} />
        ))}
        {error && <div className="combat-log-error">错误: {error}</div>}
        <div ref={logEndRef} />
      </div>

      <div className="combat-actions">
        {result ? (
          <div className={`combat-result ${result}`}>
            {result === "victory" ? "🎉 战斗胜利！" : "💀 战斗失败…"}
          </div>
        ) : (
          <>
            <div className="combat-turn-hint">
              {isPlayerTurn ? (
                <span className="turn-badge player-turn">你的回合</span>
              ) : (
                <span className="turn-badge enemy-turn">敌方回合</span>
              )}
            </div>
            <div className="combat-action-buttons">
              <button
                className="combat-btn attack"
                onClick={() => doAction("attack")}
                disabled={pending || !isPlayerTurn}
              >
                {pending ? "裁定中…" : "⚔️ 攻击"}
              </button>
              <button
                className="combat-btn skill"
                onClick={() => doAction("skill_check")}
                disabled={pending || !isPlayerTurn}
              >
                {pending ? "裁定中…" : "🎲 技能检定"}
              </button>
              <button className="combat-btn end" onClick={endCombat} disabled={pending}>
                🏳️ 结束战斗
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
