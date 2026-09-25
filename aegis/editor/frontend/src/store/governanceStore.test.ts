import { useGovernanceStore } from "./governanceStore";
import type { DomainVersion } from "@/types/domain";

describe("governanceStore", () => {
  it("has pre-seeded versions for ia-mission", () => {
    const versions = useGovernanceStore.getState().getVersions("ia-mission");
    expect(versions.length).toBeGreaterThan(0);
    expect(versions[0]!.version).toBe("1.0.0");
  });

  it("returns empty array for unknown domain", () => {
    expect(useGovernanceStore.getState().getVersions("nonexistent")).toEqual([]);
  });

  it("addVersion prepends to the list", () => {
    const newVersion: DomainVersion = {
      id: "v-new",
      version: "2.0.0",
      status: "Published",
      author: "Test",
      timestamp: new Date().toISOString(),
      changeLog: "Major update",
    };
    useGovernanceStore.getState().addVersion("ia-mission", newVersion);
    const versions = useGovernanceStore.getState().getVersions("ia-mission");
    expect(versions[0]!.id).toBe("v-new");
    expect(versions[0]!.version).toBe("2.0.0");
  });

  it("addVersion creates new entry for new domain", () => {
    const newVersion: DomainVersion = {
      id: "v1",
      version: "1.0.0",
      status: "Published",
      author: "Test",
      timestamp: new Date().toISOString(),
      changeLog: "First version",
    };
    useGovernanceStore.getState().addVersion("new-domain", newVersion);
    const versions = useGovernanceStore.getState().getVersions("new-domain");
    expect(versions).toHaveLength(1);
  });
});
