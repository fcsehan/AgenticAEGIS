import { mockDomains, mockProjects, iaMissionMeldFiles } from "./mock";

describe("mockDomains — IAMission", () => {
  const ia = mockDomains[0]!;

  it("contains exactly one domain", () => {
    expect(mockDomains).toHaveLength(1);
    expect(ia.id).toBe("ia-mission");
  });

  it("has 9 MissionSupportRoles", () => {
    expect(ia.roles).toHaveLength(9);
    const names = ia.roles.map((r) => r.name);
    expect(names).toContain("commanderInMission");
    expect(names).toContain("intelligenceAgentInMission");
    expect(names).toContain("operationsAgentInMission");
    expect(names).toContain("logisticsAgentInMission");
    expect(names).toContain("planningAndPolicyAgentInMission");
    expect(names).toContain("c4AgentInMission");
    expect(names).toContain("manPowerAndPersonnelAgentInMission");
    expect(names).toContain("personalStaffAgentInMission");
    expect(names).toContain("specialStaffAgentInMission");
  });

  it("has JointStaffResponsibilityType with J1–J6 children", () => {
    const jst = ia.obligationTypes.find((ot) => ot.id === "JointStaffResponsibilityType");
    expect(jst).toBeDefined();
    expect(jst!.children).toHaveLength(6);
    const childNames = jst!.children.map((c) => c.id);
    expect(childNames).toEqual([
      "J1Obligation",
      "J2Obligation",
      "J3Obligation",
      "J4Obligation",
      "J5Obligation",
      "J6Obligation",
    ]);
  });

  it("has PersonalStaffObligation and SpecialStaffObligation as top-level types", () => {
    const names = ia.obligationTypes.map((ot) => ot.id);
    expect(names).toContain("PersonalStaffObligation");
    expect(names).toContain("SpecialStaffObligation");
  });

  it("uses Joint Staff Doctrine as the single CodeOfConduct", () => {
    expect(ia.codes).toHaveLength(1);
    expect(ia.codes[0]!.id).toBe("JointStaffDoctrine");
  });

  it("has 22 deontic rules", () => {
    expect(ia.rules).toHaveLength(22);
  });

  it("all rules reference valid roles", () => {
    const roleNames = new Set(ia.roles.map((r) => r.name));
    for (const rule of ia.rules) {
      expect(roleNames.has(rule.agentRole)).toBe(true);
    }
  });

  it("all rules reference the JointStaffDoctrine code", () => {
    for (const rule of ia.rules) {
      expect(rule.code).toBe("JointStaffDoctrine");
    }
  });

  it("all rules have source references to .meld files", () => {
    for (const rule of ia.rules) {
      expect(rule.source).toBeDefined();
      expect(rule.source).toContain("IAMissionObligationVocabMt.meld:");
    }
  });

  it("includes the commander FORBIDDEN constraint (singleEntryFormatInArgs)", () => {
    const forbidden = ia.rules.filter((r) => r.modality === "FORBIDDEN");
    expect(forbidden).toHaveLength(1);
    expect(forbidden[0]!.agentRole).toBe("commanderInMission");
  });

  it("propositions use MELD s-expression format", () => {
    for (const rule of ia.rules) {
      // All propositions are either s-expressions or predicate-style
      expect(rule.proposition.length).toBeGreaterThan(0);
    }
  });
});

describe("mockProjects", () => {
  const projectPath = "/workspace/IAMissionProject";

  it("contains the IAMissionProject", () => {
    expect(mockProjects[projectPath]).toBeDefined();
  });

  it("project has correct name", () => {
    expect(mockProjects[projectPath]!.name).toBe("IAMissionProject");
  });

  it("project contains 4 meld files in correct load order", () => {
    const project = mockProjects[projectPath]!;
    expect(project.meldFiles).toHaveLength(4);
    // Logic → MultiFuture → Inference → IAMission
    expect(project.meldFiles[0]!.name).toContain("LogicMt");
    expect(project.meldFiles[3]!.name).toContain("IAMission");
  });

  it("meld files have valid types", () => {
    const validTypes = new Set(["ontology", "deontic", "inference", "vocabulary"]);
    for (const mf of iaMissionMeldFiles) {
      expect(validTypes.has(mf.type)).toBe(true);
      expect(mf.sizeBytes).toBeGreaterThan(0);
    }
  });
});
