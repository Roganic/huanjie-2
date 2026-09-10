import './MapPanel.css';
import { useDialogFocus } from "../hooks/useDialogFocus";
import { gameFetch } from "../gameApi";
import { useEffect, useState } from "react";
import "./InventoryPanel.css";
import ArtImage from './ArtImage';
import { itemCategory, type ModuleVisuals } from '../game/visuals';

interface Item {
  id: string; name: string; type: string; quantity?: number; description: string;
  damage_dice?: string; base_ac?: number; effect_type?: string;
}
interface Inventory {
  items: Item[];
  equipped: { weapon: Item | null; armor: Item | null };
  available_items: Item[];
}
interface Progression {
  journey: { conditions: { id: string }[]; rest: { can_long_rest: boolean; long_rest_reason: string; description: string } };
  level_cap: number;
  play_status: { can_explore: boolean; can_rest: boolean; rest_reason: string; reason: string };
  level: number; experience_points: number; next_level_xp: number | null;
  progress: { xp_current: number; xp_needed: number };
  hit_dice_remaining: number; hit_dice_total: number; can_short_rest: boolean;
  skills: { name: string; ability: string; proficient: boolean; modifier: number }[];
}
interface Props {
  visuals?: ModuleVisuals | null;
  sessionId: string;
  apiUrl: (path: string) => string;
  pending: boolean; revision: unknown;
  hp: number; hpMax: number; inCombat: boolean;
  onChanged: () => Promise<unknown>;
  onClose: () => void;
}

const SKILLS: Record<string, string> = {
  athletics: "运动", acrobatics: "体操", sleight_of_hand: "巧手", stealth: "隐匿",
  arcana: "奥秘", history: "历史", investigation: "调查", nature: "自然", religion: "宗教",
  animal_handling: "驯兽", insight: "洞悉", medicine: "医药", perception: "察觉", survival: "求生",
  deception: "欺瞒", intimidation: "威吓", performance: "表演", persuasion: "说服",
};

export default function InventoryPanel({ sessionId, apiUrl, hp, hpMax, inCombat, pending, revision: parentRevision, onChanged, onClose, visuals }: Props) {
  const dialog = useDialogFocus(onClose);
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [progress, setProgress] = useState<Progression | null>(null);
  const [tab, setTab] = useState<"inventory" | "progression">("inventory");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const abort = new AbortController();
    async function load() {
      try {
        const responses = await Promise.all(["/inventory", "/character/progression"].map(path =>
          fetch(apiUrl(path), { headers: { "X-Session-Id": sessionId }, signal: abort.signal })));
        if (responses.some(r => !r.ok)) throw new Error("角色数据加载失败，请重试。");
        const [items, growth] = await Promise.all(responses.map(r => r.json()));
        if (!abort.signal.aborted) { setInventory(items); setProgress(growth); }
      } catch (err) {
        if (!abort.signal.aborted) setError(err instanceof Error ? err.message : "加载失败");
      }
    }
    void load();
    return () => abort.abort();
  }, [apiUrl, sessionId, revision, parentRevision]);

  async function act(path: string, body: object) {
    if (busy || pending) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await gameFetch(apiUrl, path, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Session-Id": sessionId },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "操作失败");
      setNotice([result.gm?.notice, result.gm_narration, result.message].filter(Boolean).join("\n\n"));
      await onChanged();
      setRevision(value => value + 1);
    } catch (err) { setError(err instanceof Error ? err.message : "操作失败"); }
    finally { setBusy(false); }
  }

  const disabled = pending || busy || inCombat || hp <= 0 || progress?.play_status?.can_explore === false;
  return <div className="map-panel-overlay" onClick={() => { onClose(); }}>
    <div ref={dialog} tabIndex={-1} className="map-panel inventory-panel" role="dialog" aria-modal="true" aria-labelledby="inventory-title" onClick={event => event.stopPropagation()}>
      <div className="map-panel-header">
        <h2 id="inventory-title" className="map-panel-title">行囊与成长</h2>
        <button className="map-panel-close" disabled={false} onClick={onClose} aria-label="关闭行囊与成长">✕</button>
      </div>
      <div className="inventory-tabs">
        <button aria-pressed={tab === "inventory"} onClick={() => setTab("inventory")}>背包与装备</button>
        <button aria-pressed={tab === "progression"} onClick={() => setTab("progression")}>成长与技能</button>
      </div>
      <div className="map-panel-content">
        <p className="inventory-summary">生命 {hp} / {hpMax} · {hp <= 0 ? "本次冒险已结束，请读取存档或重新冒险" : inCombat ? "战斗结束后可整理行囊与休息" : "探索期间可整理装备与休息"}</p>
        {notice && <p className="inventory-notice" role="status">{notice}</p>}
        {error && <div role="alert" className="inventory-error">{error} <button onClick={() => { setError(""); setRevision(n => n + 1); }}>重新加载</button></div>}
        {(!inventory || !progress) && !error && <p>正在整理行囊…</p>}
        {inventory && progress && tab === "inventory" && <>
          <h3>已装备</h3>
          {(["weapon", "armor"] as const).map(slot => <div className="inventory-row" key={slot}>
            <ArtImage className="inventory-art" visuals={visuals} slot={visuals?.items?.[inventory.equipped[slot]?.id || '']} fallback={itemCategory(slot)} />
            <div><strong>{slot === "weapon" ? "武器" : "护甲"}</strong><p>{inventory.equipped[slot]?.name ?? "未装备"}</p></div>
            <button disabled={disabled || !inventory.equipped[slot]} onClick={() => void act("/inventory/unequip", { slot })}>卸下{slot === "weapon" ? "武器" : "护甲"}</button>
          </div>)}
          <h3>背包 · {inventory.items.reduce((sum, item) => sum + (item.quantity ?? 1), 0)} 件</h3>
          {inventory.items.length === 0 && <p>背包空空如也。</p>}
          {inventory.items.map(item => {
            const equipped = inventory.equipped.weapon?.id === item.id || inventory.equipped.armor?.id === item.id;
            return <div className="inventory-row" key={item.id}>
              <ArtImage className="inventory-art" visuals={visuals} slot={visuals?.items?.[item.id]} fallback={itemCategory(item.type)} />
              <div><strong>{item.name} ×{item.quantity}</strong>{equipped && <span className="inventory-tag">已装备</span>}
                <p>{item.description}{item.damage_dice ? ` · 伤害 ${item.damage_dice}` : ""}{item.base_ac ? ` · 基础防御 ${item.base_ac}` : ""}</p>
              </div>
              {(item.type === "weapon" || item.type === "armor") && <button disabled={disabled || equipped} onClick={() => void act("/inventory/equip", { item_id: item.id })}>装备{item.name}</button>}
              {item.type === "consumable" && <button disabled={disabled || (item.effect_type === "cure_poison" ? !progress.journey.conditions.some(c => c.id === "poisoned") : hp >= hpMax)} onClick={() => void act("/inventory/use", { item_id: item.id })}>使用{item.name}</button>}
            </div>;
          })}
          <h3>附近可拾取</h3>
          {!inventory.available_items.length && <p>附近没有可拾取物品。</p>}
          {inventory.available_items.map(item => <div className="inventory-row" key={item.id}>
            <ArtImage className="inventory-art" visuals={visuals} slot={visuals?.items?.[item.id]} fallback={itemCategory(item.type)} />
            <div><strong>{item.name}</strong><p>{item.description}</p></div>
            <button disabled={disabled} onClick={() => void act("/inventory/pickup", { item_id: item.id })}>拾取{item.name}</button>
          </div>)}
        </>}
        {progress && tab === "progression" && <>
          <h3>等级 {progress.level} · 当前支持 1–{progress.level_cap} 级</h3>
          <p>累计经验 {progress.experience_points}{progress.next_level_xp === null ? " · 已达当前版本等级上限" : ` · 下一级需 ${progress.next_level_xp}`}</p>
          <progress className="growth-progress" max={progress.progress.xp_needed || 1} value={progress.progress.xp_needed ? Math.min(progress.progress.xp_current, progress.progress.xp_needed) : 1} aria-label="升级经验进度" />
          <p className="inventory-summary">战斗胜利与完成任务获得经验；升级同步提高生命值、生命骰及技能熟练加值。</p>
          <h3>技能加值</h3>
          <div className="growth-skills">{progress.skills.map(skill => <div key={skill.name} className="inventory-row">
            <span>{SKILLS[skill.name] ?? skill.name}{skill.proficient && <span className="inventory-tag">熟练</span>}</span>
            <strong>{skill.modifier >= 0 ? "+" : ""}{skill.modifier}</strong>
          </div>)}</div>
        </>}
        {progress && <section className="inventory-rest">
          <h3>休息与恢复</h3>
          <p>剩余生命骰 {progress.hit_dice_remaining} / {progress.hit_dice_total}</p>
          {progress.play_status?.rest_reason && <p>{progress.play_status.rest_reason}</p>}
          <p>{progress.journey.rest.description}</p>
          {progress.journey.rest.long_rest_reason && <p>{progress.journey.rest.long_rest_reason}</p>}
          <div className="inventory-rest-actions">
            <button disabled={disabled || !progress.can_short_rest || !progress.play_status?.can_rest} onClick={() => void act("/character/rest", { kind: "short" })}>短休 · 恢复能力，治疗时消耗生命骰</button>
            <button disabled={disabled || !progress.journey.rest.can_long_rest} onClick={() => void act("/character/rest", { kind: "long" })}>长休 · 恢复生命与资源</button>
          </div>
        </section>}
      </div>
    </div>
  </div>;
}
