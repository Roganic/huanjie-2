import { useEffect, useRef, useState } from 'react';
import type { AtlasView } from '../game/atlasEngine';
import type { mountAtlas } from '../game/atlasEngine';

export default function AtlasCanvas({ view, onSelect, locate }: { view: AtlasView; onSelect: (id: string) => void; locate: number }) {
  const container = useRef<HTMLDivElement>(null);
  const engine = useRef<ReturnType<typeof mountAtlas>>(null);
  const latest = useRef({ view, onSelect });
  const [error, setError] = useState('');
  useEffect(() => { latest.current = { view, onSelect }; engine.current?.update(view); }, [view, onSelect]);
  useEffect(() => {
    let disposed = false;
    import('../game/atlasEngine').then(({ mountAtlas }) => {
      if (!disposed && container.current) engine.current = mountAtlas(container.current, latest.current.view, id => latest.current.onSelect(id));
    }).catch(() => { if (!disposed) setError('地图画面加载失败，可使用地点列表。'); });
    return () => { disposed = true; engine.current?.destroy(); engine.current = null; };
  }, []);
  useEffect(() => { engine.current?.locate(); }, [locate]);
  return <div className="atlas-engine-wrap">
    <div className="atlas-engine" ref={container} aria-label="地图，可拖动平移或滚轮缩放" />
    {error && <p role="alert">{error}</p>}
    <details className="atlas-location-list"><summary>地点列表</summary>
      {view.data.nodes.map(node => {
        const current = node.id === view.data.current_node;
        const near = view.data.nodes.find(n => n.id === view.data.current_node)?.exits.some(e => e.target_scene_id === node.id);
        const known = current || near || view.data.explored_nodes.includes(node.id);
        return <button key={node.id} data-testid={`map-node-${node.id}`} aria-current={current ? 'location' : undefined}
          aria-pressed={view.selected === node.id} onClick={() => onSelect(node.id)}>
          {known ? node.name : '未探索地点'}{current ? ' · 你在这里' : near ? ' · 相邻' : ''}
        </button>;
      })}
    </details>
  </div>;
}
