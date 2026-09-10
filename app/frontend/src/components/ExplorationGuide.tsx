import { useEffect, useState } from "react";
import "./ExplorationGuide.css";

interface QuestView { id: string; name: string; status_label: string; objective: string; reward: string }
export interface ChallengeChoice { approach_id?: string; consequence_id?: string }
interface Challenge {
  id: string; name: string; description: string; stakes: string; check_kind: string; dc: number; blocked_reason: string;
  approaches?: { id: string; name: string; description: string; dc: number }[];
  consequences?: { id: string; name: string; stakes: string }[];
}

interface Guidance {
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

interface Props {
  sessionId: string;
  revision: unknown;
  apiUrl: (path: string) => string;
  disabled: boolean;
  description: string;
  onTalk: (id: string, intent: string) => void;
  onChallenge: (id: string, name: string, choice?: ChallengeChoice) => void;
  onInteract: (id: string, intent: string) => void;
  onMove: (target: string) => void;
  onAttack: (target: string) => void;
}

const skillNames: Record<string, string> = { investigation: "调查", history: "历史", arcana: "奥秘", athletics: "运动", perception: "察觉", persuasion: "说服", insight: "洞察", stealth: "隐匿", survival: "生存", nature: "自然", religion: "宗教", medicine: "医药", deception: "欺瞒", intimidation: "威吓", performance: "表演", sleight_of_hand: "巧手", acrobatics: "体操", animal_handling: "驯兽" };

function ChallengeCard({ challenge: c, disabled, onChallenge }: { challenge: Challenge; disabled: boolean; onChallenge: Props['onChallenge'] }) {
  const [choice, setChoice] = useState<ChallengeChoice>({});
  const approach = c.approaches?.find(a => a.id === choice.approach_id);
  const consequence = c.consequences?.find(o => o.id === choice.consequence_id);
  return <div className="exploration-object">
    <strong>{c.name}</strong><p>{c.check_kind === 'automatic' ? '无需检定' : `难度 ${approach?.dc ?? c.dc}`}</p>
    <details><summary>{c.blocked_reason ? '查看原因' : '做法与风险'}</summary><p>{c.blocked_reason || c.description}</p>
      {!c.blocked_reason && <>
        <p>{consequence?.stakes ?? c.stakes}</p>
        {!!c.approaches?.length && <label>做法<select aria-label={`${c.name}的做法`} disabled={disabled} value={choice.approach_id ?? ''} onChange={e => setChoice({ ...choice, approach_id: e.target.value || undefined })}>
          <option value="">默认做法</option>{c.approaches.map(a => <option key={a.id} value={a.id}>{a.name} · 难度 {a.dc}</option>)}
        </select></label>}
        {approach && <p>{approach.description}</p>}
        {!!c.consequences?.length && <label>希望争取<select aria-label={`${c.name}的目标结果`} disabled={disabled} value={choice.consequence_id ?? ''} onChange={e => setChoice({ ...choice, consequence_id: e.target.value || undefined })}>
          <option value="">默认结果</option>{c.consequences.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select></label>}
      </>}
    </details>
    <button disabled={disabled || !!c.blocked_reason} aria-label={`尝试：${c.name}`} onClick={() => onChallenge(c.id, c.name, choice)}>{c.blocked_reason ? '暂不可尝试' : '尝试'}</button>
  </div>;
}

export default function ExplorationGuide({ sessionId, revision, apiUrl, disabled, description, onTalk, onChallenge, onInteract, onMove, onAttack }: Props) {
  const [data, setData] = useState<Guidance | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"nearby" | "challenges" | "journal" | null>("nearby");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const abort = new AbortController();
    async function load() {
      try {
        const response = await fetch(apiUrl("/exploration"), {
          headers: { "X-Session-Id": sessionId }, signal: abort.signal,
        });
        if (!response.ok) throw new Error("场景指引加载失败");
        const guidance: Guidance = await response.json();
        if (!abort.signal.aborted) { setData(guidance); setError(""); }
      } catch (err) {
        if (!abort.signal.aborted) setError(err instanceof Error ? err.message : "加载失败");
      }
    }
    void load();
    return () => abort.abort();
  }, [sessionId, revision, apiUrl, retry]);

  return <section className="exploration-guide" aria-label="当前场景">
    {error ? <p role="alert">{error} <button onClick={() => setRetry(n => n + 1)}>重试</button></p> : !data ? <p>正在确认当前位置…</p> : <>
      <div className="exploration-location"><strong>{data.location}</strong><span>{data.enemy_count ? `${data.danger} · ${data.enemy_count} 名敌人` : data.danger}</span></div>
      <p className="scene-intro">{description}</p>
      <p className="exploration-objective"><b>当前目标</b>{data.objective}</p>
      <div className="scene-controls">
        <nav className="exploration-actions exploration-exits" aria-label="相邻地点">{data.moves.map(move => <button key={move.target_scene_id} disabled={disabled} onClick={() => onMove(move.target_scene_id)}>{move.label} →</button>)}</nav>
        <div className="scene-tabs" aria-label="场景内容">
          {([['nearby', '此处可做'], ['challenges', '其他尝试'], ['journal', '任务与线索']] as const).map(([id, label]) => <button key={id} aria-expanded={tab === id} aria-controls="scene-content" onClick={() => setTab(tab === id ? null : id)}>{label}</button>)}
        </div>
      </div>
      {tab && <div id="scene-content" className="scene-content">
        {tab === 'nearby' && <>
          <div className="exploration-actions">{data.npcs.map(npc => <button key={npc.id} disabled={disabled} aria-label={`与${npc.name}交谈`} onClick={() => onTalk(npc.id, npc.intent)}>{npc.name}</button>)}</div>
          <div className="exploration-objects nearby-objects">{data.objects.filter(o => o.status !== 'completed').map(o => <div className="exploration-object" key={o.id}>
            <strong>{o.name}</strong><p>{o.reason || `${o.skill ? `${skillNames[o.skill] || o.skill} · 难度 ${o.dc}` : '无需检定'} · ${o.time_cost} 格时间`}</p>
            {o.rule_hint && <details><summary>行动风险</summary><p>{o.rule_hint}</p></details>}
            <button disabled={disabled || o.status !== 'available'} onClick={() => onInteract(o.id, o.intent)}>{o.status === 'locked' ? '尚未解锁' : o.intent}</button>
          </div>)}</div>
          <div className="exploration-objects nearby-objects">{data.challenges?.filter(c => !c.id.startsWith('social:') && !c.blocked_reason).map(c => <ChallengeCard key={`${data.location}:${c.id}`} challenge={c} disabled={disabled} onChallenge={onChallenge} />)}</div>
          <div className="exploration-actions">{data.targets.filter(t => t.attackable).map(t => <button key={t.id} disabled={disabled} onClick={() => onAttack(t.id)}>攻击{t.name}</button>)}</div>
          {!data.npcs.length && !data.objects.some(o => o.status !== 'completed') && !data.challenges?.some(c => !c.id.startsWith('social:') && !c.blocked_reason) && !data.targets.some(t => t.attackable) && <p>这里暂时没有可互动的对象。</p>}
        </>}
        {tab === 'challenges' && <>
          {!data.challenges?.length && <p>这里暂时没有额外挑战。</p>}
          <div className="exploration-objects">{data.challenges?.filter(c => !c.id.startsWith('social:')).map(c => <ChallengeCard key={`${data.location}:${c.id}`} challenge={c} disabled={disabled} onChallenge={onChallenge} />)}</div>
          {!!data.challenges?.some(c => c.id.startsWith('social:')) && <details><summary>其他社交尝试</summary>
            <div className="exploration-objects">{data.challenges.filter(c => c.id.startsWith('social:')).map(c => <ChallengeCard key={`${data.location}:${c.id}`} challenge={c} disabled={disabled} onChallenge={onChallenge} />)}</div>
          </details>}
        </>}
        {tab === 'journal' && <>
          {data.quests.map(q => <div className="exploration-clues" key={q.id}><b>{q.name} · {q.status_label}</b><p>{q.objective}</p>{q.reward && <small>奖励：{q.reward}</small>}</div>)}
          <h3>已知线索</h3>{data.clues.length ? <ul>{data.clues.map(c => <li key={c}>{c}</li>)}</ul> : <p>暂未收集到线索。</p>}
          {!!data.relationships?.length && <p>{data.relationships.map(r => `${r.name} · ${r.value > 0 ? '较友好' : r.value < 0 ? '较冷淡' : '平常'}`).join(' ／ ')}</p>}
          {data.objects.some(o => o.status === 'completed') && <details><summary>已完成互动</summary><p>{data.objects.filter(o => o.status === 'completed').map(o => o.name).join('、')}</p></details>}
        </>}
      </div>}
    </>}
  </section>;
}
