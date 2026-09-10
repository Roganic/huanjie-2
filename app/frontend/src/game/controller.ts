import { gameFetch, gameError, pendingCommand, recoverCommand } from '../gameApi';
import type { BootstrapState, CombatState, Guidance, EventState, SaveFile } from './types';
import type { MapData } from '../components/mapLayout';
import type { Module } from '../types/module';
import type { ModuleVisuals } from './visuals';

const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export const apiUrl = (path: string) => base ? `${base}${path}` : `/api${path}`;
const sessionKey = 'huanjie.session_id';
export type Panel = 'inventory' | 'modules' | 'studio' | 'settings' | null;
export interface AdventureView {
  state: BootstrapState | null;
  map: MapData | null;
  guide: Guidance | null;
  combat: CombatState | null;
  events: EventState | null;
  busy: string;
  error: string;
  notice: string;
  recovery: boolean;
  revision: number;
  panel: Panel;
  modules: Module[];
  synced: boolean;
  visuals: ModuleVisuals | null;
}

/** One controller owns the session and command lifecycle. Scenes only present facts. */
export class AdventureController {
  private sid = localStorage.getItem(sessionKey);
  private listeners = new Set<() => void>();
  private disposed = false;
  private refreshing = 0;
  private commandChanged = () => this.publish({ recovery: !!this.pending?.uncertain });
  constructor() { window.addEventListener('huanjie-command', this.commandChanged); }
  view: AdventureView = { state: null, map: null, guide: null, combat: null, events: null,
    busy: '', error: '', notice: '', recovery: false, revision: 0, panel: null, modules: [], synced: false, visuals: null };
  snapshot = () => this.view;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private publish(patch: Partial<AdventureView>) {
    if (this.disposed) return;
    this.view = { ...this.view, ...patch };
    this.listeners.forEach(fn => fn());
  }
  get locked() { return !this.view.synced || !!this.view.busy || !!(this.sid && pendingCommand(this.sid)); }
  get pending() { return this.sid ? pendingCommand(this.sid) : null; }
  headers(): Record<string, string> { return this.sid ? { 'X-Session-Id': this.sid } : {}; }
  private setSession(sid: string) { this.sid = sid; localStorage.setItem(sessionKey, sid); }
  async request<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(apiUrl(path), { method: body === undefined ? 'GET' : 'POST',
      headers: { ...this.headers(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new Error(await gameError(response));
    return response.json() as Promise<T>;
  }
  async start() { await this.run('正在读取冒险…', () => this.refresh(), true); }
  async refresh(sessionId?: string) {
    this.publish({ synced: false });
    try { await this.readState(sessionId); }
    catch (error) { this.publish({ error: error instanceof Error ? error.message : '状态同步失败，请重新同步。' }); throw error; }
  }
  private async readState(sessionId?: string) {
    const ticket = ++this.refreshing;
    if (sessionId) this.setSession(sessionId);
    let response = await fetch(apiUrl(this.sid ? '/state' : '/state/bootstrap'), { headers: this.headers() });
    if (response.status === 404 && this.sid) {
      // An expired local session may be replaced; never silently replace a valid adventure.
      this.sid = null; localStorage.removeItem(sessionKey);
      response = await fetch(apiUrl('/state/bootstrap'));
    }
    if (!response.ok) throw new Error(await gameError(response));
    const state = await response.json() as BootstrapState;
    if (this.disposed || ticket !== this.refreshing) return;
    this.setSession(state.session_id);
    const combat = state.game_phase === 'combat' || state.game_phase === 'ended';
    const [map, guide, events, fight, visuals] = await Promise.all([
      this.request<MapData>('/map'),
      state.actor ? this.request<Guidance>('/exploration') : null,
      state.actor ? this.request<EventState>('/events') : null,
      combat ? this.request<CombatState>('/combat/state') : null,
      state.session_id !== this.view.state?.session_id || !this.view.visuals ? this.request<ModuleVisuals>('/modules/visuals') : this.view.visuals,
    ]);
    if (this.disposed || ticket !== this.refreshing) return;
    this.publish({ state, map, guide, events, visuals, combat: fight, revision: this.view.revision + 1,
      recovery: !!pendingCommand(state.session_id), error: '', synced: true });
  }
  async run(label: string, work: () => Promise<unknown>, recovery = false) {
    if (this.view.busy || (!recovery && (!this.view.synced || (this.sid && pendingCommand(this.sid))))) return false;
    this.publish({ busy: label, error: '', notice: '' });
    try { await work(); return true; }
    catch (error) { this.publish({ error: error instanceof Error ? error.message : '未能完成，请重试。' }); return false; }
    finally { this.publish({ busy: '', recovery: !!(this.sid && pendingCommand(this.sid)) }); }
  }
  async command(path: string, body: Record<string, unknown>, label = '正在行动…') {
    return this.run(label, async () => {
      const response = await gameFetch(apiUrl, path, { method: 'POST',
        headers: { ...this.headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: this.view.state?.scene.id, ...body }) });
      if (!response.ok) throw new Error(await gameError(response));
      const result = await response.json();
      await this.refresh();
      // Transient feedback is for actions absent from narrative history (save/move/etc).
      const lastNarration = this.view.state?.narrative_history.at(-1)?.narration || '';
      this.publish({ notice: result.message && !lastNarration.includes(result.message) ? result.message : '' });
    });
  }
  async recover() {
    return this.run('正在恢复上次结果…', async () => {
      if (this.sid) {
        const response = await recoverCommand(apiUrl, this.sid);
        if (response && !response.ok) throw new Error(await gameError(response));
      }
      await this.refresh();
    }, true);
  }
  async createCharacter(body: Record<string, unknown>) {
    return this.run('正在进入冒险…', async () => { await this.request('/character/create', body); await this.refresh(); });
  }
  async restart() {
    return this.run('正在准备新冒险…', async () => {
      const result = await this.request<{ session_id: string }>('/session/restart', {});
      await this.refresh(result.session_id);
    });
  }
  async save() {
    return this.run('正在保存…', async () => { await this.request('/save', {}); this.publish({ notice: '冒险已保存' }); });
  }
  async saves() { return (await this.request<{ saves: SaveFile[] }>('/saves')).saves; }
  async load(saveId: string) {
    return this.run('正在读取存档…', async () => {
      this.publish({ visuals: null });
      const result = await this.request<BootstrapState>('/load', { save_id: saveId });
      await this.refresh(result.session_id);
    });
  }
  setNotice(notice: string) { this.publish({ notice }); }
  closePanel = () => this.publish({ panel: null });
  async openPanel(panel: Panel) {
    this.publish({ panel });
    if (panel === 'modules') await this.run('正在读取模组…', async () => {
      const data = await this.request<{ modules: Module[] }>('/modules'); this.publish({ modules: data.modules });
    });
  }
  async activateModule(id: string) {
    const ok = await this.run('正在准备冒险…', async () => {
      const result = await this.request<{ session_id: string }>('/modules/activate', { module_id: id });
      await this.refresh(result.session_id); this.publish({ panel: null, modules: [] });
    });
    if (!ok) throw new Error(this.view.error || '请先完成当前行动');
  }
  destroy() { this.disposed = true; window.removeEventListener('huanjie-command', this.commandChanged); this.listeners.clear(); }
}
