import { create } from "zustand";

export type Panel =
  | "sources"
  | "test"
  | "structure"
  | "rules"
  | "graph"
  | "governance"
  | "validation";

interface UiState {
  activePanel: Panel;
  selectedRuleId: string | null;
  selectedRoleId: string | null;
  sidebarOpen: boolean;
  ruleEditorOpen: boolean;

  setActivePanel: (panel: Panel) => void;
  setSelectedRule: (id: string | null) => void;
  setSelectedRole: (id: string | null) => void;
  toggleSidebar: () => void;
  setRuleEditorOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activePanel: "structure",
  selectedRuleId: null,
  selectedRoleId: null,
  sidebarOpen: true,
  ruleEditorOpen: false,

  setActivePanel: (panel) => set({ activePanel: panel }),
  setSelectedRule: (id) => set({ selectedRuleId: id }),
  setSelectedRole: (id) => set({ selectedRoleId: id }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  setRuleEditorOpen: (open) => set({ ruleEditorOpen: open }),
}));
