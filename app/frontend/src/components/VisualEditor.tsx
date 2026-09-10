import { useState } from 'react';
import { categoryNames, prepareUpload, resolveArt, sceneCategory, itemCategory, themeOf, themes, type ArtCategory, type ArtSlot, type ModuleVisuals, type ThemePack } from '../game/visuals';
import './VisualEditor.css';

type Doc = Record<string, unknown>;
const sources = { default: '默认素材', upload: '已上传', generated: '生成素材' };
export default function VisualEditor({ document, onChange, apiUrl, onBusyChange }: { document: Doc; onChange: (value: Doc) => void; apiUrl: (path: string) => string; onBusyChange: (busy: boolean) => void }) {
  const visuals = (document.visuals || {}) as ModuleVisuals, theme = themeOf(visuals);
  const [group, setGroup] = useState('scenes'), [selected, setSelected] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const entries = (document[group === 'map' ? 'scenes' : group] || {}) as Record<string, Doc>;
  const ids = ['player', 'cover'].includes(group) ? [group] : group === 'defaults' ? Object.keys(categoryNames) : Object.keys(entries);
  const id = ids.includes(selected) ? selected : ids[0] || '';
  const slots: Record<string, ArtSlot> | undefined = group === 'defaults' ? theme.defaults : visuals[group as 'scenes' | 'characters' | 'items' | 'map'];
  const slot: ArtSlot = (group === 'player' || group === 'cover' ? visuals[group] : slots?.[id]) || {};
  const fallback: ArtCategory = group === 'defaults' ? id as ArtCategory : group === 'player' ? 'traveller' : group === 'characters' ? 'portrait' : group === 'map' ? 'item' : group === 'items' ? itemCategory(String(entries[id]?.type || '')) : sceneCategory(String(entries[id]?.name || ''));
  const art = resolveArt(visuals, group === 'defaults' ? undefined : slot, fallback);
  const update = (next: ModuleVisuals) => { onChange({ ...document, visuals: next }); setNotice(''); };
  const changeSlot = (next: ArtSlot, base = visuals) => {
    if (group === 'defaults') return { ...base, theme: { ...themeOf(base), defaults: { ...themeOf(base).defaults, [id]: next } } };
    if (group === 'player' || group === 'cover') return { ...base, [group]: next };
    return { ...base, [group]: { ...base[group as 'scenes' | 'characters' | 'items' | 'map'], [id]: next } };
  };
  const run = async (fn: () => Promise<void>) => { setBusy(true); onBusyChange(true); setNotice(''); try { await fn(); } catch (e) { setNotice(e instanceof Error ? e.message : '未能完成操作'); } finally { setBusy(false); onBusyChange(false); } };
  const checkTheme = async (input: unknown): Promise<ThemePack> => {
    const r = await fetch(apiUrl('/themes/validate'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    if (!r.ok) throw new Error('主题包格式无效，请检查素材、分类和引用。');
    return r.json();
  };
  const total = [...Object.values(visuals.assets || {}), ...Object.values(theme.assets || {})].reduce((sum, a) => sum + a.data.length, 0);
  return <section className="visual-editor"><header><span className="studio-eyebrow">外观与素材</span><h3>让你的世界有自己的模样</h3><p>默认外观即可游玩。替换的图片随模组保存，也可以把主题单独分享。</p></header>
    <fieldset disabled={busy}><div className="visual-presets">{themes.map(p => <button key={p.id} className={`visual-preset ${p.preset}`} aria-pressed={theme.preset === p.preset} onClick={() => update({ ...visuals, theme: { ...p, assets: theme.assets, defaults: theme.defaults } })}><span>◈</span><strong>{p.name}</strong><small>{p.illustrated ? '西方奇幻 · 手绘场景' : '题材中立 · 通用视觉'}</small></button>)}</div>
      <div className="visual-theme-controls"><label>主题名称<input value={theme.name} maxLength={80} onChange={e => update({ ...visuals, theme: { ...theme, name: e.target.value } })} /></label><label>标题字体<select value={theme.heading_font || 'serif'} onChange={e => update({ ...visuals, theme: { ...theme, heading_font: e.target.value as 'serif' | 'sans' } })}><option value="serif">书卷衬线</option><option value="sans">简洁无衬线</option></select></label><label>装饰<select value={theme.frame || 'ornate'} onChange={e => update({ ...visuals, theme: { ...theme, frame: e.target.value as 'ornate' | 'simple' } })}><option value="ornate">古典纹饰</option><option value="simple">简洁边框</option></select></label></div>
      <div className="visual-workspace"><div className="visual-controls"><label>替换范围<select value={group} onChange={e => { setGroup(e.target.value); setSelected(''); }}>{[['scenes','场景画面'],['map','地图路线图标'],['characters','人物肖像'],['items','装备与物品'],['player','玩家形象'],['cover','模组封面'],['defaults','主题通用素材']].map(([v,n]) => <option key={v} value={v}>{n}</option>)}</select></label>
        {ids.length > 0 ? <><label>选择条目<select value={id} onChange={e => setSelected(e.target.value)}>{ids.map(key => <option key={key} value={key}>{group === 'defaults' ? categoryNames[key as ArtCategory] : group === 'player' ? '玩家形象' : group === 'cover' ? '模组封面' : String(entries[key]?.name || key)}</option>)}</select></label>
          <label>默认表现<select value={slot.fallback || fallback} onChange={e => update(changeSlot({ ...slot, builtin: null, fallback: e.target.value as ArtCategory }))}>{Object.entries(categoryNames).map(([v,n]) => <option key={v} value={v}>{n}</option>)}</select></label>
          <label className="visual-upload">上传替换图片<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return; void run(async () => {
            const asset = await prepareUpload(file), key = `art-${crypto.randomUUID().slice(0, 8)}`;
            if (total + asset.data.length > 768000) throw new Error('便携模组的图片总量已达上限，请移除不用的素材后继续。');
            const base = group === 'defaults' ? { ...visuals, theme: { ...theme, assets: { ...theme.assets, [key]: asset } } } : { ...visuals, assets: { ...visuals.assets, [key]: asset } };
            update(changeSlot({ ...slot, asset_id: key }, base)); setNotice('图片已加入草稿，保存后可跨设备复用。');
          }); }} /><small>本地压缩后存入模组，无生成费用</small></label>
          <label>已有素材<select value={slot.asset_id || ''} onChange={e => update(changeSlot({ ...slot, asset_id: e.target.value || null }))}><option value="">使用默认素材</option>{Object.entries((group === 'defaults' ? theme.assets : visuals.assets) || {}).map(([key,a]) => <option key={key} value={key}>{a.name}</option>)}</select></label>
          {(slot.asset_id || slot.builtin) && <><label>画面焦点 · 水平<input type="range" min="0" max="100" value={slot.focal_x ?? 50} onChange={e => update(changeSlot({ ...slot, focal_x: +e.target.value }))} /></label><label>画面焦点 · 垂直<input type="range" min="0" max="100" value={slot.focal_y ?? 50} onChange={e => update(changeSlot({ ...slot, focal_y: +e.target.value }))} /></label></>}
        </> : <p>先在对应分类添加条目，再为它选择外观。</p>}
      </div><div className="visual-preview" data-theme={theme.preset} data-font={theme.heading_font || 'serif'} data-frame={theme.frame || 'ornate'}><div className={`visual-preview-art ${['characters','player','items'].includes(group) ? 'portrait' : ''}`}><img key={art.src} src={art.src} alt="当前素材预览" style={{ objectPosition: art.position }} onError={e => { e.currentTarget.onerror = null; if (e.currentTarget.src !== art.fallback) e.currentTarget.src = art.fallback; }} /><span>{sources[art.source as keyof typeof sources]}</span></div><div className="visual-preview-copy"><small>冒险之书 · 外观预览</small><h4>{String(entries[id]?.name || document.name || '未命名冒险')}</h4><p>{String(entries[id]?.description || '每一段旅程，都由你的选择展开。')}</p><div><span>◈ 探索</span><span>✧ 交谈</span></div></div></div></div>
      <details className="visual-library"><summary>素材库 · {Math.round(total / 1024)} / 750 KB</summary><p>移除素材会让对应位置恢复默认外观。已导出的模组与旧冒险不受影响。</p>{(['module','theme'] as const).map(scope => Object.entries((scope === 'module' ? visuals.assets : theme.assets) || {}).map(([key,a]) => <div key={`${scope}-${key}`}><span>{scope === 'theme' ? '主题' : '模组'} · {a.name}</span><button onClick={() => {
          const clean = (s?: ArtSlot | null): ArtSlot => s?.asset_id === key ? { ...s, asset_id: null } : s || {};
          const assets = { ...(scope === 'module' ? visuals.assets : theme.assets) }; delete assets[key];
          if (scope === 'theme') update({ ...visuals, theme: { ...theme, assets, defaults: Object.fromEntries(Object.entries(theme.defaults || {}).map(([k,s]) => [k, clean(s)])) } });
          else update({ ...visuals, assets, map: Object.fromEntries(Object.entries(visuals.map || {}).map(([k,s]) => [k, clean(s)])), scenes: Object.fromEntries(Object.entries(visuals.scenes || {}).map(([k,s]) => [k, clean(s)])), characters: Object.fromEntries(Object.entries(visuals.characters || {}).map(([k,s]) => [k, clean(s)])), items: Object.fromEntries(Object.entries(visuals.items || {}).map(([k,s]) => [k, clean(s)])), player: clean(visuals.player), cover: clean(visuals.cover) });
        }}>移除</button></div>))}</details>
      <div className="visual-sharing"><button onClick={() => void run(async () => { const checked = await checkTheme(theme); const url = URL.createObjectURL(new Blob([JSON.stringify(checked, null, 2)], { type: 'application/json' })); const a = window.document.createElement('a'); a.href = url; a.download = `${checked.id}.theme.json`; a.click(); URL.revokeObjectURL(url); })}>导出独立主题包</button><label>导入主题包<input type="file" accept=".json,application/json" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void run(async () => { if (file.size > 1_000_000) throw new Error('主题包请小于 1 MB。'); const checked = await checkTheme(JSON.parse(await file.text())); const size = Object.values(visuals.assets || {}).reduce((s,a) => s + a.data.length, 0) + Object.values(checked.assets || {}).reduce((s,a) => s + a.data.length, 0); if (size > 768000) throw new Error('主题与当前模组素材合计超过上限。'); update({ ...visuals, theme: checked }); }); }} /></label><button disabled title="服务与价格确认后开放；按张计费">AI 生图 · 尚未开放</button></div>
    </fieldset><p role="status">{busy ? '正在处理图片…' : notice}</p>
  </section>;
}
