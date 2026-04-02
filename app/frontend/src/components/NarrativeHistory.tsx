import { useEffect, useRef } from "react";

interface Effect {
  target: string;
  field: string;
  delta: number | string;
  description: string;
}

interface CheckDetail {
  ability: string;
  modifier: number;
  proficiency_bonus: number;
  advantage: boolean | null;
  roll: number;
  total: number;
  dc: number;
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

interface Message {
  id: number;
  role: "gm" | "player" | "system";
  text: string;
  resolution?: ActionResponse;
  streamingPreview?: {
    narration: string;
    scene_progression: string;
    gm_prompt: string;
    interrupted?: boolean;
  };
  timestamp: number;
}

interface NarrativeHistoryProps {
  messages: Message[];
  streamingPreview: {
    narration: string;
    scene_progression: string;
    gm_prompt: string;
    interrupted?: boolean;
  } | null;
  sending: boolean;
}

const ABILITY_LABELS: Record<string, string> = {
  str: "力量",
  dex: "敏捷",
  con: "体质",
  int: "智力",
  wis: "感知",
  cha: "魅力",
};

function CompactResolutionSummary({ res }: { res: ActionResponse }) {
  const isCheck = res.resolution_type === "check";
  const outcomeClass = res.outcome === "success" ? "outcome-success" : "outcome-failure";
  const outcomeLabel = res.outcome === "success" ? "成功" : "失败";

  return (
    <div className="compact-resolution">
      <div className="compact-resolution-header">
        <span className={`outcome-badge-sm ${outcomeClass}`}>
          {isCheck ? "检定" : "自动"} · {outcomeLabel}
        </span>
        {isCheck && res.check && (
          <span className="check-summary-sm">
            {ABILITY_LABELS[res.check.ability] ?? res.check.ability} d20={res.check.roll}
            {res.check.modifier >= 0 ? "+" : ""}
            {res.check.modifier}
            {res.check.proficiency_bonus > 0 ? `+${res.check.proficiency_bonus}` : ""}
            {" = "}
            {res.check.total} / DC{res.check.dc}
          </span>
        )}
      </div>
      {res.effects.length > 0 && (
        <div className="effects-sm">
          {res.effects.map((eff, index) => (
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
  );
}

export function NarrativeHistory({ messages, streamingPreview, sending }: NarrativeHistoryProps) {
  const gmMessages = messages.filter((m) => m.role === "gm").slice(-5);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, streamingPreview]);

  return (
    <div className="narrative-history">
      <div className="narrative-history-header">
        <span className="narrative-history-icon">📜</span>
        <span className="narrative-history-title">叙事历史</span>
      </div>
      <div className="narrative-list">
        {gmMessages.length === 0 && !sending && (
          <div className="narrative-empty">输入一个行动开始冒险…</div>
        )}
        {gmMessages.map((message) => (
          <div key={message.id} className="narrative-item">
            <div className="narrative-text">
              {(message.resolution?.narration || message.text)
                .split("\n")
                .map((line, i) =>
                  line.trim() ? <p key={i}>{line}</p> : null
                )}
            </div>
            {message.resolution && <CompactResolutionSummary res={message.resolution} />}
          </div>
        ))}
        {sending && streamingPreview && (
          <div className="narrative-item streaming">
            <div className="narrative-text">
              {streamingPreview.narration
                .split("\n")
                .map((line, i) =>
                  line.trim() ? <p key={i}>{line}</p> : null
                )}
            </div>
            <div className="streaming-indicator">
              <span className="streaming-dot" />
              GM 正在叙述…
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
