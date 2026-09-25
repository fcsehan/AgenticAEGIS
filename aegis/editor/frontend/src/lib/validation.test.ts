import { validateDomain } from "./validation";
import type { Domain } from "@/types/domain";

/** Minimal valid domain factory. */
function makeDomain(overrides: Partial<Domain> = {}): Domain {
  return {
    id: "test",
    name: "Test Domain",
    description: "",
    status: "Draft",
    roles: [{ id: "r1", name: "Agent", description: "", ruleCount: 0 }],
    obligationTypes: [],
    codes: [{ id: "c1", name: "Code A", description: "", prevalence: 1 }],
    rules: [],
    conflictCount: 0,
    lastModified: new Date().toISOString(),
    ...overrides,
  };
}

describe("validateDomain", () => {
  it("returns no issues for a valid domain with no rules", () => {
    const domain = makeDomain();
    expect(validateDomain(domain)).toEqual([]);
  });

  it("returns no issues when all rule references are valid", () => {
    const domain = makeDomain({
      rules: [
        {
          id: "n1",
          code: "c1",
          agentRole: "Agent",
          modality: "FORBIDDEN",
          proposition: "do-harm",
          specificity: 1,
          defeasible: false,
        },
      ],
    });
    expect(validateDomain(domain)).toEqual([]);
  });

  describe("symbol validation", () => {
    it("flags undeclared agent role", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "NonExistentRole",
            modality: "FORBIDDEN",
            proposition: "do-harm",
            specificity: 1,
            defeasible: false,
          },
        ],
      });
      const issues = validateDomain(domain);
      expect(issues).toHaveLength(1);
      expect(issues[0]!.severity).toBe("error");
      expect(issues[0]!.message).toContain("NonExistentRole");
      expect(issues[0]!.ruleId).toBe("n1");
    });

    it("flags undeclared code reference", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "nonexistent-code",
            agentRole: "Agent",
            modality: "OBLIGATORY",
            proposition: "report",
            specificity: 1,
            defeasible: false,
          },
        ],
      });
      const issues = validateDomain(domain);
      expect(issues).toHaveLength(1);
      expect(issues[0]!.severity).toBe("error");
      expect(issues[0]!.message).toContain("nonexistent-code");
    });

    it("provides typo suggestion when role name is close (edit distance ≤ 2)", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agnet", // typo for "Agent"
            modality: "FORBIDDEN",
            proposition: "do-harm",
            specificity: 1,
            defeasible: false,
          },
        ],
      });
      const issues = validateDomain(domain);
      expect(issues).toHaveLength(1);
      expect(issues[0]!.suggestion).toContain("Agent");
    });

    it("does not suggest when role name is too far away", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "CompletelyDifferent",
            modality: "FORBIDDEN",
            proposition: "do-harm",
            specificity: 1,
            defeasible: false,
          },
        ],
      });
      const issues = validateDomain(domain);
      expect(issues).toHaveLength(1);
      expect(issues[0]!.suggestion).toBeUndefined();
    });

    it("reports both role and code errors on the same rule", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "bad-code",
            agentRole: "BadRole",
            modality: "PERMITTED",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const issues = validateDomain(domain);
      const errors = issues.filter((i) => i.severity === "error");
      expect(errors).toHaveLength(2);
    });
  });

  describe("conflict detection", () => {
    it("detects conflict: same role + same proposition + different modality", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent",
            modality: "OBLIGATORY",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const issues = validateDomain(domain);
      const conflicts = issues.filter((i) => i.severity === "warning");
      expect(conflicts).toHaveLength(1);
      expect(conflicts[0]!.ruleId).toBe("n1");
      expect(conflicts[0]!.relatedRuleId).toBe("n2");
      expect(conflicts[0]!.message).toContain("FORBIDDEN");
      expect(conflicts[0]!.message).toContain("OBLIGATORY");
    });

    it("does not flag rules with same modality as conflict", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 2,
            defeasible: true,
          },
        ],
      });
      const conflicts = validateDomain(domain).filter((i) => i.severity === "warning");
      expect(conflicts).toHaveLength(0);
    });

    it("does not flag rules with different propositions as conflict", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act-a",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent",
            modality: "OBLIGATORY",
            proposition: "act-b",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const conflicts = validateDomain(domain).filter((i) => i.severity === "warning");
      expect(conflicts).toHaveLength(0);
    });

    it("does not flag rules with different roles as conflict", () => {
      const domain = makeDomain({
        roles: [
          { id: "r1", name: "Agent A", description: "", ruleCount: 0 },
          { id: "r2", name: "Agent B", description: "", ruleCount: 0 },
        ],
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent A",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent B",
            modality: "OBLIGATORY",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const conflicts = validateDomain(domain).filter((i) => i.severity === "warning");
      expect(conflicts).toHaveLength(0);
    });

    it("detects multiple conflicts in a three-way clash", () => {
      const domain = makeDomain({
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent",
            modality: "OBLIGATORY",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
          {
            id: "n3",
            code: "c1",
            agentRole: "Agent",
            modality: "PERMITTED",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const conflicts = validateDomain(domain).filter((i) => i.severity === "warning");
      // 3 rules with pairwise different modalities = 3 conflicts (n1-n2, n1-n3, n2-n3)
      expect(conflicts).toHaveLength(3);
    });
  });

  describe("combined validation", () => {
    it("reports both symbol errors and conflicts together", () => {
      const domain = makeDomain({
        roles: [
          { id: "r1", name: "Agent", description: "", ruleCount: 0 },
        ],
        rules: [
          {
            id: "n1",
            code: "c1",
            agentRole: "Agent",
            modality: "FORBIDDEN",
            proposition: "act",
            specificity: 1,
            defeasible: false,
          },
          {
            id: "n2",
            code: "c1",
            agentRole: "Agent",
            modality: "OBLIGATORY",
            proposition: "act",
            specificity: 1,
            defeasible: true,
          },
          {
            id: "n3",
            code: "bad-code",
            agentRole: "BadRole",
            modality: "PERMITTED",
            proposition: "other",
            specificity: 1,
            defeasible: true,
          },
        ],
      });
      const issues = validateDomain(domain);
      const errors = issues.filter((i) => i.severity === "error");
      const warnings = issues.filter((i) => i.severity === "warning");
      expect(errors.length).toBeGreaterThanOrEqual(2); // bad role + bad code
      expect(warnings.length).toBeGreaterThanOrEqual(1); // n1 vs n2
    });
  });
});
