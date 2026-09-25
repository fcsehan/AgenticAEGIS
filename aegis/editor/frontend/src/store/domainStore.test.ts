import { useDomainStore } from "./domainStore";
import type { Domain, NormFrame, Role, ObligationType, CodeOfConduct } from "@/types/domain";

function makeDomain(id = "d1"): Domain {
  return {
    id,
    name: "Test",
    description: "",
    status: "Draft",
    roles: [],
    obligationTypes: [],
    codes: [],
    rules: [],
    conflictCount: 0,
    lastModified: new Date().toISOString(),
  };
}

function makeRule(id = "n1"): NormFrame {
  return {
    id,
    code: "c1",
    agentRole: "Agent",
    modality: "FORBIDDEN",
    proposition: "do-harm",
    specificity: 1,
    defeasible: false,
  };
}

function makeRole(id = "r1"): Role {
  return { id, name: "Agent", description: "Test agent", ruleCount: 0 };
}

beforeEach(() => {
  useDomainStore.setState({ domains: [], activeDomainId: null });
});

describe("domainStore", () => {
  describe("domain CRUD", () => {
    it("starts with empty domains", () => {
      expect(useDomainStore.getState().domains).toEqual([]);
    });

    it("setDomains replaces entire domain list", () => {
      const d = makeDomain();
      useDomainStore.getState().setDomains([d]);
      expect(useDomainStore.getState().domains).toHaveLength(1);
      expect(useDomainStore.getState().domains[0]!.id).toBe("d1");
    });

    it("addDomain appends a new domain", () => {
      useDomainStore.getState().addDomain(makeDomain("d1"));
      useDomainStore.getState().addDomain(makeDomain("d2"));
      expect(useDomainStore.getState().domains).toHaveLength(2);
    });

    it("updateDomain modifies an existing domain", () => {
      useDomainStore.getState().addDomain(makeDomain());
      useDomainStore.getState().updateDomain("d1", { name: "Updated" });
      expect(useDomainStore.getState().domains[0]!.name).toBe("Updated");
    });

    it("deleteDomain removes the domain", () => {
      useDomainStore.getState().addDomain(makeDomain());
      useDomainStore.getState().deleteDomain("d1");
      expect(useDomainStore.getState().domains).toHaveLength(0);
    });

    it("deleteDomain clears activeDomainId if it matches", () => {
      useDomainStore.getState().addDomain(makeDomain());
      useDomainStore.getState().setActiveDomain("d1");
      useDomainStore.getState().deleteDomain("d1");
      expect(useDomainStore.getState().activeDomainId).toBeNull();
    });

    it("deleteDomain preserves activeDomainId if it does not match", () => {
      useDomainStore.getState().addDomain(makeDomain("d1"));
      useDomainStore.getState().addDomain(makeDomain("d2"));
      useDomainStore.getState().setActiveDomain("d2");
      useDomainStore.getState().deleteDomain("d1");
      expect(useDomainStore.getState().activeDomainId).toBe("d2");
    });
  });

  describe("activeDomain", () => {
    it("returns undefined when no domain is active", () => {
      expect(useDomainStore.getState().activeDomain()).toBeUndefined();
    });

    it("returns the active domain", () => {
      useDomainStore.getState().addDomain(makeDomain());
      useDomainStore.getState().setActiveDomain("d1");
      expect(useDomainStore.getState().activeDomain()?.id).toBe("d1");
    });
  });

  describe("rule CRUD", () => {
    beforeEach(() => {
      useDomainStore.getState().addDomain(makeDomain());
    });

    it("addRule appends a rule to the domain", () => {
      useDomainStore.getState().addRule("d1", makeRule());
      expect(useDomainStore.getState().domains[0]!.rules).toHaveLength(1);
    });

    it("updateRule modifies an existing rule", () => {
      useDomainStore.getState().addRule("d1", makeRule());
      useDomainStore.getState().updateRule("d1", "n1", { proposition: "updated" });
      expect(useDomainStore.getState().domains[0]!.rules[0]!.proposition).toBe("updated");
    });

    it("deleteRule removes the rule", () => {
      useDomainStore.getState().addRule("d1", makeRule());
      useDomainStore.getState().deleteRule("d1", "n1");
      expect(useDomainStore.getState().domains[0]!.rules).toHaveLength(0);
    });
  });

  describe("role CRUD", () => {
    beforeEach(() => {
      useDomainStore.getState().addDomain(makeDomain());
    });

    it("addRole appends a role", () => {
      useDomainStore.getState().addRole("d1", makeRole());
      expect(useDomainStore.getState().domains[0]!.roles).toHaveLength(1);
    });

    it("updateRole modifies an existing role", () => {
      useDomainStore.getState().addRole("d1", makeRole());
      useDomainStore.getState().updateRole("d1", "r1", { name: "Updated" });
      expect(useDomainStore.getState().domains[0]!.roles[0]!.name).toBe("Updated");
    });

    it("deleteRole removes the role", () => {
      useDomainStore.getState().addRole("d1", makeRole());
      useDomainStore.getState().deleteRole("d1", "r1");
      expect(useDomainStore.getState().domains[0]!.roles).toHaveLength(0);
    });
  });

  describe("obligationType CRUD", () => {
    beforeEach(() => {
      useDomainStore.getState().addDomain(makeDomain());
    });

    it("add/update/delete cycle works", () => {
      const ot: ObligationType = { id: "ot1", name: "Safety", description: "", children: [] };
      useDomainStore.getState().addObligationType("d1", ot);
      expect(useDomainStore.getState().domains[0]!.obligationTypes).toHaveLength(1);

      useDomainStore.getState().updateObligationType("d1", "ot1", { name: "Updated" });
      expect(useDomainStore.getState().domains[0]!.obligationTypes[0]!.name).toBe("Updated");

      useDomainStore.getState().deleteObligationType("d1", "ot1");
      expect(useDomainStore.getState().domains[0]!.obligationTypes).toHaveLength(0);
    });
  });

  describe("code CRUD", () => {
    beforeEach(() => {
      useDomainStore.getState().addDomain(makeDomain());
    });

    it("add/update/delete cycle works", () => {
      const code: CodeOfConduct = { id: "c1", name: "Code", description: "", prevalence: 1 };
      useDomainStore.getState().addCode("d1", code);
      expect(useDomainStore.getState().domains[0]!.codes).toHaveLength(1);

      useDomainStore.getState().updateCode("d1", "c1", { name: "Updated" });
      expect(useDomainStore.getState().domains[0]!.codes[0]!.name).toBe("Updated");

      useDomainStore.getState().deleteCode("d1", "c1");
      expect(useDomainStore.getState().domains[0]!.codes).toHaveLength(0);
    });
  });
});
