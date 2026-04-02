import { useEffect, useState } from "react";

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

interface CombatModeProps {
  sessionId: string | null;
  apiUrl: (path: string) => string;
  buildSessionHeaders: (sessionId?: string | null, extraHeaders?: HeadersInit) => HeadersInit;
  refreshState: () => Promise<unknown>;
  onExit: () => void;
}

export function CombatMode({ sessionId, apiUrl, buildSessionHeaders, refreshState, onExit }: CombatModeProps) {
  const [combatState, setCombatState] = useState<CombatStateData | null>(null);
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<"victory" | "defeat" | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

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
        const data: CombatStateData = await response.json();
        if (mounted) {
          setCombatState(data);
          setLog(data.log || []);
          setResult(null);
          setError(null);
        }
        await refreshState();
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
  }, [sessionId, apiUrl, buildSessionHeaders, refreshState]);

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

      const newLogs: string[] = [data.narrative];
      data.enemy_actions.forEach((action) => newLogs.push(action.narrative));
      setLog((prev) => [...prev, ...newLogs]);

      setCombatState((prev) => {
        if (!prev) return null;
        const updatedCombatants = prev.combatants.map((c) => {
          if (c.id === data.target) return { ...c, hp: data.updated_hp };
          const enemyAction = data.enemy_actions.find(() => c.type === "player");
          if (enemyAction && c.type === "player") return { ...c, hp: enemyAction.updated_hp };
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
        }, 2000);
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

  return (
    <div className="combat-mode">
      <div className="combat-header">
        <div className="combat-title">⚔️ 战斗模式</div>
        {combatState && (
          <div className="combat-meta">
            <span className="combat-round">第 {combatState.round_number} 轮</span>
            <span className="combat-turn">
              当前回合: {" "}
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
        {log.length === 0 && <div className="combat-log-empty">战斗日志将显示在这里…</div>}
        {log.map((entry, idx) => (
          <div key={idx} className="combat-log-entry">
            {entry}
          </div>
        ))}
        {error && <div className="combat-log-error">错误: {error}</div>}
      </div>

      <div className="combat-actions">
        {result ? (
          <div className={`combat-result ${result}`}>
            {result === "victory" ? "🎉 战斗胜利！" : "💀 战斗失败…"}
          </div>
        ) : (
          <>
            <button
              className="combat-btn attack"
              onClick={() => doAction("attack")}
              disabled={pending || combatState?.current_turn !== orderedCombatants.find((c) => c.type === "player")?.id}
            >
              {pending ? "裁定中…" : "⚔️ 攻击"}
            </button>
            <button
              className="combat-btn skill"
              onClick={() => doAction("skill_check")}
              disabled={pending || combatState?.current_turn !== orderedCombatants.find((c) => c.type === "player")?.id}
            >
              {pending ? "裁定中…" : "🎲 技能检定"}
            </button>
            <button className="combat-btn end" onClick={endCombat} disabled={pending}>
              🏳️ 结束战斗
            </button>
          </>
        )}
      </div>
    </div>
  );
}
