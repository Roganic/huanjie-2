interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  busy: boolean;
  disabled: boolean;
  blocked: boolean;
}

export default function ActionComposer({ value, onChange, onSend, busy, disabled, blocked }: Props) {
  const canSend = !busy && !disabled && !blocked && Boolean(value.trim());
  return <div className="action-composer">
    <div className="composer-caption"><span>你的下一步</span><span aria-live="polite">{busy ? '主持人正在回应…' : 'Enter 发送 · Shift + Enter 换行'}</span></div>
    <div className="input-bar">
      <textarea rows={2} value={value} onChange={e => onChange(e.target.value)}
        aria-label="你的行动" placeholder="你想说什么，或做什么？" disabled={disabled}
        onKeyDown={e => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend) onSend();
          }
        }} />
      <button onClick={onSend} disabled={!canSend}>{busy ? '等待回应' : '行动 →'}</button>
    </div>
  </div>;
}
