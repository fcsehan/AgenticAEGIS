import { create } from "zustand";
import type { DomainVersion } from "@/types/domain";

interface GovernanceState {
  versions: Record<string, DomainVersion[]>;

  addVersion: (domainId: string, version: DomainVersion) => void;
  getVersions: (domainId: string) => DomainVersion[];
}

export const useGovernanceStore = create<GovernanceState>((set, get) => ({
  versions: {
    "ia-mission": [
      {
        id: "v1",
        version: "1.0.0",
        status: "Published",
        author: "MELD Loader",
        timestamp: "2026-03-20T10:00:00Z",
        changeLog:
          "Initial load from IAMissionObligationVocabMt.meld — 9 MissionSupportRoles, 8 JointStaffResponsibilityTypes (J1–J6 + PersonalStaff + SpecialStaff), 22 obligation rules derived from DASSA Cyber C2 spec v0.9",
      },
    ],
  },

  addVersion: (domainId, version) =>
    set((s) => ({
      versions: {
        ...s.versions,
        [domainId]: [version, ...(s.versions[domainId] ?? [])],
      },
    })),

  getVersions: (domainId) => get().versions[domainId] ?? [],
}));
