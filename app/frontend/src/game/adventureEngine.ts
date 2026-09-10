import Phaser from 'phaser';
import { AtlasScene, type AtlasView } from './atlasEngine';
import { AdventureController } from './controller';
import { AdventureInterface } from './interface';
import './adventure.css';
import './journal.css';
import './presentation.css';
import { mountScenery } from './sceneryEngine';

const emptyAtlas: AtlasView = { data: { nodes: [], connections: [], current_node: '', explored_nodes: [] }, selected: '', zoom: 1, rotation: 0, animated: true };

/** Phaser owns scene lifecycle, map cameras, combat roster, selection and the HUD. */
class AdventureScene extends AtlasScene {
  readonly ui: AdventureInterface;
  private roster?: Phaser.GameObjects.Container;
  private unsubscribe?: () => void;
  private atlas = { ...emptyAtlas };
  private wasCombat = false;
  private ready = false;
  private combatKey = '';
  private controller: AdventureController;
  private stopScenery?: () => void;
  constructor(controller: AdventureController, host: HTMLElement) {
    super(emptyAtlas, id => this.chooseLocation(id), 'adventure');
    this.controller = controller;
    this.ui = new AdventureInterface(controller, id => this.chooseLocation(id), {
      locate: () => this.locate(),
      zoom: factor => { this.atlas.zoom = Phaser.Math.Clamp(this.atlas.zoom * factor, .45, 2.5); this.setView(this.atlas); this.fit(); },
      rotate: () => { this.atlas.rotation = (this.atlas.rotation + 45) % 360; this.setView(this.atlas); },
      motion: () => { this.atlas.animated = !this.atlas.animated; this.setView(this.atlas); },
    });
    this.ui.onTarget = () => this.draw();
    this.ui.onPresentationChange = () => { if (this.ready) this.syncScenery(); };
    host.append(this.ui.root);
  }
  create() {
    super.create(); this.ready = true;
    this.syncScenery();
    this.roster = this.add.container();
    this.unsubscribe = this.controller.subscribe(() => {
      this.ui.render(this.controller.view);
      if (this.controller.view.map) this.atlas = { ...this.atlas, data: this.controller.view.map, positions: this.controller.view.visuals?.map_layout };
      this.setView(this.atlas);
    });
    this.scale.on('resize', () => { this.combatKey = ''; this.draw(); });
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => { this.unsubscribe?.(); this.stopScenery?.(); this.ui.destroy(); });
    this.ui.render(this.controller.view);
    void this.controller.start();
  }
  private syncScenery() {
    if (this.ui.isIllustrated) this.stopScenery ??= mountScenery(this.ui.scenery, this.controller);
    else { this.stopScenery?.(); this.stopScenery = undefined; }
  }
  private chooseLocation(id: string) {
    if (this.controller.view.combat || this.controller.view.panel) return;
    this.atlas = { ...this.atlas, selected: id }; this.ui.selectLocation(id); this.setView(this.atlas);
  }
  fit(center = false) {
    if (this.controller?.view.combat) { this.cameras.main.setZoom(1).setScroll(0, 0); return; }
    super.fit(center);
  }
  draw() {
    const combat = this.controller?.view.combat;
    if (!combat) {
      this.navigationEnabled = !this.controller?.view.panel;
      if (this.roster) this.roster.setVisible(false);
      this.nodes?.setVisible(true); this.roadLayer?.setVisible(true);
      if (this.wasCombat) { this.wasCombat = false; this.fit(true); this.combatKey = ''; }
      super.draw(); return;
    }
    if (!this.ready || !this.roster) return;
    this.navigationEnabled = false;
    this.wasCombat = true; this.nodes?.setVisible(false); this.roadLayer?.setVisible(false); this.roster.setVisible(true);
    this.cameras.main.setZoom(1).setScroll(0, 0).setBackgroundColor('#182d27');
    const { width, height } = this.scale;
    const key = JSON.stringify([combat, width, height, this.ui.selectedTarget]);
    if (key === this.combatKey) return;
    this.combatKey = key; this.roster.removeAll(true);
    const participants = combat.initiative_order.map(id => combat.participants.find(p => p.id === id)).filter(p => p !== undefined);
    const cols = width >= 340 ? 2 : 1, rowCount = Math.ceil(participants.length / cols);
    const rowHeight = Math.min(100, (height - 70) / Math.max(1, rowCount)), cardWidth = Math.min(300, (width - 60) / cols);
    const label = this.add.text(width / 2, 25, '先攻队列', { fontFamily: 'system-ui', fontSize: '16px', color: '#d9c293' }).setOrigin(.5, 0); this.roster.add(label);
    participants.forEach((p, index) => {
      const x = width / 2 + (index % cols - (cols - 1) / 2) * (cardWidth + 12);
      const y = 64 + Math.floor(index / cols) * rowHeight;
      const active = p.id === combat.current_actor_id && combat.status === 'active';
      const selected = p.id === this.ui.selectedTarget;
      const color = p.is_player ? 0x8cd3c0 : 0xddaa94;
      const card = this.add.rectangle(x, y, cardWidth, Math.max(40, rowHeight - 12), p.hp <= 0 ? 0x1e2c25 : 0x2a4035).setOrigin(.5, 0).setStrokeStyle(active || selected ? 2 : 1, active ? 0xf1d08f : selected ? color : 0x85724c);
      const font = { fontFamily: '"Songti SC",Georgia,serif', fontSize: cardWidth < 180 || rowHeight < 65 ? '13px' : '16px', color: p.hp <= 0 ? '#8a98a3' : '#f3ebdc' };
      const name = this.add.text(x - cardWidth / 2 + 14, y + 8, `${index + 1}  ${p.name}${p.is_player ? ' · 你' : ''}`, font);
      const hp = this.add.text(x - cardWidth / 2 + 14, y + 31, `${p.hp <= 0 ? '已倒下' : `${p.hp} / ${p.hp_max} 生命`} · 先攻 ${p.initiative}`, { ...font, fontSize: cardWidth < 180 ? '11px' : '13px', color: '#bac5af' });
      this.roster!.add([card, name, hp]);
      if (rowHeight >= 75) this.roster!.add(this.add.rectangle(x - cardWidth / 2 + 14, y + rowHeight - 25, (cardWidth - 28) * Math.max(0, p.hp / p.hp_max), 3, color).setOrigin(0, 0));
      if (!p.is_player && p.hp > 0) { card.setInteractive({ useHandCursor: true }); card.on('pointerup', () => { if (!this.controller.view.panel) this.ui.selectTarget(p.id); }); }
    });
  }
}

export function mountAdventure(host: HTMLElement, controller: AdventureController) {
  const scene = new AdventureScene(controller, host);
  const parent = scene.ui.stage;
  const game = new Phaser.Game({ type: Phaser.AUTO, parent, banner: false, transparent: true,
    scale: { mode: Phaser.Scale.NONE, width: parent.clientWidth || 600, height: parent.clientHeight || 500 },
    scene, render: { antialias: true }, input: { activePointers: 2 }, audio: { noAudio: true },
    fps: { target: 30, forceSetTimeOut: true } });
  const resize = new ResizeObserver(() => { if (parent.clientWidth && parent.clientHeight) game.scale.resize(parent.clientWidth, parent.clientHeight); });
  resize.observe(parent);
  const updateBounds = () => game.scale.updateBounds();
  parent.addEventListener('pointerdown', updateBounds, true);
  return () => { parent.removeEventListener('pointerdown', updateBounds, true); resize.disconnect(); game.destroy(true); scene.ui.destroy(); };
}
