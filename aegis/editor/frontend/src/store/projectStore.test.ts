import { useProjectStore } from "./projectStore";
import type { Project } from "@/types/domain";

const testProject: Project = {
  path: "/test/path",
  name: "TestProject",
  meldFiles: [],
  domains: [],
  loadedAt: new Date().toISOString(),
};

beforeEach(() => {
  useProjectStore.setState({ project: null, loading: false, error: null });
});

describe("projectStore", () => {
  it("starts with no project loaded", () => {
    const state = useProjectStore.getState();
    expect(state.project).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  it("setProject stores the project and clears loading/error", () => {
    useProjectStore.getState().setLoading(true);
    useProjectStore.getState().setProject(testProject);
    const state = useProjectStore.getState();
    expect(state.project?.name).toBe("TestProject");
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  it("setLoading sets loading state and clears error", () => {
    useProjectStore.getState().setError("previous error");
    useProjectStore.getState().setLoading(true);
    expect(useProjectStore.getState().loading).toBe(true);
    expect(useProjectStore.getState().error).toBeNull();
  });

  it("setError stores error message and clears loading", () => {
    useProjectStore.getState().setLoading(true);
    useProjectStore.getState().setError("something went wrong");
    expect(useProjectStore.getState().error).toBe("something went wrong");
    expect(useProjectStore.getState().loading).toBe(false);
  });

  it("closeProject resets everything", () => {
    useProjectStore.getState().setProject(testProject);
    useProjectStore.getState().closeProject();
    const state = useProjectStore.getState();
    expect(state.project).toBeNull();
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });
});
