import type { Domain } from "@/types/domain";
import { levenshtein } from "./levenshtein";

export type Severity = "error" | "warning";

export interface ValidationIssue {
  id: string;
  severity: Severity;
  message: string;
  ruleId?: string;
  relatedRuleId?: string;
  suggestion?: string;
}

/** Collect all known symbols (role names, code IDs) from a domain. */
function getKnownSymbols(domain: Domain): Set<string> {
  const symbols = new Set<string>();
  for (const role of domain.roles) symbols.add(role.name);
  for (const code of domain.codes) symbols.add(code.id);
  for (const ot of domain.obligationTypes) symbols.add(ot.name);
  return symbols;
}

/** Find the closest known symbol (by edit distance) if distance ≤ 2. */
function findTypoSuggestion(symbol: string, known: Set<string>): string | undefined {
  let bestDist = 3;
  let bestMatch: string | undefined;
  for (const k of known) {
    const dist = levenshtein(symbol.toLowerCase(), k.toLowerCase());
    if (dist < bestDist) {
      bestDist = dist;
      bestMatch = k;
    }
  }
  return bestMatch;
}

/** Check if a rule's agentRole references a defined role. */
function validateSymbols(domain: Domain): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const known = getKnownSymbols(domain);
  const roleNames = new Set(domain.roles.map((r) => r.name));

  for (const rule of domain.rules) {
    if (!roleNames.has(rule.agentRole)) {
      const suggestion = findTypoSuggestion(rule.agentRole, known);
      issues.push({
        id: `undeclared-role-${rule.id}`,
        severity: "error",
        message: `Undeclared role "${rule.agentRole}" in rule ${rule.id}`,
        ruleId: rule.id,
        suggestion: suggestion ? `Did you mean "${suggestion}"?` : undefined,
      });
    }

    const codeIds = new Set(domain.codes.map((c) => c.id));
    if (!codeIds.has(rule.code)) {
      issues.push({
        id: `undeclared-code-${rule.id}`,
        severity: "error",
        message: `Undeclared code "${rule.code}" in rule ${rule.id}`,
        ruleId: rule.id,
      });
    }
  }

  return issues;
}

/** Detect conflicts: same role + same proposition + different modality. */
function detectConflicts(domain: Domain): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const rules = domain.rules;

  for (let i = 0; i < rules.length; i++) {
    for (let j = i + 1; j < rules.length; j++) {
      const a = rules[i]!;
      const b = rules[j]!;
      if (
        a.agentRole === b.agentRole &&
        a.proposition === b.proposition &&
        a.modality !== b.modality
      ) {
        issues.push({
          id: `conflict-${a.id}-${b.id}`,
          severity: "warning",
          message: `Conflict: "${a.modality}" vs "${b.modality}" for "${a.proposition}" (${a.agentRole})`,
          ruleId: a.id,
          relatedRuleId: b.id,
        });
      }
    }
  }

  return issues;
}

/** Run all validation checks on a domain. */
export function validateDomain(domain: Domain): ValidationIssue[] {
  return [...validateSymbols(domain), ...detectConflicts(domain)];
}
