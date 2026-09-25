/** Deontic modalities from the DDIC engine. */
export type DeonticModality = "OBLIGATORY" | "FORBIDDEN" | "PERMITTED";

/** Guard verdict for an action check. */
export type Decision = "PERMITTED" | "FORBIDDEN" | "UNDECIDABLE";

/** Governance workflow status (D-002). */
export type DomainStatus = "Draft" | "Review" | "Published" | "Archived";

/** A single deontic assertion — the atomic unit of the rule base. */
export interface NormFrame {
  id: string;
  code: string;
  agentRole: string;
  modality: DeonticModality;
  proposition: string;
  specificity: number;
  defeasible: boolean;
  source?: string;
}

/** An agent role within a domain. */
export interface Role {
  id: string;
  name: string;
  description: string;
  obligationType?: string;
  ruleCount: number;
}

/** Hierarchical obligation type (tree structure). */
export interface ObligationType {
  id: string;
  name: string;
  description: string;
  parentId?: string;
  children: ObligationType[];
}

/** A code of conduct with prevalence ordering. */
export interface CodeOfConduct {
  id: string;
  name: string;
  description: string;
  prevalence: number;
}

/** Version entry for governance history. */
export interface DomainVersion {
  id: string;
  version: string;
  status: DomainStatus;
  author: string;
  timestamp: string;
  changeLog: string;
}

/** Top-level domain aggregate. */
export interface Domain {
  id: string;
  name: string;
  description: string;
  status: DomainStatus;
  classification?: string;
  roles: Role[];
  obligationTypes: ObligationType[];
  codes: CodeOfConduct[];
  rules: NormFrame[];
  revision?: string;
  codePrevalence?: string[];
  actionTypes?: string[];
  actionSchemas?: Record<string, { name: string; type: string }[]>;
  loadError?: string;
  compileStatus?: "ready" | "failed" | "uncompiled";
  conflictCount: number;
  lastModified: string;
  version?: string;
}

/** A discovered .meld file within a project directory. */
export interface MeldFile {
  path: string;
  name: string;
  type: "ontology" | "deontic" | "inference" | "vocabulary";
  sizeBytes: number;
}

/** A project directory loaded by the editor. */
export interface Project {
  path: string;
  name: string;
  meldFiles: MeldFile[];
  domains: Domain[];
  loadedAt: string;
}

/** An action to be checked by the guard. */
export interface Action {
  id: string;
  agent: string;
  actionType: string;
  description: string;
  parameters: Record<string, string>;
}

/** Guard verdict with justification chain. */
export interface Verdict {
  decision: Decision;
  justificationChain: string[];
  explanation: string;
  reasonType?: string;
  revision?: string;
  appliedRules: string[];
  timestamp: string;
}
