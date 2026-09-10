interface Props {
  name: string;
  location: string;
  reason: string;
  busy: boolean;
  error: string;
  onLoad: () => void;
  onRestart: () => void;
}

export default function AdventureDefeat({ name, location, reason, busy, error, onLoad, onRestart }: Props) {
  return <section className="adventure-defeat" aria-labelledby="defeat-title">
    <span className="defeat-eyebrow">冒险记录 · {location}</span>
    <h1 id="defeat-title">本次冒险已结束</h1>
    <p className="defeat-reason">{reason || `${name}的生命值已耗尽，无法继续行动。`}</p>
    <p>读取此前的存档，回到那一刻继续；也可以让{name}重新启程。</p>
    <div className="defeat-actions">
      <button className="header-button" disabled={busy} onClick={onLoad}>读取存档继续</button>
      <button className="header-button" disabled={busy} onClick={onRestart}>{busy ? "处理中…" : "重新冒险"}</button>
    </div>
    <p className="defeat-note">重新冒险将保留姓名、职业与初始属性，从当前模组的起点以 1 级开始。原冒险和存档保留。</p>
    {error && <p role="alert" className="inventory-error">{error}</p>}
  </section>;
}
