// Module Types for 幻界 Dashboard

export interface ModuleScene {
  id: string;
  name: string;
  description: string;
}

export interface ModuleNPC {
  id: string;
  name: string;
  description: string;
  type: "friendly" | "neutral" | "hostile";
  role?: string;
}

export interface ModuleQuest {
  id: string;
  name: string;
  description: string;
  objectives: string[];
  is_main: boolean;
}

export interface Module {
  id: string;
  name: string;
  description: string;
  author?: string;
  version?: string;
  status: "inactive" | "active" | "completed";
  scenes: ModuleScene[];
  npcs: ModuleNPC[];
  quests: ModuleQuest[];
  cover_builtin?: string | null;
  cover_image?: string;
  cover_fallback?: import('../game/visuals').ArtCategory | null;
  illustrated?: boolean;
  cover_position?: string;
  created_at?: string;
}

export interface ActiveModuleState {
  module_id: string;
  module_name: string;
  current_story_node: string;
  current_story_description: string;
  active_quests: ActiveQuest[];
  completed_quests: string[];
}

export interface ActiveQuest {
  quest_id: string;
  quest_name: string;
  current_objective: string;
  is_main: boolean;
}

export interface ModulesResponse {
  modules: Module[];
  active_module: ActiveModuleState | null;
}

export interface ModuleDetailResponse {
  module: Module;
}

export interface ActivateModuleRequest {
  module_id: string;
}

export interface ActivateModuleResponse {
  success: boolean;
  active_module: ActiveModuleState;
  message?: string;
}
