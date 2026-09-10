import { useEffect, useState } from 'react';
import { gameError, pendingCommand, recoverCommand } from '../gameApi';
export default function CommandFeedback({ apiUrl, sessionId, onRecovered }: {
  apiUrl: (path: string) => string; sessionId: string | null; onRecovered: () => Promise<unknown>;
}) {
  const [tick, setTick] = useState(0);
  const [notice, setNotice] = useState('');
  const [recovering, setRecovering] = useState(false);
  useEffect(() => {
    const update = () => setTick(t => t + 1);
    window.addEventListener('huanjie-command', update);
    const timer = setInterval(update, 1000);
    return () => { clearInterval(timer); window.removeEventListener('huanjie-command', update); };
  }, []);
  const pending = sessionId ? pendingCommand(sessionId) : null;
  const elapsed = pending ? Math.floor((Date.now() - pending.started) / 1000) : 0;
  void tick;
  async function recover() {
    if (!sessionId) return;
    setRecovering(true); setNotice('');
    try {
      const r = await recoverCommand(apiUrl, sessionId);
      if (r && !r.ok) setNotice(await gameError(r));
      else if (r) setNotice('上次结果已恢复。');
      await onRecovered();
    } catch (e) { setNotice(e instanceof Error ? e.message : '暂时无法恢复，请稍后重试。'); }
    finally { setRecovering(false); }
  }
  if (!pending) return notice ? <div className="command-feedback" role="status">{notice}<button onClick={() => setNotice('')}>关闭</button></div> : null;
  const usesModel = pending.command.kind === 'text' || pending.command.kind === 'talk';
  return <div className="command-feedback" role="status" aria-live="polite">
    <span>{pending.uncertain ? '上次行动结果待确认' : usesModel ? `正在准备回应${elapsed >= 2 ? ` · ${elapsed} 秒` : '…'}` : '正在结算…'}</span>
    {!pending.uncertain && elapsed >= 10 && <span className="feedback-hint">回应较慢，可以先查看地图或背包。</span>}
    {pending.uncertain && <><span>请先取回结果，再继续行动。</span><button disabled={recovering} onClick={() => void recover()}>{recovering ? '正在恢复…' : '恢复上次结果'}</button></>}
    {notice && <span>{notice}</span>}
  </div>;
}
