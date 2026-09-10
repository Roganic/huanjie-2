import { useState } from "react";
import type { Module, ModuleScene, ModuleNPC, ModuleQuest, ActiveModuleState } from "../types/module";
import "./ModulePanel.css";
import { defaultArt, builtinArt, sceneCategory } from '../game/visuals';

function Cover({ module }: { module: Module }) {
  const fallback = builtinArt(module.cover_builtin, module.illustrated !== false) || defaultArt(module.cover_fallback || sceneCategory(module.name), module.illustrated !== false);
  const src = module.cover_image && /^data:image\/(png|jpeg);base64,/.test(module.cover_image) ? module.cover_image : fallback;
  return <img className="module-cover" src={src} alt="" style={{ objectPosition: module.cover_position || '50% 50%' }} onError={e => { if (e.currentTarget.getAttribute('src') !== fallback) e.currentTarget.src = fallback; }} />;
}

interface ModulePanelProps {
  modules: Module[];
  activeModule: ActiveModuleState | null;
  onActivateModule: (moduleId: string) => Promise<void>;
  onClose: () => void;
  loading: boolean;
}

type ViewMode = "list" | "detail";

function SceneItem({ scene }: { scene: ModuleScene }) {
  return (
    <div className="module-detail-item">
      <div className="module-detail-item-name">📍 {scene.name}</div>
      <div className="module-detail-item-desc">{scene.description}</div>
    </div>
  );
}

function NPCItem({ npc }: { npc: ModuleNPC }) {
  const typeIcon = npc.type === "friendly" ? "😊" : npc.type === "hostile" ? "😈" : "😐";
  const typeClass = `npc-type-${npc.type}`;
  
  return (
    <div className={`module-detail-item ${typeClass}`}>
      <div className="module-detail-item-name">
        {typeIcon} {npc.name}
        {npc.role && <span className="npc-role-badge">{npc.role}</span>}
      </div>
      <div className="module-detail-item-desc">{npc.description}</div>
    </div>
  );
}

function QuestItem({ quest }: { quest: ModuleQuest }) {
  return (
    <div className={`module-detail-item ${quest.is_main ? "quest-main" : "quest-side"}`}>
      <div className="module-detail-item-name">
        {quest.is_main ? "📜" : "📋"} {quest.name}
        {quest.is_main && <span className="quest-main-badge">主线</span>}
      </div>
      <div className="module-detail-item-desc">{quest.description}</div>
      {quest.objectives.length > 0 && (
        <div className="quest-objectives">
          <div className="quest-objectives-label">目标:</div>
          <ul>
            {quest.objectives.map((obj, idx) => (
              <li key={idx}>{obj}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function ModulePanel({
  modules,
  activeModule,
  onActivateModule,
  onClose,
  loading,
}: ModulePanelProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [selectedModule, setSelectedModule] = useState<Module | null>(null);
  const [activating, setActivating] = useState(false);
  const [activationError, setActivationError] = useState("");
  const [activeTab, setActiveTab] = useState<"scenes" | "npcs" | "quests">("scenes");

  const handleModuleClick = (module: Module) => {
    setSelectedModule(module);
    setViewMode("detail");
    setActiveTab("scenes");
  };

  const handleBackToList = () => {
    setViewMode("list");
    setSelectedModule(null);
  };

  const handleActivate = async () => {
    if (!selectedModule) return;
    setActivating(true);
    setActivationError("");
    try {
      await onActivateModule(selectedModule.id);
    } catch (error) {
      setActivationError(error instanceof Error ? error.message : "未能开始冒险，请重试。");
    } finally {
      setActivating(false);
    }
  };

  const isModuleActive = selectedModule?.status === "active";

  if (viewMode === "detail" && selectedModule) {
    return (
      <div className="module-panel">
        {activationError && <p role="status">{activationError}</p>}
        <div className="module-panel-header">
          <button className="module-back-btn" onClick={handleBackToList}>
            ← 返回列表
          </button>
          <h2 className="module-panel-title">模组详情</h2>
          <button className="module-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="module-detail-header">
          <Cover module={selectedModule} />
          <div className="module-detail-info">
            <h3 className="module-detail-name">{selectedModule.name}</h3>
            <div className="module-detail-meta">
              {selectedModule.author && <span>作者: {selectedModule.author}</span>}
              {selectedModule.version && <span>版本: {selectedModule.version}</span>}
            </div>
            <div className={`module-status-badge ${selectedModule.status}`}>
              {selectedModule.status === "active" ? "🟢 已激活" : 
               selectedModule.status === "completed" ? "✅ 已完成" : "⚪ 未激活"}
            </div>
          </div>
        </div>

        <div className="module-detail-description">
          {selectedModule.description}
        </div>

        <div className="module-detail-stats">
          <div className="module-stat">
            <span className="module-stat-value">{selectedModule.scenes.length}</span>
            <span className="module-stat-label">场景</span>
          </div>
          <div className="module-stat">
            <span className="module-stat-value">{selectedModule.npcs.length}</span>
            <span className="module-stat-label">NPC</span>
          </div>
          <div className="module-stat">
            <span className="module-stat-value">{selectedModule.quests.length}</span>
            <span className="module-stat-label">任务</span>
          </div>
        </div>

        <div className="module-detail-tabs">
          <button
            className={`module-tab ${activeTab === "scenes" ? "active" : ""}`}
            onClick={() => setActiveTab("scenes")}
          >
            📍 场景 ({selectedModule.scenes.length})
          </button>
          <button
            className={`module-tab ${activeTab === "npcs" ? "active" : ""}`}
            onClick={() => setActiveTab("npcs")}
          >
            👥 NPC ({selectedModule.npcs.length})
          </button>
          <button
            className={`module-tab ${activeTab === "quests" ? "active" : ""}`}
            onClick={() => setActiveTab("quests")}
          >
            📜 任务 ({selectedModule.quests.length})
          </button>
        </div>

        <div className="module-detail-content">
          {activeTab === "scenes" && (
            <div className="module-detail-list">
              {selectedModule.scenes.length > 0 ? (
                selectedModule.scenes.map((scene) => (
                  <SceneItem key={scene.id} scene={scene} />
                ))
              ) : (
                <div className="module-empty-state">暂无场景数据</div>
              )}
            </div>
          )}
          {activeTab === "npcs" && (
            <div className="module-detail-list">
              {selectedModule.npcs.length > 0 ? (
                selectedModule.npcs.map((npc) => (
                  <NPCItem key={npc.id} npc={npc} />
                ))
              ) : (
                <div className="module-empty-state">暂无 NPC 数据</div>
              )}
            </div>
          )}
          {activeTab === "quests" && (
            <div className="module-detail-list">
              {selectedModule.quests.length > 0 ? (
                selectedModule.quests.map((quest) => (
                  <QuestItem key={quest.id} quest={quest} />
                ))
              ) : (
                <div className="module-empty-state">暂无任务数据</div>
              )}
            </div>
          )}
        </div>

        <p>开始新冒险会使用这里展示的版本，以当前角色的姓名与职业重新创建 1 级角色。原冒险和存档保留，已有进度不会自动套用新版故事。</p>
        <div className="module-detail-actions">
            <button
              className="module-activate-btn"
              onClick={handleActivate}
              disabled={activating || loading}
            >
              {activating ? "准备新冒险…" : isModuleActive ? "以最新内容开始新冒险" : "以此模组开始新冒险"}
            </button>
        </div>
      </div>
    );
  }

  // List view
  return (
    <div className="module-panel">
      <div className="module-panel-header">
        <h2 className="module-panel-title">📦 模组管理</h2>
        <button className="module-close-btn" onClick={onClose}>✕</button>
      </div>

      {activeModule && (
        <div className="module-active-section">
          <div className="module-active-header">
            <span className="module-active-icon">🎮</span>
            <span className="module-active-title">当前激活模组</span>
          </div>
          <div className="module-active-name">{activeModule.module_name}</div>
          <div className="module-active-node">
            <span className="node-label">剧情节点:</span>
            <span className="node-value">{activeModule.current_story_node}</span>
          </div>
        </div>
      )}

      <div className="module-list">
        {loading ? (
          <div className="module-loading">加载中…</div>
        ) : modules.length === 0 ? (
          <div className="module-empty-state">
            <div className="module-empty-icon">📭</div>
            <div className="module-empty-text">暂无可用模组</div>
          </div>
        ) : (
          modules.map((module) => (
            <div
              key={module.id}
              className={`module-card ${module.status}`}
              role="button"
              tabIndex={0}
              onClick={() => handleModuleClick(module)}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); handleModuleClick(module); } }}
            >
              <div className="module-card-header">
                <Cover module={module} />
                <div className="module-card-name">{module.name}</div>
                <div className={`module-card-status ${module.status}`}>
                  {module.status === "active" ? "●" : module.status === "completed" ? "✓" : "○"}
                </div>
              </div>
              <div className="module-card-desc">{module.description}</div>
              <div className="module-card-stats">
                <span>📍 {module.scenes.length}</span>
                <span>👥 {module.npcs.length}</span>
                <span>📜 {module.quests.length}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
