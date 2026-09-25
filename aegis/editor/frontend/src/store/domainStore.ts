import { create } from "zustand";
import type { Domain, NormFrame, Role, ObligationType, CodeOfConduct } from "@/types/domain";

interface DomainState {
  domains: Domain[];
  activeDomainId: string | null;

  // Domain CRUD
  setDomains: (domains: Domain[]) => void;
  setActiveDomain: (id: string | null) => void;
  addDomain: (domain: Domain) => void;
  updateDomain: (id: string, updates: Partial<Domain>) => void;
  deleteDomain: (id: string) => void;

  // Rule CRUD
  addRule: (domainId: string, rule: NormFrame) => void;
  updateRule: (domainId: string, ruleId: string, updates: Partial<NormFrame>) => void;
  deleteRule: (domainId: string, ruleId: string) => void;

  // Role CRUD
  addRole: (domainId: string, role: Role) => void;
  updateRole: (domainId: string, roleId: string, updates: Partial<Role>) => void;
  deleteRole: (domainId: string, roleId: string) => void;

  // Obligation Type CRUD
  addObligationType: (domainId: string, ot: ObligationType) => void;
  updateObligationType: (
    domainId: string,
    otId: string,
    updates: Partial<ObligationType>,
  ) => void;
  deleteObligationType: (domainId: string, otId: string) => void;

  // Code of Conduct CRUD
  addCode: (domainId: string, code: CodeOfConduct) => void;
  updateCode: (domainId: string, codeId: string, updates: Partial<CodeOfConduct>) => void;
  deleteCode: (domainId: string, codeId: string) => void;

  // Computed
  activeDomain: () => Domain | undefined;
}

function updateDomainInList(
  domains: Domain[],
  domainId: string,
  updater: (d: Domain) => Domain,
): Domain[] {
  return domains.map((d) => (d.id === domainId ? updater(d) : d));
}

export const useDomainStore = create<DomainState>((set, get) => ({
  domains: [],
  activeDomainId: null,

  setDomains: (domains) => set({ domains }),
  setActiveDomain: (id) => set({ activeDomainId: id }),

  addDomain: (domain) => set((s) => ({ domains: [...s.domains, domain] })),

  updateDomain: (id, updates) =>
    set((s) => ({
      domains: s.domains.map((d) => (d.id === id ? { ...d, ...updates } : d)),
    })),

  deleteDomain: (id) =>
    set((s) => ({
      domains: s.domains.filter((d) => d.id !== id),
      activeDomainId: s.activeDomainId === id ? null : s.activeDomainId,
    })),

  // Rules
  addRule: (domainId, rule) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        rules: [...d.rules, rule],
      })),
    })),

  updateRule: (domainId, ruleId, updates) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        rules: d.rules.map((r) => (r.id === ruleId ? { ...r, ...updates } : r)),
      })),
    })),

  deleteRule: (domainId, ruleId) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        rules: d.rules.filter((r) => r.id !== ruleId),
      })),
    })),

  // Roles
  addRole: (domainId, role) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        roles: [...d.roles, role],
      })),
    })),

  updateRole: (domainId, roleId, updates) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        roles: d.roles.map((r) => (r.id === roleId ? { ...r, ...updates } : r)),
      })),
    })),

  deleteRole: (domainId, roleId) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        roles: d.roles.filter((r) => r.id !== roleId),
      })),
    })),

  // Obligation Types
  addObligationType: (domainId, ot) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        obligationTypes: [...d.obligationTypes, ot],
      })),
    })),

  updateObligationType: (domainId, otId, updates) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        obligationTypes: d.obligationTypes.map((ot) =>
          ot.id === otId ? { ...ot, ...updates } : ot,
        ),
      })),
    })),

  deleteObligationType: (domainId, otId) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        obligationTypes: d.obligationTypes.filter((ot) => ot.id !== otId),
      })),
    })),

  // Codes
  addCode: (domainId, code) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        codes: [...d.codes, code],
      })),
    })),

  updateCode: (domainId, codeId, updates) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        codes: d.codes.map((c) => (c.id === codeId ? { ...c, ...updates } : c)),
      })),
    })),

  deleteCode: (domainId, codeId) =>
    set((s) => ({
      domains: updateDomainInList(s.domains, domainId, (d) => ({
        ...d,
        codes: d.codes.filter((c) => c.id !== codeId),
      })),
    })),

  activeDomain: () => {
    const { domains, activeDomainId } = get();
    return domains.find((d) => d.id === activeDomainId);
  },
}));
