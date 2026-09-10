import Phaser from 'phaser';
import { layoutMap, type MapData } from '../components/mapLayout';

export interface AtlasView {
  data: MapData;
  selected: string;
  zoom: number;
  rotation: number;
  animated: boolean;
  positions?: Record<string,{x:number;y:number;label?:string|null}>;
}

export class AtlasScene extends Phaser.Scene {
    protected navigationEnabled = true;
    private mapKey = '';
    private layout = layoutMap([]);
    private marker?: Phaser.GameObjects.Container;
    protected roadLayer?: Phaser.GameObjects.Graphics;
    protected nodes?: Phaser.GameObjects.Container;
    private dragStart?: { x: number; y: number; scrollX: number; scrollY: number };
    private dragged = false;
    protected view: AtlasView;
    private select: (id: string) => void;
    constructor(view: AtlasView, select: (id: string) => void, key = 'atlas') { super(key); this.view = view; this.select = select; }
    setView(view: AtlasView) { this.view = view; this.draw(); }
    create() {
      this.cameras.main.setBackgroundColor('rgba(0,0,0,0)');
      this.roadLayer = this.add.graphics(); this.nodes = this.add.container();
      this.input.on('pointerdown', (p: Phaser.Input.Pointer) => {
        if (!this.navigationEnabled) return;
        this.dragged = false; this.dragStart = { x:p.x, y:p.y, scrollX:this.cameras.main.scrollX, scrollY:this.cameras.main.scrollY };
      });
      this.input.on('pointermove', (p: Phaser.Input.Pointer) => {
        if (!this.navigationEnabled || !p.isDown || !this.dragStart) return;
        const dx=p.x-this.dragStart.x, dy=p.y-this.dragStart.y;
        if (Math.hypot(dx,dy)<6 && !this.dragged) return;
        this.dragged=true; this.cameras.main.setScroll(this.dragStart.scrollX-dx/this.cameras.main.zoom,this.dragStart.scrollY-dy/this.cameras.main.zoom);
      });
      this.input.on('pointerup', () => { this.dragStart=undefined; });
      this.input.on('wheel', (_:unknown, __:unknown, ___:number, dy:number) => {
        if (!this.navigationEnabled) return;
        this.view.zoom=Phaser.Math.Clamp(this.view.zoom*Math.exp(-dy*.001),.45,2.5); this.draw();
      });
      this.scale.on('resize', () => { this.fit(true); this.draw(); }); this.draw();
    }
    fit(center=false) {
      const camera=this.cameras.main; camera.setSize(this.scale.width,this.scale.height);
      const base=Math.min(camera.width/this.layout.width,camera.height/this.layout.height,1.15);
      camera.setZoom(Math.max(.1,base*this.view.zoom));
      if (center) camera.centerOn(this.layout.width/2,this.layout.height/2);
    }
    locate() { this.fit(true); this.draw(); }
    draw() {
      if (!this.nodes || !this.roadLayer) return;
      this.cameras.main.setBackgroundColor('rgba(0,0,0,0)');
      const key=JSON.stringify([this.view.data.nodes.map(n=>[n.id,n.exits]),this.view.positions,this.scale.width,this.scale.height]);
      const changed=key!==this.mapKey;
      if (changed) {
        const positions=this.view.positions;
        this.layout=positions && this.view.data.nodes.every(n=>positions[n.id]) ? {positions:new Map(this.view.data.nodes.map(n=>[n.id,positions[n.id]])),width:1000,height:620} : layoutMap(this.view.data.nodes);
        const ratio=Math.max(1,this.scale.width/Math.max(1,this.scale.height));
        const height=this.layout.width/ratio, unit=this.layout.width/Math.max(1,this.scale.width);
        const points=[...this.layout.positions.values()];
        const xs=points.map(p=>p.x), ys=points.map(p=>p.y);
        const minX=Math.min(...xs), minY=Math.min(...ys);
        const spanX=Math.max(1,Math.max(...xs)-minX), spanY=Math.max(1,Math.max(...ys)-minY);
        // Reserve screen-space room for the pointer and labels at every edge.
        this.layout={...this.layout,height,positions:new Map([...this.layout.positions].map(([id,p])=>[id,{
          x:45*unit+(p.x-minX)/spanX*Math.max(1,this.layout.width-90*unit),
          y:35*unit+(p.y-minY)/spanY*Math.max(1,height-83*unit),
        }]))};
        this.mapKey=key;
      }
      this.fit(changed);
      if(this.marker)this.tweens.killTweensOf(this.marker);
      this.nodes.removeAll(true);this.roadLayer.clear();
      const current=this.view.data.current_node;
      const adjacent=new Set(this.view.data.nodes.find(n=>n.id===current)?.exits.map(e=>e.target_scene_id));
      const visited=new Set(this.view.data.explored_nodes), drawn=new Set<string>();
      for(const link of this.view.data.connections){
        const key=[link.from_node,link.to_node].sort().join('|');if(drawn.has(key))continue;drawn.add(key);
        const a=this.layout.positions.get(link.from_node),b=this.layout.positions.get(link.to_node);if(!a||!b)continue;
        const near=link.from_node===current||link.to_node===current;
        const curve=new Phaser.Curves.QuadraticBezier(new Phaser.Math.Vector2(a.x,a.y),new Phaser.Math.Vector2((a.x+b.x)/2+(b.y-a.y)*.08,(a.y+b.y)/2-(b.x-a.x)*.08),new Phaser.Math.Vector2(b.x,b.y));
        const points=curve.getPoints(32);
        this.roadLayer.lineStyle(near?10:6,0x826443,near?.3:.15).strokePoints(points);
        this.roadLayer.lineStyle(near?3:2,0x6b5439,near?.9:.45);
        for(let i=0;i<points.length-1;i++){if(near||i%3!==0)this.roadLayer.lineBetween(points[i].x,points[i].y,points[i+1].x,points[i+1].y);}
      }
      for(const node of this.view.data.nodes){
        const point=this.layout.positions.get(node.id)!;
        const active=node.id===current,known=active||adjacent.has(node.id)||visited.has(node.id),selected=this.view.selected===node.id;
        const color=active?0x284f43:known?0x785b36:0xa99a7d;
        // Compensate only for viewport fitting; preserve the player's zoom for
        // the icon, label, pointer and hit area together.
        const group=this.add.container(point.x,point.y).setScale(this.view.zoom/this.cameras.main.zoom);
        const tile=this.add.rectangle(0,0,30,30,active?0x355748:0xe7d7b4,known?1:.65).setStrokeStyle(selected||active?2:1,color);
        if(selected)group.add(this.add.rectangle(0,0,38,38).setStrokeStyle(1,0x9b733d));
        const g=this.add.graphics().lineStyle(1.5,active?0xf5e6be:color);
        if(!known){g.strokeCircle(0,-3,4);g.lineBetween(0,1,0,5);g.fillStyle(color).fillCircle(0,9,1);}
        else if(/林|森林|forest/.test(node.name)){g.strokeTriangle(-9,5,-3,-10,4,5);g.strokeTriangle(-2,9,5,-6,11,9);g.lineBetween(-3,5,-3,11);}
        else if(/酒馆|村|镇|棚|工坊|市/.test(node.name)){g.strokeTriangle(-11,-2,0,-12,11,-2);g.strokeRect(-8,-2,16,13);g.strokeRect(-2,4,4,7);}
        else{g.strokeRect(-9,-9,18,20);g.strokeRect(-4,0,8,11);g.lineBetween(-12,12,12,12);g.lineBetween(-11,-10,11,-10);}
        group.add([tile,g]);
        const name=known?(this.view.positions?.[node.id]?.label||node.name):'未探索';
        const label=this.add.text(0,21,name,{fontFamily:'"Songti SC",Georgia,serif',fontSize:'12px',color:active?'#244c3d':known?'#483a28':'#887a60',backgroundColor:'#e7d8b8',padding:{x:4,y:2},align:'center',wordWrap:{width:85,useAdvancedWrap:true}}).setOrigin(.5,0)
          .setResolution(Math.ceil(Math.max(1,this.view.zoom)*(window.devicePixelRatio || 1)));
        const hit=this.add.zone(0,8,95,72).setInteractive({useHandCursor:true});
        hit.on('pointerup',()=>{if(this.navigationEnabled&&this.dragStart&&!this.dragged)this.select(node.id);});
        hit.on('pointerover',()=>tile.setStrokeStyle(2,0x315b47));hit.on('pointerout',()=>tile.setStrokeStyle(active||selected?2:1,color));
        group.add([label,hit]);this.nodes.add(group);
        if(active){
          this.marker=this.add.container(0,-30,[this.add.triangle(-4,0,0,0,8,3,8,18,0xdec180),this.add.triangle(4,0,0,3,8,0,0,18,0x8a6234)]).setAngle(this.view.rotation);
          group.add(this.marker);
          if(this.view.animated&&!matchMedia('(prefers-reduced-motion: reduce)').matches)this.tweens.add({targets:this.marker,y:-35,duration:900,yoyo:true,repeat:-1,ease:'Sine.easeInOut'});
        }
      }
    }
}

/** Standalone atlas used by the optional floating map. */
export function mountAtlas(parent: HTMLElement, initial: AtlasView, select: (id: string) => void) {
  let active: AtlasScene | undefined = new AtlasScene(initial, select);
  const game = new Phaser.Game({ type: Phaser.AUTO, parent, transparent: true, banner: false,
    scale: { mode: Phaser.Scale.NONE, width: parent.clientWidth, height: parent.clientHeight },
    scene: active, render: { antialias: true }, input: { activePointers: 2 },
    audio: { noAudio: true }, fps: { target: 30, forceSetTimeOut: true } });
  const observer = new ResizeObserver(() => game.scale.resize(parent.clientWidth, parent.clientHeight));
  observer.observe(parent);
  return {
    update(next: AtlasView) { active?.setView(next); },
    locate() { active?.locate(); },
    destroy() { observer.disconnect(); active = undefined; game.destroy(true); },
  };
}
