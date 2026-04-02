import { useEffect, useRef } from "react";
import "./NarrativeHistory.css";

export interface CheckDetail {
  ability: string;
  modifier: number;
  proficiency_bonus: number;
  advantage: boolean | null;
  roll: number;
  total: number;
  dc: number;
}

export interface Effect {
  target: string;
  field: string;
  delta: number | string;
  description: string;
}

export interface ActionResponse {
  action_summary: string;
  resolution_type: "auto_success" | "check";
  check: CheckDetail | null;
  outcome: "success" | "failure";
  effects: Effect[];
  narration: string;
  scene_progression: string;
  gm_prompt: string;
}

export interface StreamingPreview {
  narration: string;
  scene_progression: string;
  gm_prompt: string;
  interrupted?: boolean;
}

export interface CombatResultSummary {
  hit?: boolean;
  damage?: number;
  effects: Effect[];
}

export interface NarrativeEntry {
  id: number;
  narrative: string;
  sceneProgression?: string;
  gmPrompt?: string;
  resolution?: ActionResponse;
  combatResult?: CombatResultSummary;
  timestamp: number;
}

interface NarrativeHistoryProps {
  entries: NarrativeEntry[];
  loading?: boolean;
  streamingPreview?: StreamingPreview | null;
}

const ABILITY_LABELS: Record<string, string> = {
  str: "力量",
  dex: "敏捷",
  con: "体质",
  int: "智力",
  wis: "感知",
  cha: "魅力",
};

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ResolutionSummary({
  resolution,
  combatResult,
}: {
  resolution?: ActionResponse;
  combatResult?: CombatResultSummary;
}) {
  if (combatResult) {
    return (
      <div className="narrative-resolution">
        {combatResult.hit ? (
          <span className="resolution-badge combat-hit">
            命中
            {combatResult.damage !== undefined && (
              <span className="combat-damage">，造成 {combatResult.damage} 点伤害</span>
            )}
          </span>
        ) : (
          <span className="resolution-badge combat-miss">未命中</span>
        )}
        {combatResult.effects.length > 0 && (
          <div className="narrative-effects">
            {combatResult.effects.map((effect, idx) => (
              <span key={idx} className="effect-tag">{effect.description}</span>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (!resolution) return null;

  const isCheck = resolution.resolution_type === "check";
  const outcomeClass = resolution.outcome === "success" ? "success" : "failure";

  return (
    <div className="narrative-resolution">
      <span className={`resolution-badge ${outcomeClass}`}>
        {isCheck ? "检定" : "自动成功"} - {resolution.outcome === "success" ? "成功" : "失败"}
      </span>
      {isCheck && resolution.check && (
        <span className="check-summary">
          {ABILITY_LABELS[resolution.check.ability] ?? resolution.check.ability}
          {" "}d20={resolution.check.roll} / 总计 {resolution.check.total} / DC {resolution.check.dc}
        </span>
      )}
      {resolution.effects.length > 0 && (
        <div className="narrative-effects">
          {resolution.effects.map((effect, idx) => (
            <span
              key={idx}
              className={`effect-tag ${
                typeof effect.delta === "number" && effect.delta < 0
                  ? "negative"
                  : typeof effect.delta === "number" && effect.delta > 0
                    ? "positive"
                    : ""
              }`}
            >
              {effect.description}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function NarrativeCard({ entry }: { entry: NarrativeEntry }) {
  return (
    <div className="narrative-card">
      <div className="narrative-card-header">
        <span className="narrative-card-icon">📖</span>
        <span className="narrative-card-label">叙事</span>
        <span className="narrative-card-time">{formatTime(entry.timestamp)}</span>
      </div>
      <div className="narrative-card-body">
        {entry.resolution?.action_summary && (
          <div className="narrative-context">
            <span className="narrative-context-label">🎭 行动</span>
            <span className="narrative-context-text">{entry.resolution.action_summary}</span>
          </div>
        )}
        <p className="narrative-text">{entry.narrative}</p>
        <ResolutionSummary resolution={entry.resolution} combatResult={entry.combatResult} />
        {entry.sceneProgression && (
          <div className="narrative-section progression">
            <span className="section-label">🕯️ 场景推进</span>
            <p className="section-text">{entry.sceneProgression}</p>
          </div>
        )}
        {entry.gmPrompt && (
          <div className="narrative-section gm-prompt">
            <span className="section-label">🎯 GM 提示</span>
            <p className="section-text">{entry.gmPrompt}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingNarration() {
  return (
    <div className="narrative-card loading">
      <div className="narrative-card-header">
        <span className="narrative-card-icon">🎲</span>
        <span className="narrative-card-label">GM 正在叙述</span>
      </div>
      <div className="narrative-skeleton">
        <div className="skeleton-line" />
        <div className="skeleton-line short" />
        <div className="skeleton-line medium" />
      </div>
    </div>
  );
}

function StreamingNarrativeCard({ preview }: { preview: StreamingPreview }) {
  const hasNarration = preview.narration.trim().length > 0;
  const hasProgression = preview.scene_progression.trim().length > 0;
  const hasPrompt = preview.gm_prompt.trim().length > 0;

  if (!hasNarration && !hasProgression && !hasPrompt) {
    return <LoadingNarration />;
  }

  return (
    <div className="narrative-card streaming">
      <div className="narrative-card-header">
        <span className="narrative-card-icon">✨</span>
        <span className="narrative-card-label">叙事生成中</span>
      </div>
      <div className="narrative-card-body">
        {hasNarration && (
          <p className="narrative-text">
            {preview.narration}
            <span className="streaming-cursor">▌</span>
          </p>
        )}
        {hasProgression && (
          <div className="narrative-section progression">
            <span className="section-label">🕯️ 场景推进</span>
            <p className="section-text">{preview.scene_progression}</p>
          </div>
        )}
        {hasPrompt && (
          <div className="narrative-section gm-prompt">
            <span className="section-label">🎯 GM 提示</span>
            <p className="section-text">{preview.gm_prompt}</p>
          </div>
        )}
        {preview.interrupted && (
          <div className="interrupted-notice">叙事流已中断，已保留收到的片段。</div>
        )}
      </div>
    </div>
  );
}

export function NarrativeHistory({
  entries,
  loading,
  streamingPreview,
}: NarrativeHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, loading, streamingPreview]);

  const visibleEntries = entries.slice(-10);

  return (
    <div className="narrative-history">
      <div className="narrative-history-header">
        <span className="narrative-history-title">📜 叙事历史</span>
        <span className="narrative-history-count">最近 {visibleEntries.length} 条</span>
      </div>
      {visibleEntries.length === 0 && !loading && !streamingPreview && (
        <div className="narrative-empty">输入一个行动开始冒险…</div>
      )}
      {visibleEntries.map((entry) => (
        <NarrativeCard key={entry.id} entry={entry} />
      ))}
      {streamingPreview && <StreamingNarrativeCard preview={streamingPreview} />}
      {loading && !streamingPreview && <LoadingNarration />}
      <div ref={bottomRef} />
    </div>
  );
}
