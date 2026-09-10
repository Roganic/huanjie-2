/** Player-facing prose stays separate from inspectable mechanics. */
export interface ActionPresentation {
  action_status?: 'executed' | 'blocked' | 'clarification' | 'read_only';
  feedback?: { summary: string; detail: string };
  narration: string;
  gm_narration?: string;
  gm?: { mode: string; notice?: string };
  outcome: 'success' | 'failure';
  check: { ability: string; skill_name?: string | null; roll: number; modifier: number; proficiency_bonus: number; total: number; dc: number; advantage: boolean | null } | null;
  adjudication?: { name: string; kind: string; stakes: string };
  effects: { description: string }[];
  world_events?: { id: string; title: string; narration: string }[];
}
const abilities: Record<string, string> = { str: '力量', dex: '敏捷', con: '体质', int: '智力', wis: '感知', cha: '魅力' };
export default function ActionMessage({ text, role, resolution: r }: { text: string; role: string; resolution?: ActionPresentation }) {
  const feedback = r?.feedback ?? (r?.action_status === 'blocked' ? { summary: '这次行动没有执行。', detail: r.narration } : undefined);
  const prose = feedback?.summary || r?.gm_narration || r?.narration || text;
  const resultLabel = r?.action_status === 'blocked' ? '未执行' : r?.action_status === 'clarification' ? '待明确' : r?.check ? `${r.adjudication?.kind === 'saving_throw' ? '豁免' : '检定'}${r.outcome === 'success' ? '成功' : '失败'}` : '';
  const hasDetails = !!r && !!(r.check || r.adjudication || r.gm_narration || r.gm?.notice || feedback || r.effects?.length);
  return <article className={`narrative-item message-${role}`}>
    {role === 'player' && <span className="message-speaker">你</span>}
    <div className="narrative-text">{prose.split('\n').filter(line => line.trim()).map((line, i) => <p key={i}>{line}</p>)}</div>
    {r?.world_events?.filter(e => !prose.includes(e.narration)).map(e => <p className="story-consequence" key={e.id}>{e.narration}</p>)}
    {(resultLabel || hasDetails) && <div className="message-result">
      {resultLabel && <span className={`result-label ${r?.outcome === 'failure' ? 'result-muted' : ''}`}>{resultLabel}{r?.check && ` · ${r.check.total} / ${r.check.dc}`}</span>}
      {hasDetails && <details className="narrative-facts"><summary>规则记录</summary>
        {feedback && <p>{feedback.detail}</p>}
        {r.gm_narration && !feedback && <p>{r.narration}</p>}
        {r.check && <p>{abilities[r.check.ability] || r.check.ability}{r.check.advantage === true ? ' · 优势' : r.check.advantage === false ? ' · 劣势' : ''}：d20 {r.check.roll} + 修正 {r.check.modifier} + 熟练 {r.check.proficiency_bonus} = {r.check.total}，难度 {r.check.dc}</p>}
        {r.adjudication && <p>{r.adjudication.stakes}</p>}
        {r.effects?.map((effect, i) => <p key={i}>{effect.description}</p>)}
        {r.gm?.notice && <p>{r.gm.notice}</p>}
      </details>}
    </div>}
  </article>;
}
