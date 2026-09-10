import Phaser from 'phaser';
import type { AdventureController } from './controller';
import { resolveArt, sceneCategory } from './visuals';

/** Decorative scene camera. It never decides targets, dice, rewards or time. */
export function mountScenery(parent: HTMLElement, controller: AdventureController) {
  let unsubscribe: (() => void) | undefined;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  class Scenery extends Phaser.Scene {
    private background?: Phaser.GameObjects.Image;
    private source = '';
    private position = '50% 50%';
    private serial = 0;
    private dust: Phaser.GameObjects.Arc[] = [];
    create() {
      this.cameras.main.setBackgroundColor('#1b302e');
      const geometry = this.add.graphics().setDepth(-1);
      const resize = () => { const { width: w, height: h } = this.scale; geometry.clear().lineStyle(1, 0xb99c61, .12).strokeCircle(w / 2, h / 2, Math.min(w,h) * .35); this.fit(); };
      this.scale.on('resize', resize); resize();
      for (let i = 0; i < 14; i++) this.dust.push(this.add.circle(Math.random() * this.scale.width, Math.random() * this.scale.height, i % 3 === 0 ? 2 : 1, 0xf3d49b, .25).setDepth(2));
      const refresh = () => {
        const v = controller.view, scene = v.state?.scene;
        const art = resolveArt(v.visuals, v.visuals?.scenes?.[scene?.id || ''], sceneCategory(scene?.name));
        this.position = art.position;
        parent.setAttribute('aria-label', `${scene?.name || '旅途'} · 场景插画`);
        if (art.src === this.source) { this.fit(); return; }
        this.source = art.src; const serial = ++this.serial;
        const load = (url: string, fallback = false) => {
          const key = `scenery-${serial}-${fallback ? "fallback" : "primary"}`;
          const event = `filecomplete-image-${key}`;
          const complete = () => {
            this.load.off('loaderror', failed);
            if (serial !== this.serial) { this.textures.remove(key); return; }
            const old = this.background;
            if (old) { this.tweens.killTweensOf(old); const texture = old.texture.key; old.destroy(); this.textures.remove(texture); }
            this.background = this.add.image(0, 0, key).setOrigin(0).setDepth(0); this.fit();
            if (!reduced.matches) { this.background.setAlpha(0); this.tweens.add({ targets: this.background, alpha: 1, duration: 650, ease: 'Sine.easeOut' }); }
          };
          const failed = (file: Phaser.Loader.File) => {
            if (file.key !== key) return;
            this.load.off('loaderror', failed); this.load.off(event, complete);
            if (serial !== this.serial) return;
            if (!fallback && art.fallback !== url) { load(art.fallback, true); return; }
            const old = this.background;
            if (old) { const texture = old.texture.key; old.destroy(); this.textures.remove(texture); this.background = undefined; }
          };
          this.load.once(event, complete); this.load.on('loaderror', failed);
          this.load.image(key, url); if (!this.load.isLoading()) this.load.start();
        };
        load(art.src);
      };
      unsubscribe = controller.subscribe(refresh); refresh();
    }
    private fit() {
      if (!this.background) return;
      const { width: w, height: h } = this.scale;
      const image = this.background, scale = Math.max(w / image.width, h / image.height);
      const [x, y] = this.position.split(' ').map(v => parseFloat(v) / 100);
      image.setScale(scale).setPosition((w - image.width * scale) * x, (h - image.height * scale) * y);
    }
    update(_time: number, delta: number) {
      const hidden = reduced.matches || !!controller.view.panel || document.hidden;
      for (let i = 0; i < this.dust.length; i++) {
        const d = this.dust[i]; d.visible = !hidden;
        if (!hidden) { d.y -= Math.min(delta, 50) * (.003 + i * .0003); if (d.y < -5) d.setPosition(Math.random() * this.scale.width, this.scale.height + 5); }
      }
    }
  }
  const game = new Phaser.Game({ type: Phaser.AUTO, parent, banner: false, scene: Scenery, audio: { noAudio: true },
    scale: { mode: Phaser.Scale.NONE, width: parent.clientWidth || 500, height: parent.clientHeight || 400 },
    fps: { target: 24, forceSetTimeOut: true }, render: { antialias: true } });
  const resize = new ResizeObserver(() => { if (parent.clientWidth && parent.clientHeight) game.scale.resize(parent.clientWidth, parent.clientHeight); }); resize.observe(parent);
  return () => { unsubscribe?.(); resize.disconnect(); game.destroy(true); };
}
