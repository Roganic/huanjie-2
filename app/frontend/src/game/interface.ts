import type { AdventureController, AdventureView } from './controller';
import type { AbilityScores, CharacterClass, Challenge, ChallengeChoice, NarrativeHistoryEntry } from './types';
import { applyTheme, artImage, itemCategory } from './visuals';

export const abilityNames: Record<string, string> = { str: '力量', dex: '敏捷', con: '体质', int: '智力', wis: '感知', cha: '魅力' };
export const classNames: Record<string, string> = { warrior: '战士', mage: '法师', rogue: '盗贼' };
const classAbilities: Record<CharacterClass, AbilityScores> = {
  warrior: { str: 15, dex: 13, con: 14, int: 8, wis: 12, cha: 10 },
  mage: { str: 8, dex: 13, con: 12, int: 15, wis: 14, cha: 10 },
  rogue: { str: 10, dex: 15, con: 13, int: 12, wis: 14, cha: 8 },
};
const el = <K extends keyof HTMLElementTagNameMap>(tag: K, text = '', cls = '') => {
  const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;
};
const button = (text: string, fn: () => void, cls = '') => {
  const b = el('button', text, cls); b.type = 'button'; b.onclick = fn; return b;
};
const paragraphs = (parent: HTMLElement, text?: string) => {
  text?.split('\n').filter(line => line.trim()).forEach(line => parent.append(el('p', line)));
};
type Presentation = 'text' | 'illustrated';
const presentationKey = 'huanjie.presentation';
function savedPresentation(): Presentation {
  try { return localStorage.getItem(presentationKey) === 'text' ? 'text' : 'illustrated'; }
  catch { return 'illustrated'; }
}

/** Semantic text/input layer owned and destroyed by the Phaser adventure scene. */
export class AdventureInterface {
  readonly root = el('main', '', 'adventure-engine');
  readonly stage = el('div', '', 'adventure-stage');
  readonly scenery = el('div', '', 'adventure-scenery');
  private sidebar = el('aside', '', 'adventure-character');
  private landscape = el('section', '', 'adventure-landscape');
  private scenicCaption = el('div', '', 'adventure-scenic-caption');
  private sceneSummary = el('p', '', 'adventure-text-scene');
  private presentation: Presentation = savedPresentation();
  private viewSwitch = el('div', '', 'adventure-view-switch');
  private scrollFrame = 0;
  onPresentationChange = () => {};
  get isIllustrated() { return this.presentation === 'illustrated'; }
  private cast = el('div', '', 'adventure-cast');
  private sheetKey = '';
  private heading = el('div', '', 'adventure-heading');
  private status = el('div', '', 'adventure-status');
  private narrative = el('div', '', 'adventure-narrative');
  private actions = el('div', '', 'adventure-actions');
  private statusLine = el('div', '', 'adventure-feedback');
  private composer = el('form', '', 'adventure-composer');
  private input = el('textarea');
  private sendButton: HTMLButtonElement;
  private cue = el('div', '', 'adventure-cue');
  private selection = el('div', '', 'adventure-selection');
  private tools = el('div', '', 'adventure-map-tools');
  private creation = el('div', '', 'adventure-creation');
  private story = el('section', '', 'adventure-story');
  private world = el('section', '', 'adventure-world');
  private historyKey = '';
  private actionsKey = '';
  private creationSession = '';
  private selected = '';
  private target = '';
  onTarget = () => {};
  get selectedTarget() { return this.target; }
  private continuedEnding = '';
  private worldMode: 'docked' | 'floating' | 'hidden' = matchMedia('(max-width: 760px)').matches ? 'hidden' : 'docked';
  private dragListeners = new AbortController();
  private floatSize?: { width: number; height: number };
  private mapObserver: ResizeObserver;
  private dialog: HTMLDialogElement | null = null;
  private mutationButtons = new Map<HTMLButtonElement, boolean>();
  private controller: AdventureController;
  private select: (id: string) => void;
  constructor(controller: AdventureController, select: (id: string) => void,
    movement: { locate: () => void; zoom: (factor: number) => void; rotate: () => void; motion: () => void }) {
    this.controller = controller; this.select = select;
    this.mapObserver = new ResizeObserver(() => {
      if (this.worldMode === 'floating') { const rect = this.world.getBoundingClientRect(); this.mapPosition(rect.left, rect.top); }
    });
    this.mapObserver.observe(this.world);
    const header = el('header', '', 'adventure-header');
    const brand = el('div', '', 'adventure-brand'); brand.append(el('strong', '幻界'), el('span', '冒险之书'));
    const nav = el('nav'); nav.setAttribute('aria-label', '冒险工具');
    nav.append(button('地图', () => this.mapMode(this.worldMode === 'hidden' ? 'docked' : 'hidden')), button('角色', () => this.character()), button('背包', () => void controller.openPanel('inventory')),
      button('手记', () => this.journal()), button('模组', () => void controller.openPanel('modules')),
      button('创作', () => void controller.openPanel('studio')), button('菜单', () => this.menu()));
    this.viewSwitch.setAttribute('role', 'group'); this.viewSwitch.setAttribute('aria-label', '游玩视图');
    this.viewSwitch.append(button('文字版', () => this.changePresentation('text')), button('美术版', () => this.changePresentation('illustrated')));
    header.append(brand, this.status, this.viewSwitch, nav);
    this.renderPresentation();
    this.world.setAttribute('aria-label', '冒险地图');
    this.stage.setAttribute('role', 'img'); this.stage.setAttribute('aria-label', '地点路网；可用地图下方地点按钮选择路线');
    this.tools.append(el('span', '区域地图', 'adventure-atlas-title'), button('−', () => movement.zoom(.8)), button('+', () => movement.zoom(1.25)),
      button('定位', movement.locate), button('旋转指针', movement.rotate), button('动效', movement.motion));
    this.tools.children[1].setAttribute('aria-label', '缩小地图'); this.tools.children[2].setAttribute('aria-label', '放大地图');
    this.tools.append(button('浮窗 / 归位', () => this.mapMode(this.worldMode === 'floating' ? 'docked' : 'floating')), button('关闭', () => this.mapMode('hidden')));
    const handle = button('移动地图', () => {}, 'adventure-map-handle');
    handle.title = '拖动移动；也可用方向键移动';
    handle.onpointerdown = event => {
      if (this.worldMode !== 'floating') return;
      event.preventDefault(); handle.setPointerCapture(event.pointerId);
      const rect = this.world.getBoundingClientRect(), x = event.clientX, y = event.clientY;
      handle.onpointermove = move => this.mapPosition(rect.left + move.clientX - x, rect.top + move.clientY - y);
      handle.onpointerup = () => { handle.onpointermove = null; };
    };
    handle.onkeydown = event => {
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
      event.preventDefault(); const rect = this.world.getBoundingClientRect();
      this.mapPosition(rect.left + (event.key === 'ArrowLeft' ? -20 : event.key === 'ArrowRight' ? 20 : 0), rect.top + (event.key === 'ArrowUp' ? -20 : event.key === 'ArrowDown' ? 20 : 0));
    };
    this.tools.append(handle);
    window.addEventListener('resize', () => { if (this.worldMode === 'floating') { const rect = this.world.getBoundingClientRect(); this.mapPosition(rect.left, rect.top); } }, { signal: this.dragListeners.signal });
    this.world.append(this.stage, this.tools, this.selection);
    this.narrative.setAttribute('aria-label', '冒险叙事'); this.narrative.tabIndex = 0;
    this.cue.setAttribute('role', 'status'); this.statusLine.setAttribute('role', 'status');
    this.input.rows = 2; this.input.maxLength = 2000; this.input.placeholder = '说点什么，或描述你的行动…'; this.input.setAttribute('aria-label', '你的行动');
    this.sendButton = button('行动 →', () => void this.send(), 'adventure-primary');
    this.input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); void this.send(); }
    });
    this.composer.onsubmit = e => { e.preventDefault(); void this.send(); };
    this.composer.append(this.input, this.sendButton);
    this.story.append(this.heading, this.narrative, this.cue, this.actions, this.statusLine, this.composer);
    const illustration = el('div', '', 'adventure-illustration');
    this.scenery.setAttribute('role', 'img'); this.scenery.setAttribute('aria-label', '当前场景画面');
    this.cast.setAttribute('aria-label', '此地人物');
    illustration.append(this.scenery, this.scenicCaption, this.sceneSummary, this.cast);
    this.landscape.append(illustration, this.world);
    const body = el('div', '', 'adventure-body'); body.append(this.sidebar, this.landscape, this.story, this.creation);
    this.root.append(header, body);
  }
  private renderPresentation() {
    this.root.dataset.presentation = this.presentation;
    Array.from(this.viewSwitch.children).forEach((b, i) => b.setAttribute('aria-pressed', String(i === (this.isIllustrated ? 1 : 0))));
  }
  private changePresentation(presentation: Presentation) {
    if (presentation === this.presentation) return;
    const range = this.narrative.scrollHeight - this.narrative.clientHeight;
    const progress = range > 0 ? this.narrative.scrollTop / range : 1;
    this.presentation = presentation;
    try { localStorage.setItem(presentationKey, presentation); } catch { /* The current view still works when storage is unavailable. */ }
    this.renderPresentation();
    this.render(this.controller.view);
    this.onPresentationChange();
    cancelAnimationFrame(this.scrollFrame);
    this.scrollFrame = requestAnimationFrame(() => {
      this.narrative.scrollTop = progress * (this.narrative.scrollHeight - this.narrative.clientHeight);
    });
  }
  private action(text: string, fn: () => void, blocked = false, cls = '') {
    const b = button(text, fn, cls); this.mutationButtons.set(b, blocked);
    b.disabled = blocked || this.controller.locked; return b;
  }
  private async send() {
    const intent = this.input.value.trim();
    if (!intent || this.controller.locked) return;
    const original = this.input.value;
    const ok = await this.controller.command('/action', { intent, actor: this.controller.view.state?.actor?.name, approach: '' }, '正在准备回应…');
    if (ok && this.input.value === original) this.input.value = '';
  }
  render(view: AdventureView) {
    const { state, guide, combat } = view;
    applyTheme(this.root, view.visuals);
    this.renderSheet(view);
    this.root.inert = !!view.panel;
    const creating = state?.phase === 'character_creation';
    this.root.dataset.world = creating || combat ? 'docked' : this.worldMode;
    this.stage.setAttribute('aria-label', combat ? '战斗先攻队列；可用敌人按钮选择目标' : '地点路网；可用地图下方地点按钮选择路线');
    this.world.setAttribute('aria-label', combat ? '战斗先攻' : '冒险地图');
    this.root.dataset.mode = creating ? 'creation' : combat ? 'combat' : 'exploration';
    this.creation.hidden = !creating; this.story.hidden = !!creating;
    this.status.replaceChildren();
    if (state?.actor) {
      const a = state.actor;
      this.status.append(el('span', `${a.name} · ${classNames[a.character_class || ''] || '冒险者'} ${a.level || 1}`));
      const hp = el('meter'); hp.min = 0; hp.max = a.hp_max; hp.value = Math.max(0, a.hp); hp.setAttribute('aria-label', `生命 ${a.hp} / ${a.hp_max}`);
      this.status.append(hp, el('span', `${a.hp} / ${a.hp_max}`));
    }
    if (state && creating && this.creationSession !== state.session_id) { this.creationSession = state.session_id; this.createForm(); }
    this.heading.replaceChildren();
    if (state) {
      this.heading.append(el('span', combat ? (combat.status === 'active' ? `遭遇 · 第 ${combat.round_number} 轮` : '遭遇结束') : `探索 · 时间 ${state.scene.time ?? 0}`, 'adventure-eyebrow'),
        el('h1', combat ? '交锋时刻' : '旅途手记'));
      const currentActor = combat?.participants.find(p => p.id === combat.current_actor_id);
      const objective = combat?.status === 'active' ? `${currentActor?.is_player ? '你的回合' : `${currentActor?.name || '敌人'}的回合`} · 剩余 ${combat.actions_remaining ?? 0} 次行动` : guide?.objective;
      if (objective) this.heading.append(el('p', objective, 'adventure-objective'));
    }
    const historyKey = JSON.stringify([state?.session_id, state?.scene.id, state?.narrative_history, combat?.log]);
    if (this.historyKey !== historyKey) {
      this.historyKey = historyKey;
      const atBottom = this.narrative.scrollHeight - this.narrative.scrollTop - this.narrative.clientHeight < 90;
      this.narrative.replaceChildren();
      if (state) {
        const scene = el('details', '', 'adventure-scene-description');
        scene.append(el('summary', '此地景象')); paragraphs(scene, state.scene.description);
        scene.open = !state.narrative_history.length; this.narrative.append(scene);
        for (const entry of state.narrative_history.slice(-30)) this.entry(entry);
        if (combat?.log.length) {
          const log = el('article', '', 'adventure-combat-log'); log.append(el('h3', '战况'));
          for (const line of combat.log.slice(-8)) paragraphs(log, line.narrative);
          this.narrative.append(log);
        }
      }
      if (atBottom || combat) this.narrative.scrollTop = this.narrative.scrollHeight;
    }
    this.cue.replaceChildren();
    const urgent = view.events?.pending.filter(e => (e.has_consequences || ['urgent', 'critical'].includes(e.priority || '')) && !e.waiting_for_conditions && !e.waiting_for_scene && e.remaining <= 2);
    if (urgent?.length) this.cue.append(el('span', urgent.map(e => `${e.title} · ${e.remaining > 0 ? `${e.remaining} ${e.clock === 'combat' ? '轮' : '格时间'}后` : '即将发生'}`).join(' / ')));
    const actionKey = JSON.stringify([state?.session_id, state?.scene.id, state?.play_status, state?.journey?.ending, guide, combat, this.target, this.continuedEnding]);
    if (actionKey !== this.actionsKey) { this.actionsKey = actionKey; this.renderActions(view); }
    this.statusLine.replaceChildren();
    const statusText = view.busy || (this.controller.pending && !view.recovery ? '正在结算…' : '') || view.error || view.notice;
    if (statusText) this.statusLine.append(el('span', statusText));
    if (view.recovery && !view.busy) this.statusLine.append(button('恢复上次结果', () => void this.controller.recover()));
    else if (view.error && !view.busy) this.statusLine.append(button('重新同步', () => void this.controller.start()));
    this.composer.hidden = !!creating || !state?.actor || state?.play_status?.mode === 'defeated' || !!(combat && combat.status !== 'active');
    this.sendButton.disabled = this.controller.locked;
    this.mutationButtons.forEach((blocked, b) => {
      if (!b.isConnected) this.mutationButtons.delete(b); else b.disabled = blocked || this.controller.locked;
    });
    const fieldset = this.creation.querySelector('fieldset'); if (fieldset) fieldset.disabled = this.controller.locked;
    this.renderSelection(view);
  }
  private renderSheet(view: AdventureView) {
    const { state, guide, visuals, events, combat } = view;
    const key = JSON.stringify([this.presentation, state?.session_id, state?.actor, state?.scene.id, state?.scene.time, guide?.objective, guide?.quest, guide?.npcs, events, !!combat, visuals?.theme?.id]);
    if (key === this.sheetKey) return;
    this.sheetKey = key;
    this.sidebar.replaceChildren(); this.scenicCaption.replaceChildren(); this.cast.replaceChildren();
    const a = state?.actor;
    if (this.isIllustrated) {
      const portrait = artImage(visuals, visuals?.player, 'traveller', '冒险者形象'); portrait.className = 'adventure-portrait'; this.sidebar.append(portrait);
    }
    const identity = el('div', '', 'adventure-identity');
    identity.append(el('span', '旅 人 档 案', 'adventure-eyebrow'), el('h2', a?.name || '未启程的旅人'), el('p', a ? `${classNames[a.character_class || ''] || '冒险者'} · 等级 ${a.level || 1}` : '一个世界，等待你的到来'));
    this.sidebar.append(identity);
    this.sceneSummary.textContent = state?.scene.description || '';
    if (a) {
      const health = el('div', '', 'adventure-vitals'); health.append(el('span', '生命'), el('strong', `${a.hp} / ${a.hp_max}`));
      const bar = el('meter'); bar.min = 0; bar.max = a.hp_max; bar.value = Math.max(0, a.hp); bar.setAttribute('aria-label', `生命 ${a.hp}/${a.hp_max}`); health.append(bar);
      const stats = el('div', '', 'adventure-attributes');
      Object.entries(a.abilities).forEach(([id,n]) => { const cell = el('div'); cell.append(el('span', abilityNames[id] || id), el('strong', String(n))); stats.append(cell); });
      const minor = el('div', '', 'adventure-minor'); minor.append(el('span', `护甲 ${a.ac ?? '—'}`), el('span', `经验 ${a.experience_points ?? 0}`));
      this.sidebar.append(health, stats, minor);
      if (a.conditions?.length) this.sidebar.append(el('p', a.conditions.join(' · '), 'adventure-conditions'));
      const equipment = el('div', '', 'adventure-equipment'); equipment.append(el('h3', '随身装备'));
      for (const [type,item] of Object.entries(a.equipped || {})) {
        const b = button(item?.name || (type === 'weapon' ? '未装备武器' : '未装备防具'), () => void this.controller.openPanel('inventory'));
        if (this.isIllustrated) b.prepend(artImage(visuals, item ? visuals?.items?.[item.id] : null, itemCategory(type)));
        equipment.append(b);
      }
      equipment.append(button('查看背包与成长 ↗', () => void this.controller.openPanel('inventory'))); this.sidebar.append(equipment);
      const quest = el('div', '', 'adventure-quest-card'); quest.append(el('h3', '旅途目标'), el('strong', guide?.quest?.name || '继续探索'), el('p', guide?.objective || '看看四周，寻找新的线索。'), button('打开冒险手记 ↗', () => this.journal())); this.sidebar.append(quest);
    }
    this.scenicCaption.append(el('span', combat ? '危 险 遭 遇' : `探索 · 时间 ${state?.scene.time ?? 0}`, 'adventure-eyebrow'), el('h2', state?.scene.name || '旅途将启'));
    const clocks = events?.pending.filter(e => !e.waiting_for_scene && !e.waiting_for_conditions).slice(0, 2) || [];
    clocks.forEach(e => {
      const clock = el('div', '', 'adventure-clock');
      clock.append(el('span', e.title), el('strong', `余 ${e.remaining} ${e.clock === 'combat' ? '轮' : '格'}`)); this.scenicCaption.append(clock);
    });
    if (!combat) guide?.npcs.forEach(npc => {
      const b = this.action(npc.name, () => void this.controller.command('/talk', { npc_id: npc.id }, '正在交谈…'), !state?.play_status?.can_explore);
      if (this.isIllustrated) b.prepend(artImage(visuals, visuals?.characters?.[npc.id], 'portrait'));
      b.append(el('small', '交谈')); b.title = `与${npc.name}交谈`; this.cast.append(b);
    });
  }
  private mapPosition(x: number, y: number) {
    const rect = this.world.getBoundingClientRect();
    this.world.style.setProperty('--map-left', `${Math.max(8, Math.min(x, innerWidth - rect.width - 8))}px`);
    this.world.style.setProperty('--map-top', `${Math.max(8, Math.min(y, innerHeight - rect.height - 8))}px`);
  }
  private mapMode(mode: 'docked' | 'floating' | 'hidden') {
    if (this.worldMode === 'floating') {
      const rect = this.world.getBoundingClientRect(); this.floatSize = { width: rect.width, height: rect.height };
    }
    this.world.style.removeProperty('width'); this.world.style.removeProperty('height');
    if (mode === 'floating' && this.floatSize) {
      this.world.style.width = `${this.floatSize.width}px`; this.world.style.height = `${this.floatSize.height}px`;
    }
    this.worldMode = mode; this.render(this.controller.view);
  }
  private entry(entry: NarrativeHistoryEntry) {
    const r = entry.resolution_summary;
    if (r.player_input && (!r.command_kind || r.command_kind === 'text')) this.narrative.append(el('p', `你：${r.player_input}`, 'adventure-player-line'));
    const article = el('article', '', 'adventure-prose');
    const prose = r.feedback?.summary || entry.gm_narration || entry.narration;
    const labels: Record<string,string> = {talk:'交谈',text:'回应',move:'行旅',interact:'发现',challenge:'尝试',pickup:'拾取',combat:'战况',rest:'休整'};
    article.append(el('div', labels[r.command_kind || 'text'] || '旅途记录', 'adventure-entry-label'));
    paragraphs(article, prose);
    r.world_events?.filter(event => !prose.includes(event.narration)).forEach(event => paragraphs(article, event.narration));
    if (r.check || r.action_status === 'blocked' || r.action_status === 'clarification') {
      article.append(el('span', r.check ? `${r.outcome === 'success' ? '检定成功' : '检定失败'} · ${r.check.total} / ${r.check.dc}` : r.action_status === 'blocked' ? '未执行' : '待明确', 'adventure-check'));
    }
    if (r.check || r.adjudication || entry.gm_narration || r.feedback || entry.gm_notice) {
      const details = el('details', '', 'adventure-rule'); details.append(el('summary', '规则记录'));
      if (r.feedback) paragraphs(details, r.feedback.detail);
      else if (entry.gm_narration) paragraphs(details, entry.narration);
      if (r.check) paragraphs(details, `${abilityNames[r.check.ability] || r.check.ability}：d20 ${r.check.roll} + 修正 ${r.check.modifier} + 熟练 ${r.check.proficiency_bonus} = ${r.check.total}，难度 ${r.check.dc}`);
      paragraphs(details, r.adjudication?.stakes); paragraphs(details, entry.gm_notice); article.append(details);
    }
    this.narrative.append(article);
  }
  selectLocation(id: string) { this.selected = id; this.renderSelection(this.controller.view); }
  selectTarget(id: string) { this.target = id; this.actionsKey = ''; this.render(this.controller.view); this.onTarget(); }
  private renderSelection(view: AdventureView) {
    this.selection.replaceChildren(); this.tools.hidden = !!view.combat;
    if (!view.map || view.combat) return;
    const current = view.map.nodes.find(n => n.id === view.map?.current_node);
    const selected = view.map.nodes.find(n => n.id === this.selected) || current;
    if (!selected) return;
    const near = current?.exits.some(e => e.target_scene_id === selected.id);
    const known = selected.id === current?.id || near || view.map.explored_nodes.includes(selected.id);
    this.selection.append(el('strong', known ? selected.name : '未探索地点'));
    if (selected.id === current?.id) this.selection.append(el('span', '当前位置', 'adventure-eyebrow'));
    else this.selection.append(this.action(near ? '前往这里 →' : '尚无直达路线', () => void this.controller.command('/map/move', { target_scene_id: selected.id }, '正在前往…'), !near || !view.state?.play_status?.can_explore, 'adventure-primary'));
    const routes = el('div', '', 'adventure-routes'); routes.setAttribute('aria-label', '相邻地点');
    current?.exits.forEach(exit => {
      const node = view.map?.nodes.find(n => n.id === exit.target_scene_id);
      if (node) {
        const route = button(node.name, () => this.select(node.id), node.id === selected.id ? 'selected' : '');
        if (this.isIllustrated && view.visuals?.map?.[node.id]) route.prepend(artImage(view.visuals, view.visuals.map[node.id], 'item'));
        routes.append(route);
      }
    });
    this.selection.append(routes);
  }
  private renderActions(view: AdventureView) {
    this.actions.replaceChildren();
    const { state, guide, combat } = view;
    if (!state?.actor) return;
    if (state.play_status?.mode === 'defeated') {
      this.actions.append(el('h2', '冒险暂告一段落'), el('p', state.play_status.reason),
        button('读取存档', () => void this.loadDialog()), this.action('重新冒险', () => this.restartDialog())); return;
    }
    if (combat) {
      if (combat.status !== 'active') {
        this.actions.append(el('h2', ({ victory: '战斗胜利', defeat: '冒险者倒下了', escaped: '成功撤离' })[combat.status]),
          this.action('继续冒险 →', () => void this.controller.command('/combat/end', { reason: combat.status === 'escaped' ? 'flee' : combat.status })));
        return;
      }
      const alive = combat.participants.filter(p => !p.is_player && p.hp > 0);
      if (!alive.some(p => p.id === this.target)) this.target = alive[0]?.id || '';
      const targets = el('div', '', 'adventure-targets'); targets.setAttribute('aria-label', '选择敌人');
      alive.forEach(p => { const b = button(`${p.name} · ${p.hp}/${p.hp_max}`, () => this.selectTarget(p.id)); b.setAttribute('aria-pressed', String(p.id === this.target)); targets.append(b); });
      this.actions.append(targets);
      const list = el('div', '', 'adventure-action-list');
      const playerTurn = combat.participants.find(p => p.is_player)?.id === combat.current_actor_id;
      for (const a of combat.available_actions || []) {
        const b = this.action(a.name, () => void this.controller.command('/combat/action', { action_type: a.id, target_id: a.target === 'enemy' ? this.target : undefined }), !playerTurn || !a.available || (a.target === 'enemy' && !this.target));
        b.title = a.disabled_reason || `${a.description} · ${a.cost}`; list.append(b);
      }
      this.actions.append(list); return;
    }
    const ending = state.journey?.ending;
    if (ending && this.continuedEnding !== `${state.session_id}:${ending.id}`) {
      const card = el('div', '', 'adventure-ending'); card.append(el('span', '本章终章', 'adventure-eyebrow'), el('h2', ending.title)); paragraphs(card, ending.description);
      card.append(button('继续探索', () => { this.continuedEnding = `${state.session_id}:${ending.id}`; this.render(this.controller.view); }), button('选择下一篇冒险', () => void this.controller.openPanel('modules'))); this.actions.append(card); return;
    }
    if (!guide) return;
    const disabled = !state.play_status?.can_explore;
    const list = el('div', '', 'adventure-action-list');
    guide.objects.filter(o => o.status !== 'completed').forEach(o => {
      const b = this.action(o.name, () => void this.controller.command('/interact', { interaction_id: o.id }), disabled || o.status === 'blocked'); b.title = o.reason || o.rule_hint; list.append(b);
    });
    guide.challenges.filter(c => !c.id.startsWith('social:') && !c.blocked_reason).forEach(c => list.append(this.action(c.name, () => this.challenge(c), disabled)));
    guide.targets.filter(t => t.attackable).forEach(t => list.append(this.action(`攻击 · ${t.name}`, () => void this.controller.command('/combat/start', { target_id: t.id }), disabled, 'adventure-danger')));
    if (!list.children.length) list.append(el('p', '可以沿路线继续探索，或描述你的行动。'));
    this.actions.append(list);
    if (guide.challenges.some(c => c.id.startsWith('social:') || c.blocked_reason)) this.actions.append(button('其他尝试', () => this.challenges()));
  }
  private openDialog(title: string) {
    this.dialog?.close(); this.dialog?.remove();
    const dialog = el('dialog', '', 'adventure-dialog'); dialog.setAttribute('aria-label', title);
    const header = el('header'); header.append(el('h2', title), button('关闭', () => dialog.close())); dialog.append(header);
    document.body.append(dialog); dialog.addEventListener('close', () => { dialog.remove(); if (this.dialog === dialog) this.dialog = null; });
    this.dialog = dialog; dialog.showModal(); return dialog;
  }
  private challenge(c: Challenge) {
    const d = this.openDialog(c.name); paragraphs(d, c.description);
    const choice: ChallengeChoice = {};
    const risk = el('p', '', 'adventure-risk');
    const update = () => {
      const a = c.approaches?.find(a => a.id === choice.approach_id), outcome = c.consequences?.find(o => o.id === choice.consequence_id);
      risk.textContent = `${c.check_kind === 'automatic' ? '无需检定' : `难度 ${a?.dc ?? c.dc}`} · ${outcome?.stakes ?? c.stakes}${a ? `\n${a.description}` : ''}`;
    };
    for (const [key, label, options] of [['approach_id', '做法', c.approaches], ['consequence_id', '后果', c.consequences]] as const) {
      if (!options?.length) continue;
      const field = el('label', label); const select = el('select'); select.setAttribute('aria-label', label);
      select.append(new Option('默认', '')); options.forEach(o => select.append(new Option(o.name, o.id)));
      select.onchange = () => { choice[key] = select.value || undefined; update(); }; field.append(select); d.append(field);
    }
    update(); d.append(risk);
    if (c.blocked_reason) paragraphs(d, c.blocked_reason);
    d.append(this.action('尝试', () => { d.close(); void this.controller.command('/challenge', { challenge_id: c.id, choice }); }, !!c.blocked_reason, 'adventure-primary'));
  }
  private challenges() {
    const d = this.openDialog('其他尝试');
    this.controller.view.guide?.challenges.forEach(c => { d.append(button(c.name, () => this.challenge(c))); if (c.blocked_reason) paragraphs(d, c.blocked_reason); });
  }
  private character() {
    const a = this.controller.view.state?.actor; const d = this.openDialog(a?.name || '角色');
    if (!a) { paragraphs(d, '创建角色后，可在这里查看属性与成长。'); return; }
    paragraphs(d, `${classNames[a.character_class || ''] || '冒险者'} · 等级 ${a.level || 1} · 经验 ${a.experience_points || 0}\n生命 ${a.hp}/${a.hp_max} · 护甲 ${a.ac ?? '—'} · 熟练 +${a.proficiency_bonus}`);
    const scores = el('div', '', 'adventure-scores');
    Object.entries(a.abilities).forEach(([key, value]) => { const block = el('div'); block.append(el('span', abilityNames[key]), el('strong', String(value)), el('small', `修正 ${Math.floor((value - 10) / 2) >= 0 ? '+' : ''}${Math.floor((value - 10) / 2)}`)); scores.append(block); }); d.append(scores);
    if (a.skills?.length) { d.append(el('h3', '技能')); a.skills.forEach(s => paragraphs(d, `${skillName(s.name)} ${s.modifier >= 0 ? '+' : ''}${s.modifier}${s.proficient ? ' · 熟练' : ''}`)); }
    const slots = Array.isArray(a.spell_slots) ? a.spell_slots : Object.entries(a.spell_slots || {}).map(([level, current]) => ({ level: Number(level), current, max: a.spell_slots_max?.[level] ?? current }));
    if (slots.length) { d.append(el('h3', '法术位')); slots.forEach(s => paragraphs(d, `${s.level} 环：${s.current} / ${s.max}`)); }
    if (a.class_features && ['warrior', 'rogue'].includes(a.character_class || '')) { d.append(el('h3', '职业能力')); const f = a.class_features;
      if (a.character_class === 'warrior' && f.second_wind_used !== undefined) paragraphs(d, `回气：${f.second_wind_used ? '已使用' : '可用'}`);
      if (a.character_class === 'warrior' && f.action_surge_used !== undefined) paragraphs(d, `动作如潮：${f.action_surge_used ? '已使用' : '可用'}`);
      if (a.character_class === 'rogue' && f.sneak_attack_available !== undefined) paragraphs(d, `偷袭：${f.sneak_attack_available ? '可用' : '本回合已使用'}`);
    }
    this.controller.view.state?.journey?.conditions.forEach(c => paragraphs(d, `${c.name}：${c.description}${c.remaining !== null ? ` · 剩余 ${c.remaining} 个行动` : ''}`));
  }
  private journal() {
    const d = this.openDialog('冒险手记'); const { guide, events, state } = this.controller.view;
    if (!guide) { paragraphs(d, '冒险开始后，线索会记录在这里。'); return; }
    guide.quests.forEach(q => { d.append(el('h3', q.name)); paragraphs(d, `${q.status_label} · ${q.objective}\n${q.reward}`); });
    if (guide.clues.length) { d.append(el('h3', '线索')); guide.clues.forEach(c => paragraphs(d, c)); }
    if (guide.relationships.length) { d.append(el('h3', '人物关系')); guide.relationships.forEach(r => paragraphs(d, `${r.name} · ${r.value}`)); }
    events?.pending.forEach(e => paragraphs(d, `${e.title} · ${e.waiting_for_scene ? '等待回到相关地点' : e.waiting_for_conditions ? '等待条件满足' : `${e.remaining} ${e.clock === 'combat' ? '轮' : '格时间'}后`}`));
    events?.resolved.slice(-6).forEach(e => paragraphs(d, `${e.title} · ${{ fired: '已发生', cancelled: '已取消', expired: '已失效' }[e.status] || e.status}${e.reason ? `：${e.reason}` : ''}`));
    const journey = state?.journey;
    if (journey) paragraphs(d, `已探索 ${journey.locations}/${journey.total_locations} 处地点${journey.rest.supply_item_id ? ` · 补给 ${journey.rest.quantity} 份` : ''}`);
    if (journey?.ending) { d.append(el('h3', journey.ending.title)); paragraphs(d, journey.ending.description); }
  }
  private menu() {
    const d = this.openDialog('冒险菜单');
    d.append(this.action('保存冒险', () => { d.close(); void this.controller.save(); }, !this.controller.view.state?.actor),
      this.action('读取存档', () => void this.loadDialog()), button('模型设置', () => { d.close(); void this.controller.openPanel('settings'); }),
      this.action('重新冒险', () => this.restartDialog(), !this.controller.view.state?.actor));
  }
  private restartDialog() {
    const d = this.openDialog('重新冒险'); paragraphs(d, '将创建独立的新冒险，当前冒险与存档会保留。');
    d.append(this.action('开始新冒险', () => { d.close(); void this.controller.restart(); }, false, 'adventure-primary'));
  }
  private async loadDialog() {
    const d = this.openDialog('读取存档'); const notice = el('p', '正在读取…'); d.append(notice);
    try {
      const saves = await this.controller.saves(); if (!d.isConnected) return;
      notice.textContent = saves.length ? '' : '还没有存档。';
      for (const save of saves) d.append(this.action(`${save.character_name || '未命名角色'} · ${save.scene_name || '冒险起点'} · ${new Date(save.saved_at).toLocaleString('zh-CN')}`, async () => { if (await this.controller.load(save.save_id)) d.close(); }));
    } catch (error) { notice.textContent = error instanceof Error ? error.message : '读取失败'; }
  }
  private createForm() {
    this.creation.replaceChildren();
    const title = el('span', this.controller.view.state?.active_module?.module_name || '新的冒险', 'adventure-eyebrow');
    const form = el('form'); const fields = el('fieldset');
    form.append(title, el('h1', '写下你的名字'), el('p', '选一个职业，让故事从这里开始。'), fields);
    const nameLabel = el('label', '角色名'), name = el('input'); name.required = true; name.maxLength = 40; name.placeholder = '冒险者的名字'; name.setAttribute('aria-label', '角色名'); nameLabel.append(name);
    const classLabel = el('label', '职业'), cls = el('select'); cls.setAttribute('aria-label', '职业');
    Object.entries(classNames).forEach(([id, label]) => cls.append(new Option(label, id))); classLabel.append(cls);
    const description = el('p', '', 'adventure-class-description');
    const generationLabel = el('label', '属性生成'), generation = el('select'); generation.setAttribute('aria-label', '属性生成');
    generation.append(new Option('标准数组', 'standard_array'), new Option('掷骰 · 4d6 取三', 'random_4d6'), new Option('手动输入', 'manual')); generationLabel.append(generation);
    let scores = { ...classAbilities.warrior }; const scoreFields = el('div', '', 'adventure-scores');
    const roll = () => { scores = Object.fromEntries(Object.keys(abilityNames).map(key => [key, Array.from({ length: 4 }, () => crypto.getRandomValues(new Uint32Array(1))[0] % 6 + 1).sort((a, b) => b - a).slice(0, 3).reduce((a, b) => a + b, 0)])) as unknown as AbilityScores; drawScores(); };
    const reroll = button('重新掷骰', roll); reroll.hidden = true;
    const drawScores = () => {
      scoreFields.replaceChildren();
      Object.entries(scores).forEach(([key, value]) => {
        const label = el('label', abilityNames[key]); const input = generation.value === 'standard_array' ? el('select') : el('input'); input.setAttribute('aria-label', abilityNames[key]);
        if (input instanceof HTMLSelectElement) [15, 14, 13, 12, 10, 8].forEach(v => input.append(new Option(String(v), String(v))));
        else { input.type = 'number'; input.min = '3'; input.max = '18'; input.required = true; }
        input.value = String(value); input.onchange = () => {
          const next = Number(input.value), k = key as keyof AbilityScores;
          if (generation.value === 'standard_array') { const other = (Object.keys(scores) as (keyof AbilityScores)[]).find(id => id !== k && scores[id] === next); if (other) scores[other] = scores[k]; }
          scores[k] = next; if (generation.value === 'standard_array') drawScores();
        }; label.append(input); scoreFields.append(label);
      });
    };
    const classChanged = () => {
      description.textContent = { warrior: '坚韧的近战冒险者，能在战斗中回气，争取额外行动。', mage: '运用奥术攻击、控制和治疗；留意有限的法术位。', rogue: '擅长敏捷行动与偷袭，在探索中寻找更巧妙的做法。' }[cls.value as CharacterClass];
      if (generation.value === 'standard_array') scores = { ...classAbilities[cls.value as CharacterClass] }; drawScores();
    };
    cls.onchange = classChanged; generation.onchange = () => { reroll.hidden = generation.value !== 'random_4d6'; if (generation.value === 'random_4d6') roll(); else classChanged(); };
    const submit = el('button', '开始冒险 →', 'adventure-primary'); submit.type = 'submit';
    const error = el('p'); error.setAttribute('role', 'status');
    form.onsubmit = async e => {
      e.preventDefault(); if (this.controller.locked || !form.reportValidity()) return;
      const ok = await this.controller.createCharacter({ name: name.value.trim(), character_class: cls.value, ability_generation: 'manual', abilities: scores });
      if (!ok) error.textContent = this.controller.view.error;
    };
    fields.append(nameLabel, classLabel, description, generationLabel, scoreFields, reroll, submit, error); this.creation.append(form); classChanged();
  }
  destroy() { cancelAnimationFrame(this.scrollFrame); this.mapObserver.disconnect(); this.dragListeners.abort(); this.dialog?.close(); this.dialog?.remove(); this.root.remove(); }
}
const skillLabels: Record<string, string> = { athletics: '运动', acrobatics: '杂技', sleight_of_hand: '巧手', stealth: '隐匿', arcana: '奥秘', history: '历史', investigation: '调查', nature: '自然', religion: '宗教', animal_handling: '驯兽', insight: '洞察', medicine: '医药', perception: '察觉', survival: '生存', deception: '欺骗', intimidation: '威吓', performance: '表演', persuasion: '说服' };
function skillName(name: string) { return skillLabels[name] || name; }
