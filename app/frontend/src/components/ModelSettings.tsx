import { useEffect, useRef, useState } from 'react';
import './ModelSettings.css';

type Settings = { enabled: boolean; style: string; url: string; model: string; authoring_model?: string; has_key: boolean; environment_overrides: string[]; managed?: boolean };
type Metrics = { turns: number; calls: number; fallbacks: number; input_tokens: number; output_tokens: number; p50_ms: number | null; p95_ms: number | null };
export default function ModelSettings({ apiUrl, sessionId, onClose, onSaved }: {
  apiUrl: (path: string) => string; sessionId: string | null; onClose: () => void; onSaved: (label: string) => void;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    const controller = new AbortController();
    async function load() {
      try {
        const r = await fetch(apiUrl('/gm/settings'), { signal: controller.signal });
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || '设置加载失败');
        setSettings(body);
        if (sessionId) {
          const m = await fetch(apiUrl('/gm/metrics'), { headers: { 'X-Session-Id': sessionId }, signal: controller.signal });
          if (m.ok) setMetrics(await m.json());
        }
      } catch (e) { if (!controller.signal.aborted) setNotice(e instanceof Error ? e.message : '无法连接后端'); }
    }
    void load();
    return () => controller.abort();
  }, [apiUrl, sessionId]);
  const update = (change: Partial<Settings>) => { setSettings(s => s && { ...s, ...change }); setNotice(''); };
  async function submit(test: boolean) {
    if (!settings || busy) return;
    setBusy(true); setNotice(test ? '正在测试连接，通常需要几秒…' : '正在保存…');
    try {
      const { enabled, style, url, model, authoring_model = '' } = settings;
      const r = await fetch(apiUrl(test ? '/gm/test' : '/gm/settings'), {
        method: test ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(25_000),
        body: JSON.stringify({ enabled, style, url, model, authoring_model, api_key: key }),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || '设置未完成');
      if (test) {
        setNotice(body.ok ? `连接成功 · ${(body.elapsed_ms / 1000).toFixed(1)} 秒 · 输入 ${body.usage.input_tokens ?? '未知'} / 输出 ${body.usage.output_tokens ?? '未知'} tokens\n${body.message}\n测试未修改冒险进度；新设置需保存后生效。` : body.message);
      } else {
        setSettings(body); setKey(''); onSaved(body.status.label);
        setNotice('已保存，下次行动生效。当前冒险和存档保持不变。');
      }
    } catch (e) { setNotice(e instanceof Error && e.name === 'TimeoutError' ? '请求超时，请检查连接后重试。' : e instanceof Error ? e.message : '连接失败'); }
    finally { setBusy(false); }
  }
  return <dialog className="model-settings" ref={dialog} onCancel={e => { if (busy) e.preventDefault(); else onClose(); }}>
    <div className="model-settings-header"><div><span className="settings-eyebrow">主持偏好</span><h2>模型设置</h2></div><button onClick={onClose} disabled={busy} aria-label="关闭模型设置">×</button></div>
    <p className="settings-muted">{settings?.managed ? '此网站使用统一配置的主持，你可以检查当前连接和冒险用量。' : '为这段冒险选择主持。切换服务不会重置角色或剧情。'}</p>
    {settings?.managed && <section className="settings-managed"><h3>{settings.model || '尚未配置模型'}</h3><p className="settings-muted">{settings.enabled ? 'AI 主持已启用' : '固定主持'}</p><button disabled={busy || !settings.enabled} onClick={() => void submit(true)}>测试当前主持</button></section>}
    {settings && !settings.managed && <form onSubmit={e => { e.preventDefault(); void submit(false); }}>
      <fieldset disabled={busy}>
        <label className="settings-toggle"><input type="checkbox" checked={settings.enabled} onChange={e => update({ enabled: e.target.checked })} /> 启用 AI 主持</label>
        <p className="settings-muted">关闭后使用固定主持，原有操作仍可使用。</p>
        <label>服务类型<select value={settings.style} onChange={e => update({ style: e.target.value })}>
          <option value="qwen">阿里云百炼 / 千问</option><option value="glm">智谱 / GLM</option><option value="deepseek">DeepSeek</option><option value="kimi">Kimi</option><option value="standard">其他兼容服务</option>
        </select></label>
        <label>接口地址<input type="url" value={settings.url} placeholder="粘贴服务商提供的 OpenAI 兼容地址" onChange={e => update({ url: e.target.value })} /></label>
        <label>模型名称<input value={settings.model} placeholder="填写支持工具调用的模型名称" onChange={e => update({ model: e.target.value })} /></label>
        <label>模组创作模型<input value={settings.authoring_model ?? ''} placeholder="留空则使用同一个模型" onChange={e => update({ authoring_model: e.target.value })} /></label>
        <p className="settings-muted">创作可选同一服务的更强模型，日常冒险仍使用上面的模型。</p>
        <label>API 密钥<input type="password" autoComplete="new-password" value={key} placeholder={settings.has_key ? '已保存密钥；留空即可保留' : '粘贴 API Key'} onChange={e => { setKey(e.target.value); setNotice(''); }} /></label>
        <p className="settings-muted">密钥只保存在本机后端，不会放入游戏存档。更换接口地址时需填写对应密钥。</p>
        {settings.environment_overrides.length > 0 && <p className="settings-notice">当前有环境变量覆盖配置，需移除覆盖后才能在这里保存。</p>}
        <div className="settings-actions"><button type="button" onClick={() => void submit(true)}>测试连接</button><button className="settings-primary" type="submit" disabled={settings.environment_overrides.length > 0}>保存设置</button></div>
        <p className="settings-muted">测试会发起一次真实模型调用，按服务商规则消耗额度。</p>
      </fieldset>
    </form>}
    {notice && <p className="settings-notice" role="status">{notice}</p>}
    {metrics && <section className="settings-metrics"><h3>这段冒险的近期用量</h3><p className="settings-muted">最近最多 40 轮，包含读档恢复的记录；不含连接测试，非账户账单。</p>
      <div className="metrics-grid"><span>完成回合<strong>{metrics.turns}</strong></span><span>模型调用<strong>{metrics.calls}</strong></span><span>输入 tokens<strong>{metrics.input_tokens.toLocaleString()}</strong></span><span>输出 tokens<strong>{metrics.output_tokens.toLocaleString()}</strong></span><span>中位耗时<strong>{metrics.p50_ms === null ? '—' : `${(metrics.p50_ms / 1000).toFixed(1)} 秒`}</strong></span><span>95% 回合耗时不超过<strong>{metrics.p95_ms === null ? '—' : `${(metrics.p95_ms / 1000).toFixed(1)} 秒`}</strong></span></div>
      <p className="settings-muted">使用固定结果或未执行的回合：{metrics.fallbacks}。小样本耗时仅供参考。</p>
    </section>}
  </dialog>;
}
