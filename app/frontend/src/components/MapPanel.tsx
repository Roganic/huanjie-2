import { useEffect, useRef, useState } from "react";

export interface MapNode {
  id: string;
  name: string;
  description?: string;
  x: number;
  y: number;
  connected_to: string[];
}

export interface MapData {
  nodes: MapNode[];
  current_node_id: string;
  explored_node_ids: string[];
}

interface MapPanelProps {
  mapData: MapData | null;
  isOpen: boolean;
  onClose: () => void;
  loading?: boolean;
}

// Canvas size
const CANVAS_WIDTH = 600;
const CANVAS_HEIGHT = 400;
const NODE_RADIUS = 20;

// Styles
const overlayStyle: React.CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: "rgba(0, 0, 0, 0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const panelStyle: React.CSSProperties = {
  backgroundColor: "#1a1a2e",
  borderRadius: "12px",
  boxShadow: "0 20px 60px rgba(0, 0, 0, 0.5)",
  width: "680px",
  maxWidth: "90vw",
  maxHeight: "90vh",
  display: "flex",
  flexDirection: "column",
  border: "1px solid #2d2d44",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "16px 20px",
  borderBottom: "1px solid #2d2d44",
};

const titleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: "18px",
  fontWeight: 600,
  color: "#e5e7eb",
  display: "flex",
  alignItems: "center",
  gap: "8px",
};

const closeBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#9ca3af",
  fontSize: "20px",
  cursor: "pointer",
  padding: "4px 8px",
  borderRadius: "4px",
  transition: "all 0.2s",
};

const contentStyle: React.CSSProperties = {
  padding: "20px",
  display: "flex",
  flexDirection: "column",
  gap: "16px",
  overflow: "auto",
};

const loadingStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: "12px",
  padding: "40px",
  color: "#9ca3af",
};

const spinnerStyle: React.CSSProperties = {
  width: "32px",
  height: "32px",
  border: "3px solid #2d2d44",
  borderTopColor: "#60a5fa",
  borderRadius: "50%",
  animation: "spin 1s linear infinite",
};

const emptyStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
  padding: "40px",
  color: "#9ca3af",
  textAlign: "center",
};

const legendStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "16px",
  padding: "12px 16px",
  backgroundColor: "#16162a",
  borderRadius: "8px",
  fontSize: "13px",
};

const legendItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  color: "#d1d5db",
};

const legendDotStyle = (color: string): React.CSSProperties => ({
  width: "12px",
  height: "12px",
  borderRadius: "50%",
  backgroundColor: color,
  border: "2px solid #374151",
});

const canvasContainerStyle: React.CSSProperties = {
  position: "relative",
  display: "flex",
  justifyContent: "center",
  backgroundColor: "#0f0f1a",
  borderRadius: "8px",
  padding: "12px",
  border: "1px solid #2d2d44",
};

const canvasStyle: React.CSSProperties = {
  borderRadius: "4px",
  cursor: "crosshair",
};

const tooltipStyle = (x: number, y: number): React.CSSProperties => ({
  position: "fixed",
  left: x + 10,
  top: y - 10,
  backgroundColor: "#1f2937",
  color: "#e5e7eb",
  padding: "10px 14px",
  borderRadius: "8px",
  fontSize: "13px",
  maxWidth: "200px",
  pointerEvents: "none",
  zIndex: 1001,
  boxShadow: "0 4px 20px rgba(0, 0, 0, 0.4)",
  border: "1px solid #374151",
});

const tooltipTitleStyle: React.CSSProperties = {
  fontWeight: 600,
  marginBottom: "4px",
  color: "#f3f4f6",
};

const tooltipDescStyle: React.CSSProperties = {
  color: "#9ca3af",
  fontSize: "12px",
  marginBottom: "6px",
  lineHeight: 1.4,
};

const tooltipStatusStyle: React.CSSProperties = {
  fontSize: "11px",
  color: "#60a5fa",
};

const statsStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "12px 16px",
  backgroundColor: "#16162a",
  borderRadius: "8px",
  fontSize: "13px",
  color: "#d1d5db",
};

const currentLocationStyle: React.CSSProperties = {
  color: "#4ade80",
  fontWeight: 500,
};

const mapButtonStyle = (isOpen: boolean): React.CSSProperties => ({
  position: "fixed",
  bottom: "20px",
  right: "20px",
  width: "56px",
  height: "56px",
  borderRadius: "50%",
  backgroundColor: isOpen ? "#4ade80" : "#3b82f6",
  color: "#fff",
  border: "none",
  boxShadow: "0 4px 14px rgba(59, 130, 246, 0.4)",
  cursor: "pointer",
  fontSize: "24px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  transition: "all 0.2s",
  zIndex: 100,
});

export function MapButton({
  isOpen,
  onClick,
}: {
  isOpen: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={mapButtonStyle(isOpen)}
      title={isOpen ? "关闭地图" : "打开地图"}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "scale(1.05)";
        e.currentTarget.style.boxShadow = "0 6px 20px rgba(59, 130, 246, 0.5)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "scale(1)";
        e.currentTarget.style.boxShadow = "0 4px 14px rgba(59, 130, 246, 0.4)";
      }}
    >
      🗺️
    </button>
  );
}

export function MapPanel({ mapData, isOpen, onClose, loading }: MapPanelProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hoveredNode, setHoveredNode] = useState<MapNode | null>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Draw the map on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !mapData) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear canvas
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Draw background
    ctx.fillStyle = "#0f0f1a";
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Draw grid lines (subtle)
    ctx.strokeStyle = "#1e1e32";
    ctx.lineWidth = 1;
    for (let x = 0; x <= CANVAS_WIDTH; x += 40) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, CANVAS_HEIGHT);
      ctx.stroke();
    }
    for (let y = 0; y <= CANVAS_HEIGHT; y += 40) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(CANVAS_WIDTH, y);
      ctx.stroke();
    }

    const { nodes, current_node_id, explored_node_ids } = mapData;
    const exploredSet = new Set(explored_node_ids);

    // Helper to check if a node is connected to current node
    const isConnectedToCurrent = (nodeId: string) => {
      const currentNode = nodes.find((n) => n.id === current_node_id);
      return currentNode?.connected_to.includes(nodeId) ?? false;
    };

    // Helper to get node color
    const getNodeColor = (node: MapNode) => {
      if (node.id === current_node_id) {
        return "#4ade80"; // Bright green for current node
      }
      if (exploredSet.has(node.id)) {
        return "#60a5fa"; // Blue for explored nodes
      }
      if (isConnectedToCurrent(node.id)) {
        return "#fbbf24"; // Amber for connected but unexplored
      }
      return "#6b7280"; // Gray for unexplored and not connected
    };

    // Draw connections first (so they appear behind nodes)
    nodes.forEach((node) => {
      node.connected_to.forEach((targetId) => {
        const targetNode = nodes.find((n) => n.id === targetId);
        if (!targetNode) return;

        // Determine connection style
        const isExplored = exploredSet.has(node.id) && exploredSet.has(targetId);
        const isCurrentConnection =
          node.id === current_node_id || targetId === current_node_id;

        ctx.beginPath();
        ctx.moveTo(node.x, node.y);
        ctx.lineTo(targetNode.x, targetNode.y);

        if (isCurrentConnection) {
          ctx.strokeStyle = "#4ade80";
          ctx.lineWidth = 3;
          ctx.setLineDash([]);
        } else if (isExplored) {
          ctx.strokeStyle = "#60a5fa";
          ctx.lineWidth = 2;
          ctx.setLineDash([]);
        } else if (exploredSet.has(node.id) || exploredSet.has(targetId)) {
          ctx.strokeStyle = "#9ca3af";
          ctx.lineWidth = 1.5;
          ctx.setLineDash([5, 5]);
        } else {
          ctx.strokeStyle = "#4b5563";
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 7]);
        }

        ctx.stroke();
        ctx.setLineDash([]);
      });
    });

    // Draw nodes
    nodes.forEach((node) => {
      const color = getNodeColor(node);
      const isCurrent = node.id === current_node_id;

      // Node shadow/glow
      if (isCurrent) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_RADIUS + 8, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(74, 222, 128, 0.3)";
        ctx.fill();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, NODE_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // Node border
      ctx.beginPath();
      ctx.arc(node.x, node.y, NODE_RADIUS, 0, Math.PI * 2);
      ctx.strokeStyle = isCurrent ? "#22c55e" : "#374151";
      ctx.lineWidth = isCurrent ? 4 : 2;
      ctx.stroke();

      // Node label (name)
      ctx.font = isCurrent ? "bold 12px sans-serif" : "11px sans-serif";
      ctx.fillStyle = isCurrent ? "#4ade80" : "#e5e7eb";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      // Draw text with background for readability
      const text = node.name.length > 8 ? node.name.slice(0, 7) + "…" : node.name;
      const textY = node.y + NODE_RADIUS + 15;

      ctx.fillText(text, node.x, textY);

      // Current node indicator
      if (isCurrent) {
        ctx.font = "10px sans-serif";
        ctx.fillStyle = "#4ade80";
        ctx.fillText("★ 当前位置", node.x, textY + 14);
      }
    });
  }, [mapData]);

  // Handle mouse move for hover effects
  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || !mapData) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setMousePos({ x: e.clientX, y: e.clientY });

    // Check if hovering over a node
    let hovered: MapNode | null = null;
    for (const node of mapData.nodes) {
      const dx = x - node.x;
      const dy = y - node.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      if (distance <= NODE_RADIUS + 5) {
        hovered = node;
        break;
      }
    }
    setHoveredNode(hovered);
  };

  if (!isOpen) return null;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <h2 style={titleStyle}>
            <span>🗺️</span>
            世界地图
          </h2>
          <button
            style={closeBtnStyle}
            onClick={onClose}
            title="关闭地图"
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = "#374151";
              e.currentTarget.style.color = "#fff";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
              e.currentTarget.style.color = "#9ca3af";
            }}
          >
            ✕
          </button>
        </div>

        <div style={contentStyle}>
          {loading ? (
            <div style={loadingStyle}>
              <div style={spinnerStyle} />
              <span>加载地图数据…</span>
            </div>
          ) : !mapData ? (
            <div style={emptyStyle}>
              <span style={{ fontSize: "48px" }}>🗺️</span>
              <p>暂无地图数据</p>
              <p style={{ fontSize: "12px", opacity: 0.7 }}>
                开始冒险后地图将自动更新
              </p>
            </div>
          ) : (
            <>
              <div style={legendStyle}>
                <div style={legendItemStyle}>
                  <span style={legendDotStyle("#4ade80")} />
                  <span>当前位置</span>
                </div>
                <div style={legendItemStyle}>
                  <span style={legendDotStyle("#60a5fa")} />
                  <span>已探索</span>
                </div>
                <div style={legendItemStyle}>
                  <span style={legendDotStyle("#fbbf24")} />
                  <span>可到达</span>
                </div>
                <div style={legendItemStyle}>
                  <span style={legendDotStyle("#6b7280")} />
                  <span>未探索</span>
                </div>
              </div>

              <div style={canvasContainerStyle}>
                <canvas
                  ref={canvasRef}
                  width={CANVAS_WIDTH}
                  height={CANVAS_HEIGHT}
                  onMouseMove={handleMouseMove}
                  onMouseLeave={() => setHoveredNode(null)}
                  style={canvasStyle}
                />

                {hoveredNode && (
                  <div style={tooltipStyle(mousePos.x, mousePos.y)}>
                    <div style={tooltipTitleStyle}>{hoveredNode.name}</div>
                    {hoveredNode.description && (
                      <div style={tooltipDescStyle}>{hoveredNode.description}</div>
                    )}
                    <div style={tooltipStatusStyle}>
                      {hoveredNode.id === mapData.current_node_id
                        ? "📍 当前位置"
                        : mapData.explored_node_ids.includes(hoveredNode.id)
                        ? "✓ 已探索"
                        : "? 未探索"}
                    </div>
                  </div>
                )}
              </div>

              <div style={statsStyle}>
                <span>
                  已探索: {mapData.explored_node_ids.length} / {mapData.nodes.length} 区域
                </span>
                <span style={currentLocationStyle}>
                  📍 当前:{" "}
                  {mapData.nodes.find((n) => n.id === mapData.current_node_id)
                    ?.name || "未知"}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
