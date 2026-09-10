export interface Journey {
  content_version: string;
  locations: number; total_locations: number;
  conditions: { id: string; name: string; description: string; remaining: number | null }[];
  rest: { supply_item_id: string | null; quantity: number; description: string; long_rest_reason: string };
  ending: { id: string; title: string; description: string; level: number; xp: number; locations: number; clues: number } | null;
}

export default function JourneySummary({ journey }: { journey: Journey }) {
  return <section className="journey-summary" aria-label="冒险进展">
    <h2>冒险进展</h2>
    <p>已探索 {journey.locations} / {journey.total_locations} 处地点{journey.rest.supply_item_id && ` · 补给 ${journey.rest.quantity} 份`}</p>
    <details><summary>补给与休息</summary><p className="journey-rule">{journey.rest.description}</p></details>
    {journey.conditions.map(condition => <div className="journey-condition" key={condition.id} role="status">
      <strong>{condition.name}{condition.remaining !== null && ` · 剩余 ${condition.remaining} 个行动`}</strong>
      <p>{condition.description}</p>
    </div>)}
    {journey.ending && <div className="journey-ending" role="status">
      <span>本章结局 · 可继续探索</span>
      <h3>{journey.ending.title}</h3>
      <p>达成时：{journey.ending.description}</p>
      <details><summary>查看结算记录</summary>
        <p>达成时：等级 {journey.ending.level} · 累计经验 {journey.ending.xp}<br />探索 {journey.ending.locations} 处地点 · 记录 {journey.ending.clues} 条线索</p>
        <p>结局已保存，后续探索不会重复发放任务奖励。</p>
      </details>
    </div>}
  </section>;
}
