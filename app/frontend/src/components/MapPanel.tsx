import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type KeyboardEvent } from 'react';
import { DIRECTIONS, type MapData } from './mapLayout';
import AtlasCanvas from './AtlasCanvas';
import './FloatingMap.css';

interface MapPanelProps {
  apiUrl: (path: string) => string;
  sessionId: string | null;
  buildSessionHeaders: (sessionId?: string | null, extraHeaders?: HeadersInit) => HeadersInit;
  currentSceneId: string; isVisible: boolean; onClose: () => void;
  onMove: (target: string) => Promise<void>; moving: boolean; canMove: boolean;
}
interface Frame { x:number; y:number; width:number; height:number }
const STORAGE='huanjie.map-window.v1';
function clampFrame(frame: Frame): Frame {
  const width=Math.max(Math.min(320,window.innerWidth-16),Math.min(frame.width,window.innerWidth-16));
  const height=Math.max(Math.min(360,window.innerHeight-16),Math.min(frame.height,window.innerHeight-16));
  return {width,height,x:Math.max(8,Math.min(frame.x,window.innerWidth-width-8)),y:Math.max(8,Math.min(frame.y,window.innerHeight-height-8))};
}
function initialFrame(): Frame {
  const fallback={x:Math.max(8,window.innerWidth-600),y:84,width:560,height:600};
  try {
    const saved=JSON.parse(localStorage.getItem(STORAGE) ?? 'null');
    if (saved && ['x','y','width','height'].every(k=>typeof saved[k]==='number' && Number.isFinite(saved[k]))) return clampFrame(saved);
  } catch { /* Preferences are optional. */ }
  return clampFrame(fallback);
}
function MapIcon() { return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16" /></svg>; }

export function MapPanel({apiUrl,sessionId,buildSessionHeaders,currentSceneId,isVisible,onClose,onMove,moving,canMove}: MapPanelProps) {
  const [map,setMap]=useState<{session:string|null; data:MapData}|null>(null);
  const [error,setError]=useState('');
  const [retry,setRetry]=useState(0);
  const [frame,setFrame]=useState(initialFrame);
  const [zoom,setZoom]=useState(1);
  const [rotation,setRotation]=useState(0);
  const [animated,setAnimated]=useState(true);
  const [selected,setSelected]=useState<{scene:string; id:string}|null>(null);
  const [travelBusy,setTravelBusy]=useState(false);
  const drag=useRef<{type:'move'|'resize'; x:number; y:number; frame:Frame}|null>(null);
  const [locate,setLocate]=useState(0);
  const closeButton=useRef<HTMLButtonElement>(null);
  const travelLock=useRef(false);
  const data=map?.session===sessionId ? map.data : null;
  const fresh=data?.current_node===currentSceneId;
  const adjacent=new Map((data?.nodes.find(n=>n.id===currentSceneId)?.exits ?? []).map(e=>[e.target_scene_id,e.direction]));
  const selectedId=selected?.scene===currentSceneId ? selected.id : currentSceneId;
  const target=data?.nodes.find(n=>n.id===selectedId);


  useEffect(()=>{
    if (!isVisible || !sessionId) return;
    const abort=new AbortController();
    fetch(apiUrl('/map'),{headers:buildSessionHeaders(sessionId),signal:abort.signal})
      .then(async response=>{if(!response.ok) throw new Error('地图加载失败，请重试。');return response.json();})
      .then((value:MapData)=>{
        if (!Array.isArray(value.nodes)||!Array.isArray(value.connections)||!Array.isArray(value.explored_nodes)) throw new Error('地图数据不完整。');
        if (!abort.signal.aborted) {setMap({session:sessionId,data:value});setError('');}
      }).catch(e=>{if(!abort.signal.aborted) setError(e instanceof Error?e.message:'地图加载失败。');});
    return ()=>abort.abort();
  },[apiUrl,sessionId,buildSessionHeaders,currentSceneId,isVisible,retry]);
  useEffect(()=>{
    const resize=()=>setFrame(value=>clampFrame(value));
    window.addEventListener('resize',resize);
    return ()=>window.removeEventListener('resize',resize);
  },[]);
  useEffect(()=>{try {localStorage.setItem(STORAGE,JSON.stringify(frame));} catch { /* Keep working without preference storage. */ }},[frame]);
  useEffect(()=>{
    if (!isVisible) return;
    const previous=document.activeElement as HTMLElement|null;
    closeButton.current?.focus({preventScroll:true});
    return ()=>{if(previous?.isConnected) previous.focus({preventScroll:true});};
  },[isVisible]);


  function begin(event:PointerEvent<HTMLElement>,type:'move'|'resize') {
    if (event.button!==0) return;
    event.preventDefault(); event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current={type,x:event.clientX,y:event.clientY,frame};
  }
  function change(event:PointerEvent<HTMLElement>) {
    if (!drag.current) return;
    const {type,x,y,frame:start}=drag.current;
    const dx=event.clientX-x,dy=event.clientY-y;
    setFrame(clampFrame(type==='move'?{...start,x:start.x+dx,y:start.y+dy}:{...start,width:start.width+dx,height:start.height+dy}));
  }
  function end() {drag.current=null;}
  function keyboard(event:KeyboardEvent<HTMLElement>,type:'move'|'resize') {
    const steps:Record<string,[number,number]>={ArrowLeft:[-16,0],ArrowRight:[16,0],ArrowUp:[0,-16],ArrowDown:[0,16]};
    const step=steps[event.key];if(!step) return;
    event.preventDefault();
    setFrame(v=>clampFrame(type==='move'?{...v,x:v.x+step[0],y:v.y+step[1]}:{...v,width:v.width+step[0],height:v.height+step[1]}));
  }
  async function travel() {
    if (!target || !fresh || !adjacent.has(target.id) || !canMove || moving || travelLock.current) return;
    travelLock.current=true;setTravelBusy(true);setError('');
    try {await onMove(target.id);} catch(e) {setError(e instanceof Error?e.message:'移动失败。');}
    finally {travelLock.current=false;setTravelBusy(false);}
  }
  if (!isVisible) return null;
  const known=target && (data?.explored_nodes.includes(target.id)||adjacent.has(target.id)||target.id===currentSceneId);

  return <section className="atlas-window" role="dialog" aria-label="探索地图" aria-modal="false"
    style={{left:frame.x,top:frame.y,width:frame.width,height:frame.height} as CSSProperties}
    onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();onClose();}}}>
    <header className="atlas-header">
      <button className="atlas-drag" aria-label="移动地图，拖动或使用方向键" onPointerDown={e=>begin(e,'move')} onPointerMove={change} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} onKeyDown={e=>keyboard(e,'move')}>
        <MapIcon/><span>探索地图<small>拖动标题移动</small></span>
      </button>
      <button aria-label="缩小浮窗" title="缩小浮窗" onClick={()=>setFrame(v=>clampFrame({...v,width:v.width-100,height:v.height-70}))}>−</button>
      <button aria-label="放大浮窗" title="放大浮窗" onClick={()=>setFrame(v=>clampFrame({...v,width:v.width+100,height:v.height+70}))}>＋</button>
      <button ref={closeButton} aria-label="关闭地图" title="关闭地图（Esc）" onClick={onClose}>×</button>
    </header>
    <div className="atlas-toolbar">
      <span><i className="atlas-dot current"/>当前位置 <i className="atlas-dot adjacent"/>相邻 <i className="atlas-dot visited"/>已探索</span>
      <button onClick={()=>{setZoom(1);setSelected(null);setLocate(n=>n+1);}} title="定位当前地点">定位</button>
      <label>比例<input aria-label="地图比例" type="range" min="70" max="180" step="10" value={Math.round(zoom*100)} onChange={e=>setZoom(Number(e.target.value)/100)}/></label>
    </div>
    {error && <p className="atlas-error" role="alert">{error} <button onClick={()=>setRetry(n=>n+1)}>重试</button></p>}
    {!data ? <p className="atlas-loading">正在展开地图…</p> : <>
      <AtlasCanvas view={{data,selected:selectedId,zoom,rotation,animated}} locate={locate}
        onSelect={id=>setSelected({scene:currentSceneId,id})}/>
      <div className="atlas-destination">
        <div><strong>{known?target?.name:'未探索地点'}</strong><p>{!fresh?'正在同步当前位置…':!canMove?'当前无法移动，可继续查看地图。':selectedId===currentSceneId?'点击相邻地点，选择下一条路。':adjacent.has(selectedId)?`相邻出口 · ${DIRECTIONS[adjacent.get(selectedId)!]??'前往'}${data.explored_nodes.includes(selectedId)?' · 已探索':' · 尚未探索'}`:'此地点没有当前场景的直达出口。'}</p></div>
        <button className="atlas-travel" disabled={!fresh||!canMove||moving||travelBusy||!adjacent.has(selectedId)} onClick={()=>void travel()}>{moving||travelBusy?'移动中…':'前往此处'}</button>
      </div>
    </>}
    <footer className="atlas-footer">
      <span>拖动地图 · 滚轮缩放</span>
      <button onClick={()=>setRotation(v=>v+90)} aria-label="旋转当前位置箭头" title="旋转当前位置箭头">↻</button>
      <button onClick={()=>setAnimated(v=>!v)} aria-pressed={animated}>{animated?'暂停动画':'开启动画'}</button>
      <button className="atlas-resize" aria-label="调整地图大小，拖动或使用方向键" title="拖动调整大小" onPointerDown={e=>begin(e,'resize')} onPointerMove={change} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} onKeyDown={e=>keyboard(e,'resize')}>◢</button>
    </footer>
  </section>;
}
export default MapPanel;
