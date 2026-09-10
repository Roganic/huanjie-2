export interface MapNode {
  id: string; name: string; description: string;
  exits: { direction: string; target_scene_id: string }[];
}
export interface MapData {
  current_node: string; nodes: MapNode[];
  connections: { from_node: string; to_node: string; direction: string }[];
  explored_nodes: string[];
}
export const DIRECTIONS: Record<string, string> = {
  north: '北', south: '南', east: '东', west: '西', up: '上层', down: '下层',
  northeast: '东北', northwest: '西北', southeast: '东南', southwest: '西南',
};
/** Deterministic force layout. Only authored exits define routes; geometry is cosmetic. */
export function layoutMap(nodes: MapNode[]) {
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const hash = (id: string) => [...id].reduce((n, c) => Math.imul(n ^ c.charCodeAt(0), 16777619) >>> 0, 2166136261);
  const points = ordered.map((node, i) => {
    const angle = i * 2.39996323 + (hash(node.id) % 100) / 300;
    const radius = 85 * Math.sqrt(i + 1);
    return { id: node.id, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
  });
  const index = new Map(points.map((p, i) => [p.id, i]));
  const links = new Set<string>();
  ordered.forEach((node, i) => node.exits.forEach(exit => {
    const j = index.get(exit.target_scene_id);
    if (j !== undefined && j !== i) links.add([i, j].sort((a, b) => a - b).join(':'));
  }));
  const edges = [...links].map(key => key.split(':').map(Number));
  for (let step = 0; step < 180; step++) {
    const forces = points.map(() => ({ x: 0, y: 0 }));
    for (let i = 0; i < points.length; i++) for (let j = i + 1; j < points.length; j++) {
      const dx = points[i].x - points[j].x, dy = points[i].y - points[j].y;
      const distance = Math.max(1, Math.hypot(dx, dy)), strength = 14000 / (distance * distance);
      const fx = dx / distance * strength, fy = dy / distance * strength;
      forces[i].x += fx; forces[i].y += fy; forces[j].x -= fx; forces[j].y -= fy;
    }
    for (const [i, j] of edges) {
      const dx = points[j].x - points[i].x, dy = points[j].y - points[i].y;
      const distance = Math.max(1, Math.hypot(dx, dy)), strength = (distance - 190) * .018;
      const fx = dx / distance * strength, fy = dy / distance * strength;
      forces[i].x += fx; forces[i].y += fy; forces[j].x -= fx; forces[j].y -= fy;
    }
    const cooling = 1 - step / 210;
    points.forEach((p, i) => {
      p.x += Math.max(-8, Math.min(8, forces[i].x - p.x * .0007)) * cooling;
      p.y += Math.max(-8, Math.min(8, forces[i].y - p.y * .0007)) * cooling;
    });
  }
  const minX = Math.min(0, ...points.map(p => p.x)), minY = Math.min(0, ...points.map(p => p.y));
  const positions = new Map(points.map(p => [p.id, { x: p.x - minX + 100, y: p.y - minY + 100 }]));
  return { positions, width: Math.max(0, ...points.map(p => p.x)) - minX + 200,
    height: Math.max(0, ...points.map(p => p.y)) - minY + 210 };
}
