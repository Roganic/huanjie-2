import { useEffect, useState } from 'react';
import VisualEditor from './VisualEditor';
import { ModalPanel } from './SideSheet';
import { gameError } from '../gameApi';
import './StoryStudio.css';

type Doc = Record<string, unknown>;
type Schema = { $ref?: string; $defs?: Record<string, Schema>; type?: string; properties?: Record<string, Schema>; required?: string[]; additionalProperties?: Schema | boolean; items?: Schema; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; default?: unknown; minimum?: number; maximum?: number; description?: string };
type Issue = { loc?: (string | number)[]; msg: string };
type Pending = { format: 'json' | 'story_graph'; source: string };
type SourceMapping = { source_excerpt: string; references: string[]; note: string };
type Review = { coverage?: SourceMapping[]; outline?: Doc; valid: boolean; issues: Issue[]; warnings?: Issue[]; draft?: Doc | null; module?: Doc; assumptions?: string[]; questions?: string[] };
type Draft = { pending?: Pending | null; id: string; document: Doc; source: string; updated_at: number; review?: Review };
const labels: Record<string, string> = { id:'标识', name:'名称', version:'版本', description:'描述', starting_scene_id:'起始地点', scenes:'地图与场景', characters:'人物', items:'装备与物品', quests:'任务', events:'事件', endings:'结局', supplies:'初始补给', schema_version:'格式版本', exits:'相邻地点', direction:'出口名称', target_scene_id:'目标地点', character_ids:'场景人物', item_ids:'地面物品', interactions:'场景互动', challenges:'行为挑战', safe_rest:'允许安全休息', aliases:'别名', type:'类型', dialogue:'对白', clue:'线索', personality:'性格与动机', knowledge:'人物知识', text:'内容', required_flags:'前置标记', forbidden_flags:'排除标记', set_flags:'产生标记', kind:'类型', giver_id:'委托人', objective:'任务目标', ready_text:'目标达成后的叙事', alternative_flags:'替代路线标记', alternative_objective:'替代路线目标', alternative_ready_text:'替代路线结果', rewards:'奖励', xp_reward:'经验奖励', target_id:'目标标识', action_name:'行动名称', goal_id:'目标标识', approaches:'可选做法', consequences:'可选后果', skill:'技能', ability:'属性', dc:'难度', on_success:'成功事件', on_failure:'失败事件', success_narrative:'成功叙事', failure_narrative:'失败叙事', risk:'风险', stakes:'利害关系', title:'标题', narration:'叙事', effects:'实际效果', category:'事件类别', scope:'影响范围', priority:'优先级', delay:'倒计时', clock:'计时方式', on:'触发方式', completed_quests:'已完成任务', failed_quests:'已失败任务', item_id:'物品标识', quantity:'数量', amount:'数量/幅度', value:'值', hp:'生命', ac:'防御', weapon_id:'武器', abilities:'属性', damage_dice:'伤害骰', attack_ability:'攻击属性', damage_type:'伤害类型', base_ac:'护甲防御', effect_type:'物品效果', effect_dice:'效果骰', retry:'重试规则', retry_delay:'重试间隔', time_cost:'时间消耗', check_kind:'鉴定类型', occupation:'职业', race:'种族', role:'角色定位', alive:'存活', drops:'掉落', starting_quantity:'初始数量' };
const groups = ['scenes', 'characters', 'items', 'quests', 'events', 'endings', 'supplies'];
function resolve(schema: Schema, root: Schema): Schema {
  const ref = schema.$ref ? root.$defs?.[schema.$ref.split('/').at(-1)!] ?? schema : schema;
  return ref.anyOf ? resolve(ref.anyOf.find(v => v.type !== 'null') ?? ref.anyOf[0], root) : ref;
}
function initial(schema: Schema, root: Schema): unknown {
  if (schema.default !== undefined) return structuredClone(schema.default);
  const s = resolve(schema, root);
  if (s.const !== undefined) return s.const;
  if (s.enum) return s.enum[0];
  if (s.type === 'array') return [];
  if (s.type === 'object') return Object.fromEntries((s.required ?? []).map(key => [key, initial(s.properties?.[key] ?? {}, root)]));
  if (s.type === 'integer' || s.type === 'number') return s.minimum ?? 0;
  if (s.type === 'boolean') return false;
  return '';
}
function Field({ label, value, schema, root, onChange }: { label: string; value: unknown; schema: Schema; root: Schema; onChange: (value: unknown) => void }) {
  const s = resolve(schema, root);
  if (s.const !== undefined) return <label className="studio-field">{label}<input aria-label={label} value={String(s.const)} readOnly /></label>;
  if (s.enum) return <label className="studio-field">{label}<select aria-label={label} value={String(value ?? '')} onChange={e => onChange(e.target.value === '' ? undefined : s.enum!.find(v => String(v) === e.target.value))}><option value="">未设置</option>{s.enum.map(v => <option key={String(v)} value={String(v)}>{String(v)}</option>)}</select></label>;
  if (s.type === 'object' && typeof s.additionalProperties === 'object') return <RecordField label={label} value={value} schema={s.additionalProperties} root={root} onChange={onChange} />;
  if (s.type === 'boolean') return <label className="studio-check"><input aria-label={label} type="checkbox" checked={Boolean(value)} onChange={e => onChange(e.target.checked)} />{label}</label>;
  if (s.type === 'object' && s.properties) {
    const obj = (value && typeof value === 'object' ? value : {}) as Doc;
    return <details className="studio-object" open><summary>{label}</summary><div>{Object.entries(s.properties).map(([key, child]) => <Field key={key} label={labels[key] ?? key} value={obj[key]} schema={child} root={root} onChange={v => onChange({ ...obj, [key]: v })} />)}</div></details>;
  }
  if (s.type === 'array') {
    const values = Array.isArray(value) ? value : [];
    return <details className="studio-array"><summary>{label} · {values.length}</summary>{values.map((v, i) => <div className="studio-row" key={i}><Field label={`${label} ${i + 1}`} value={v} schema={s.items ?? { type: 'string' }} root={root} onChange={next => onChange(values.map((old, n) => n === i ? next : old))} /><button aria-label={`删除${label} ${i + 1}`} onClick={() => onChange(values.filter((_, n) => n !== i))}>移除</button></div>)}<button onClick={() => onChange([...values, initial(s.items ?? { type: 'string' }, root)])}>＋ 添加{label}</button></details>;
  }
  if (s.type === 'integer' || s.type === 'number') return <label className="studio-field">{label}<input aria-label={label} type="number" value={value == null ? '' : Number(value)} min={s.minimum} max={s.maximum} onChange={e => onChange(e.target.value === '' ? undefined : Number(e.target.value))} /></label>;
  if (!/描述|叙事|内容|对白|线索|动机|风险|利害|设定/.test(label) && String(value ?? '').length < 100) return <label className="studio-field">{label}<input aria-label={label} value={String(value ?? '')} onChange={e => onChange(e.target.value)} /></label>;
  return <label className="studio-field">{label}<textarea aria-label={label} rows={String(value ?? '').length > 90 ? 4 : 2} value={String(value ?? '')} onChange={e => onChange(e.target.value)} /></label>;
}
function RecordField({ label, value, schema, root, onChange }: { label: string; value: unknown; schema: Schema; root: Schema; onChange: (value: unknown) => void }) {
  const [key, setKey] = useState('');
  const entries = value && typeof value === 'object' && !Array.isArray(value) ? value as Doc : {};
  return <details className="studio-array"><summary>{label} · {Object.keys(entries).length}</summary>
    {Object.entries(entries).map(([id, child]) => <div className="studio-row" key={id}><Field label={labels[id] ?? id} value={child} schema={schema} root={root} onChange={v => onChange({ ...entries, [id]: v })} /><button aria-label={`删除${label} ${id}`} onClick={() => { const next = { ...entries }; delete next[id]; onChange(next); }}>移除</button></div>)}
    <div className="studio-inline"><input aria-label={`${label}新字段`} value={key} onChange={e => setKey(e.target.value)} /><button disabled={!/^[a-zA-Z0-9_-]+$/.test(key) || key in entries} onClick={() => { onChange({ ...entries, [key]: initial(schema, root) }); setKey(''); }}>添加</button></div>
  </details>;
}
const blank = (): Doc => ({ schema_version: 1, id: `story-${crypto.randomUUID().slice(0, 8)}`, version: '1.0.0', name: '未命名冒险', description: '', starting_scene_id: '', scenes: {}, characters: {}, items: {}, quests: {}, events: {}, endings: [] });

export default function StoryStudio({ apiUrl, onClose, onInstalled, onPlay }: { apiUrl: (path: string) => string; onClose: () => void; onInstalled: () => void; onPlay: (id: string) => Promise<void> }) {
  const [document, setDocument] = useState<Doc>(blank);
  const [source, setSource] = useState(() => localStorage.getItem('huanjie-story-source') ?? '');
  const [schema, setSchema] = useState<Schema>({});
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [library, setLibrary] = useState<{id: string; name: string}[]>([]);
  const [notes, setNotes] = useState<{assumptions?: string[]; questions?: string[]; coverage?: SourceMapping[]}>({});
  const [draftId, setDraftId] = useState<string>();
  const [review, setReview] = useState<Review>();
  const [tab, setTab] = useState('story');
  const [selected, setSelected] = useState('');
  const [newId, setNewId] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState('');
  const [raw, setRaw] = useState('');
  const [pending, setPending] = useState<Pending>();
  const [dirty, setDirty] = useState(false);
  useEffect(() => { localStorage.setItem('huanjie-story-source', source); }, [source]);
  useEffect(() => {
    let live = true;
    Promise.all([fetch(apiUrl('/modules/schema')).then(r => r.json()), fetch(apiUrl('/modules/drafts')).then(r => r.json()), fetch(apiUrl('/modules')).then(r => r.json())])
      .then(([s, d, m]) => { if (live) { setSchema(s); setDrafts(d.drafts ?? []); setLibrary(m.modules ?? []); } }).catch(() => { if (live) setNotice('创作服务连接失败，请重试打开。'); });
    return () => { live = false; };
  }, [apiUrl]);
  const change = (d: Doc) => { setDocument(d); setReview(undefined); setDirty(true); };
  const request = async (path: string, body: unknown) => {
    const r = await fetch(apiUrl(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await gameError(r));
    return r.json();
  };
  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label); setNotice('');
    try { await action(); } catch (e) { setNotice(e instanceof Error ? e.message : '操作失败，草稿仍保留。'); } finally { setBusy(''); }
  };
  const inspect = async () => { if (pending) throw new Error('请先应用文件中的修改，或保存草稿稍后继续。'); const result = await request('/modules/validate', document); setReview({ ...result, ...notes }); return result as Review; };
  const acceptTranslation = (result: Review) => {
    setReview(result); setNotes({ assumptions: result.assumptions, questions: result.questions, coverage: result.coverage });
    if (result.draft) { setDirty(true); setDocument(result.draft); setPending(undefined); setDraftId(undefined); setTab('overview'); }
    else {
      if (result.outline) { const value = JSON.stringify(result.outline, null, 2); setPending({ format: 'story_graph', source: value }); setRaw(value); setDirty(true); setDraftId(undefined); setTab('json'); }
      setNotice('故事未能完成解析。原稿和已生成的结构会随草稿保存。');
    }
  };
  const translate = () => run('正在将故事整理成模组…', async () => acceptTranslation(await request('/modules/parse', { format: 'text', source })));
  const repair = () => run('正在修复故事结构…', async () => acceptTranslation(await request('/modules/repair', { source, outline: pending?.source, assumptions: notes.assumptions, questions: notes.questions })));
  const persistDraft = async () => {
    const saved: Draft = await request('/modules/drafts', { id: draftId, source, document, pending, ...notes });
    setDraftId(saved.id); setDrafts([saved, ...drafts.filter(d => d.id !== saved.id)]); setNotice('草稿已保存。'); setDirty(false);
  };
  const loadDraft = (d: Draft) => run('载入草稿…', async () => {
    if (dirty) await persistDraft();
    setDocument(d.document); setSource(d.source); setPending(d.pending ?? undefined); setRaw(d.pending?.source ?? '');
    setDraftId(d.id); setDirty(false); setReview(d.review); setNotes({ assumptions: d.review?.assumptions, questions: d.review?.questions, coverage: d.review?.coverage });
    setSelected(''); setTab(d.pending ? 'json' : 'overview'); setNotice('');
  });
  const save = () => run('保存草稿…', persistDraft);
  const exit = () => { if (busy) return; if (!dirty) { onClose(); return; } void run('保存草稿…', async () => { await persistDraft(); onClose(); }); };
  const install = (play: boolean) => run(play ? '准备试玩…' : '加入模组库…', async () => {
    const result = await inspect();
    if (!result.valid) { setNotice('请先修复下方问题。'); return; }
    await request('/modules/import', result.module); onInstalled();
    if (play) { await onPlay(String(document.id)); onClose(); } else setNotice('已加入模组库。修改后请使用新标识导入新版本。');
  });
  const download = () => run('导出…', async () => {
    const result = await inspect();
    if (!result.valid) { setNotice('请修复格式问题后导出模组；未完成内容可保存为草稿。'); return; }
    const url = URL.createObjectURL(new Blob([JSON.stringify(result.module, null, 2)], { type: 'application/json' }));
    const a = window.document.createElement('a'); a.href = url; a.download = `${String(document.id).replace(/[^a-zA-Z0-9_-]/g, '') || 'module'}.json`; a.click(); URL.revokeObjectURL(url);
  });
  const tabChange = (t: string) => { setTab(t); setSelected(''); if (t === 'json') setRaw(pending?.source ?? JSON.stringify(document, null, 2)); };
  const groupSchema = schema.properties?.[tab] ?? {};
  const group = (document[tab] ?? {}) as Doc;
  const recordSchema = typeof groupSchema.additionalProperties === 'object' ? groupSchema.additionalProperties : {};
  return <div className="studio-overlay"><ModalPanel className="story-studio" title="模组创作工坊" onClose={exit}>
    <header className="studio-header"><div><span className="studio-eyebrow">幻界 · 创作工坊</span><h2>{String(document.name || '未命名冒险')}</h2></div><button disabled={Boolean(busy)} onClick={exit}>{dirty ? '保存并返回' : '返回游戏'}</button></header>
    <div className="studio-body"><nav aria-label="创作内容">{[['story', '故事原稿'], ['overview', '冒险概览'], ['visuals', '外观与素材'], ...groups.map(g => [g, labels[g]]), ['json', 'JSON 文件']].map(([id, name]) => <button key={id} disabled={Boolean(busy)} aria-current={tab === id ? 'page' : undefined} onClick={() => tabChange(id)}>{name}</button>)}
      <label className="studio-drafts">已保存草稿<select disabled={Boolean(busy)} value={draftId ?? ''} onChange={e => { const d = drafts.find(v => v.id === e.target.value); if (d) void loadDraft(d); }}><option value="">选择草稿</option>{drafts.map(d => <option key={d.id} value={d.id}>{String(d.document.name ?? '未命名冒险')}</option>)}</select></label>
      <label className="studio-drafts">以现有模组为起点<select value="" disabled={Boolean(busy)} onChange={e => { const id = e.target.value; if (id) void run('载入模组副本…', async () => { if (dirty) await persistDraft(); const r = await fetch(apiUrl(`/modules/${encodeURIComponent(id)}`)); if (!r.ok) throw new Error(await gameError(r)); const pack = await r.json(); change({ ...pack, id: `story-${crypto.randomUUID().slice(0, 8)}`, name: `${pack.name} · 改编` }); setDraftId(undefined); setPending(undefined); setSource(''); setNotes({}); setSelected(''); setTab('overview'); }); }}><option value="">选择模组创建副本</option>{library.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
    </nav><main className="studio-main"><fieldset disabled={Boolean(busy) || Boolean(pending) && tab !== 'json' && tab !== 'story'}>
      {tab === 'story' && <section className="studio-source"><h3>把故事写下来</h3><p>写出人物、地点、玩家目标和可能的结局。生成后可以逐项修改。</p><label className="studio-field">读取故事文件<input type="file" aria-label="读取故事文件" accept=".txt,.md,text/plain,text/markdown" onChange={e => { const file = e.target.files?.[0]; if (file) void run('读取故事…', async () => { if (file.size > 240000) throw new Error('故事文件过大，请按章节拆分。'); const text = await file.text(); if (text.length > 60000) throw new Error('单篇原稿请控制在 60,000 字以内。'); setSource(text); setDirty(true); }); }} /></label><textarea aria-label="故事原稿" placeholder="雨停之前，小镇必须找回灯塔的透镜……" value={source} maxLength={60000} onChange={e => { setSource(e.target.value); setDirty(true); }} /><div className="studio-inline"><span>{source.length.toLocaleString()} / 60,000 字</span><button className="studio-primary" disabled={source.trim().length < 20} onClick={() => void translate()}>生成模组草稿</button></div></section>}
      {tab === 'visuals' && <VisualEditor document={document} onChange={change} apiUrl={apiUrl} onBusyChange={value => setBusy(value ? "正在处理外观…" : "")} />}
      {tab === 'overview' && <section><h3>冒险概览</h3>{['id','version','name','description','starting_scene_id'].map(key => <Field key={key} label={labels[key]} value={document[key]} schema={schema.properties?.[key] ?? { type: 'string' }} root={schema} onChange={value => change({ ...document, [key]: value })} />)}<div className="studio-map">{Object.entries((document.scenes ?? {}) as Record<string, Doc>).map(([key,s]) => <article key={key}><strong>{String(s.name ?? key)}</strong><span>{key === document.starting_scene_id ? '起点' : key}</span><p>{((s.exits ?? []) as Doc[]).map(e => `→ ${String(e.target_scene_id)}`).join('　') || '无出口'}</p></article>)}</div></section>}
      {groups.includes(tab) && !['endings','supplies'].includes(tab) && <section><h3>{labels[tab]}</h3><div className="studio-inline"><select aria-label={`选择${labels[tab]}`} value={selected} onChange={e => setSelected(e.target.value)}><option value="">选择条目</option>{Object.entries(group).map(([key, v]) => <option key={key} value={key}>{String((v as Doc)?.name ?? (v as Doc)?.title ?? key)} · {key}</option>)}</select><input aria-label="新条目标识" placeholder="新条目标识，如 harbor" value={newId} onChange={e => setNewId(e.target.value)} /><button disabled={!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(newId) || newId in group} onClick={() => { change({ ...document, [tab]: { ...group, [newId]: { ...(initial(recordSchema, schema) as Doc), id: newId, ...(resolve(recordSchema, schema).properties?.name ? { name: newId } : {}) } } }); setSelected(newId); setNewId(''); }}>添加</button></div>
        {selected && group[selected] != null && <><Field label={labels[tab]} value={group[selected]} schema={recordSchema} root={schema} onChange={value => change({ ...document, [tab]: { ...group, [selected]: value } })} /><button onClick={() => { const next = { ...group }; delete next[selected]; change({ ...document, [tab]: next }); setSelected(''); }}>删除当前条目</button></>}
      </section>}
      {['endings','supplies'].includes(tab) && <Field label={labels[tab]} value={document[tab]} schema={groupSchema} root={schema} onChange={value => change({ ...document, [tab]: value })} />}
      {tab === 'json' && <section><h3>{pending?.format === 'story_graph' ? '修复故事结构' : '导入或修改模组文件'}</h3><input type="file" aria-label="读取 JSON 文件" accept=".json,application/json" onChange={e => { const file = e.target.files?.[0]; if (file) void run('读取文件…', async () => { if (file.size > 2_000_000) throw new Error('文件请小于 2 MB。'); const text = await file.text(); setRaw(text); setPending({ format: 'json', source: text }); setDirty(true); }); }} /><textarea wrap="off" className="studio-code" aria-label="模组 JSON" value={raw} onChange={e => { setRaw(e.target.value); setPending({ format: pending?.format ?? 'json', source: e.target.value }); setDirty(true); }} /><button onClick={() => void run('检查文件…', async () => { const r = await request('/modules/parse', { format: pending?.format ?? 'json', source: raw }); setReview({ ...r, ...notes }); if (r.draft) { setDirty(true); setDocument(r.draft); setPending(undefined); setRaw(JSON.stringify(r.draft, null, 2)); setDraftId(undefined); setNotice('已载入，继续校验或编辑。'); } })}>应用到草稿</button>{pending?.format === 'story_graph' && <button disabled={source.trim().length < 20} onClick={() => void repair()}>让 AI 修复结构</button>}</section>}
    </fieldset>
    {review && <section className="studio-review" aria-label="草稿审阅"><h3>{review.valid ? '格式校验通过' : '需要修改'}</h3>{[...review.issues, ...(review.warnings ?? [])].map((issue, i) => <p key={i}>{issue.loc?.join(' → ')}：{issue.msg}</p>)}{review.coverage?.length ? <details open><summary>原稿与机制对应 · {review.coverage.length} 项</summary><p>以下为生成时的审查记录；编辑后请重新对照原稿确认。</p>{review.coverage.map((mapping, i) => <div className="studio-source-mapping" key={i}><blockquote>{mapping.source_excerpt}</blockquote><p>{mapping.note}</p><small>{mapping.references.length ? mapping.references.join(' · ') : '需要作者补充'}</small></div>)}</details> : null}{review.assumptions?.length ? <details open><summary>补全的设定</summary>{review.assumptions.map((s,i) => <p key={i}>{s}</p>)}</details> : null}{review.questions?.length ? <details open><summary>待你确定</summary>{review.questions.map((s,i) => <p key={i}>{s}</p>)}</details> : null}</section>}
    </main></div><footer className="studio-footer"><span role="status">{busy || notice || (pending ? '文件修改尚未应用，已编辑内容可保存后继续。' : '草稿与正在进行的冒险分别保存。')}</span><div><button disabled={Boolean(busy)} onClick={() => void save()}>保存草稿</button><button disabled={Boolean(busy)} onClick={() => void run('校验…', async () => { await inspect(); })}>校验</button><button disabled={Boolean(busy)} onClick={() => void download()}>导出</button><button disabled={Boolean(busy)} onClick={() => void install(false)}>加入模组库</button><button className="studio-primary" disabled={Boolean(busy)} onClick={() => void install(true)}>试玩新冒险</button></div></footer>
  </ModalPanel></div>;
}
