import { useEffect, useState, useCallback } from "react";
import "./MapPanel.css";

interface MapNode {
  id: string;
  name: string;
  description: string;
  exits: { direction: string; target_scene_id: string }[];
}

interface MapConnection {
  from_node: string;
  to_node: string;
  direction: string;
}

interface MapData {
  current_node: string;
  nodes: MapNode[];
  connections: MapConnection[];
  explored_nodes: string[];
}

interface MapPanelProps {
  apiUrl: (path: string) => string;
  sessionId: string | null;
  buildSessionHeaders: (sessionId?: string | null, extraHeaders?: HeadersInit) => HeadersInit;
  currentSceneId: string;
  isVisible: boolean;
  onClose: () => void;
}

export function MapPanel({
  apiUrl,
  sessionId,
  buildSessionHeaders,
  currentSceneId,
  isVisible,
  onClose,
}: MapPanelProps) {
  const [mapData, setMapData] = useState<MapData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMapData = useCallback(async () => {
    if (!isVisible) return;

    // Only show loading spinner if we have no data yet (first load)
    if (!mapData) setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/map"), {
        headers: buildSessionHeaders(sessionId),
      });
      if (!response.ok) {
        throw new Error(`获取地图数据失败 (${response.status})`);
      }
      const data: MapData = await response.json();
      setMapData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [apiUrl, sessionId, buildSessionHeaders, isVisible]);

  // Fetch map data when panel becomes visible
  useEffect(() => {
    if (isVisible) {
      fetchMapData();
    }
  }, [isVisible, fetchMapData]);

  // Refresh map data when current scene changes
  useEffect(() => {
    if (isVisible && mapData && currentSceneId !== mapData.current_node) {
      fetchMapData();
    }
  }, [currentSceneId, isVisible, mapData, fetchMapData]);

  if (!isVisible) return null;

  const isNodeExplored = (nodeId: string) => {
    if (!mapData) return false;
    return mapData.explored_nodes.includes(nodeId);
  };

  const isCurrentNode = (nodeId: string) => {
    return nodeId === currentSceneId;
  };

  const getConnectedNodes = (nodeId: string) => {
    if (!mapData) return [];
    return mapData.connections
      .filter((conn) => conn.from_node === nodeId)
      .map((conn) => ({
        node: mapData.nodes.find((n) => n.id === conn.to_node),
        direction: conn.direction,
      }))
      .filter((item) => item.node !== undefined) as {
      node: MapNode;
      direction: string;
    }[];
  };

  return (
    <div className="map-panel-overlay" onClick={onClose}>
      <div className="map-panel" onClick={(e) => e.stopPropagation()}>
        <div className="map-panel-header">
          <h2 className="map-panel-title">🗺️ 地图</h2>
          <button className="map-panel-close" onClick={onClose} title="关闭">
            ✕
          </button>
        </div>

        <div className="map-panel-content">
          {loading && (
            <div className="map-loading">
              <span className="map-loading-spinner">🗺️</span>
              <span>加载地图中...</span>
            </div>
          )}

          {error && (
            <div className="map-error">
              <span className="map-error-icon">⚠️</span>
              <span>{error}</span>
              <button className="map-retry-btn" onClick={fetchMapData}>
                重试
              </button>
            </div>
          )}

          {!loading && !error && mapData && (
            <div className="map-container">
              {/* Current Location */}
              <div className="map-current-location">
                <span className="map-current-label">当前位置</span>
                <span className="map-current-name">
                  {mapData.nodes.find((n) => n.id === mapData.current_node)?.name || "未知区域"}
                </span>
              </div>

              {/* Node List */}
              <div className="map-nodes-section">
                <h3 className="map-section-title">已探索区域</h3>
                <div className="map-nodes-list">
                  {mapData.nodes.map((node) => {
                    const explored = isNodeExplored(node.id);
                    const current = isCurrentNode(node.id);
                    const connected = getConnectedNodes(node.id);

                    return (
                      <div
                        key={node.id}
                        className={`map-node ${explored ? "explored" : "unexplored"} ${
                          current ? "current" : ""
                        }`}
                        data-testid={`map-node-${node.id}`}
                      >
                        <div className="map-node-header">
                          <span className="map-node-icon">
                            {current ? "📍" : explored ? "🗺️" : "❓"}
                          </span>
                          <span className="map-node-name">
                            {explored ? node.name : "未探索区域"}
                          </span>
                          {current && <span className="map-node-badge current">当前</span>}
                          {explored && !current && (
                            <span className="map-node-badge explored">已探索</span>
                          )}
                        </div>

                        {explored && (
                          <>
                            <p className="map-node-description">{node.description}</p>

                            {connected.length > 0 && (
                              <div className="map-node-exits">
                                <span className="map-exits-label">出口:</span>
                                <div className="map-exits-list">
                                  {connected.map(({ node: targetNode, direction }) => (
                                    <span
                                      key={`${node.id}-${direction}`}
                                      className={`map-exit-tag ${
                                        isNodeExplored(targetNode.id) ? "explored" : "unexplored"
                                      }`}
                                    >
                                      {direction} →{" "}
                                      {isNodeExplored(targetNode.id)
                                        ? targetNode.name
                                        : "???"}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Legend */}
              <div className="map-legend">
                <h3 className="map-section-title">图例</h3>
                <div className="map-legend-items">
                  <div className="map-legend-item">
                    <span className="map-legend-icon">📍</span>
                    <span>当前位置</span>
                  </div>
                  <div className="map-legend-item">
                    <span className="map-legend-icon">🗺️</span>
                    <span>已探索</span>
                  </div>
                  <div className="map-legend-item">
                    <span className="map-legend-icon">❓</span>
                    <span>未探索</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default MapPanel;
