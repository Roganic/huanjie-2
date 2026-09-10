import { useEffect, useState } from 'react';

type PendingEvent = { has_consequences?: boolean; priority?: string; id: string; title: string; remaining: number; clock: string; waiting_for_scene: boolean; waiting_for_conditions: boolean };
type EventState = { pending: PendingEvent[]; resolved: { id: string; title: string; status: string; reason: string }[] };

export default function EventTimeline({ sessionId, revision, apiUrl, compact = false }: {
  compact?: boolean;
  sessionId: string; revision: unknown; apiUrl: (path: string) => string;
}) {
  const [data, setData] = useState<EventState | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController();
    fetch(apiUrl('/events'), { headers: { 'X-Session-Id': sessionId }, signal: abort.signal })
      .then(async response => {
        if (!response.ok) throw new Error('事件进度暂时无法读取');
        return response.json() as Promise<EventState>;
      }).then(result => { if (!abort.signal.aborted) { setData(result); setError(''); } })
      .catch(() => { if (!abort.signal.aborted) setError('事件进度暂时无法读取，下次行动后会重新确认。'); });
    return () => abort.abort();
  }, [sessionId, revision, apiUrl]);
  if (compact && error) return null;
  if (error) return <p className="event-timeline" role="status">{error}</p>;
  if (!data || (!data.pending.length && !data.resolved.length)) return null;
  if (compact) {
    const upcoming = data.pending.filter(e => (e.has_consequences || e.priority === 'urgent' || e.priority === 'critical') && !e.waiting_for_scene && !e.waiting_for_conditions && e.remaining <= 2);
    return upcoming.length ? <div className="event-cue" role="status">{upcoming.slice(0, 2).map(e => `${e.title} · ${e.remaining > 0 ? `${e.remaining} ${e.clock === 'combat' ? '轮' : '格时间'}后` : '即将发生'}`).join(' ／ ')}</div> : null;
  }
  return <section className="event-timeline" aria-label="事件进度">
    {data.pending.length > 0 && <><b>正在推进的事情</b>
      {data.pending.map(event => <p key={event.id}>{event.title} · {event.waiting_for_scene ? '等待回到相关地点' : event.waiting_for_conditions ? '等待条件满足' : event.remaining > 0 ? `${event.remaining} ${event.clock === 'combat' ? '轮战斗' : '格场景时间'}后` : '即将发生'}</p>)}

    </>}
    {data.resolved.length > 0 && <details><summary>近期事件记录</summary>
      {data.resolved.slice(-6).map(event => <p key={event.id}>{event.title} · {event.status === 'fired' ? '已发生' : event.status === 'cancelled' ? '已取消' : '已失效'}{event.reason && `：${event.reason}`}</p>)}
    </details>}
  </section>;
}
