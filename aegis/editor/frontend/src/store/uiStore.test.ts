import { useUiStore } from "./uiStore";

beforeEach(() => {
  useUiStore.setState({
    activePanel: "structure",
    selectedRuleId: null,
    selectedRoleId: null,
    sidebarOpen: true,
    ruleEditorOpen: false,
  });
});

describe("uiStore", () => {
  it("has correct defaults", () => {
    const state = useUiStore.getState();
    expect(state.activePanel).toBe("structure");
    expect(state.sidebarOpen).toBe(true);
  });

  it("setActivePanel changes panel", () => {
    useUiStore.getState().setActivePanel("graph");
    expect(useUiStore.getState().activePanel).toBe("graph");
  });

  it("toggleSidebar flips open/closed", () => {
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarOpen).toBe(false);
    useUiStore.getState().toggleSidebar();
    expect(useUiStore.getState().sidebarOpen).toBe(true);
  });


  it("setSelectedRule updates selection", () => {
    useUiStore.getState().setSelectedRule("n1");
    expect(useUiStore.getState().selectedRuleId).toBe("n1");
    useUiStore.getState().setSelectedRule(null);
    expect(useUiStore.getState().selectedRuleId).toBeNull();
  });

  it("setRuleEditorOpen controls rule editor visibility", () => {
    useUiStore.getState().setRuleEditorOpen(true);
    expect(useUiStore.getState().ruleEditorOpen).toBe(true);
  });
});
