import { create } from "zustand";
import type { Project } from "@/types/domain";

interface ProjectState {
  project: Project | null;
  loading: boolean;
  error: string | null;

  setProject: (project: Project) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  closeProject: () => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  project: null,
  loading: false,
  error: null,

  setProject: (project) => set({ project, loading: false, error: null }),
  setLoading: (loading) => set({ loading, error: null }),
  setError: (error) => set({ error, loading: false }),
  closeProject: () => set({ project: null, loading: false, error: null }),
}));
