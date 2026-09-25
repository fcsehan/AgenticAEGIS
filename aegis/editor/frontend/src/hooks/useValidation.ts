import { useEffect, useMemo, useState } from "react";
import type { Domain } from "@/types/domain";
import { validateDomain, type ValidationIssue } from "@/lib/validation";
import { requestJson } from "@/api/client";

export function useValidation(domain: Domain | undefined) {
  const [remote, setRemote] = useState<{
    revision: string;
    issues: ValidationIssue[];
  } | null>(null);
  useEffect(() => {
    if (!domain?.revision) return;
    let active = true;
    setRemote(null);
    requestJson<{ revision: string; issues: ValidationIssue[] }>(
      `/api/domains/${domain.id}/validate`,
    )
      .then((result) => {
        if (active) setRemote(result);
      })
      .catch((e: Error) => {
        if (active)
          setRemote({
            revision: domain.revision!,
            issues: [{ id: "backend", severity: "error", message: e.message }],
          });
      });
    return () => {
      active = false;
    };
  }, [domain?.id, domain?.revision]);
  return useMemo(() => {
    const issues = !domain
      ? []
      : domain.revision
        ? remote?.revision === domain.revision
          ? remote.issues
          : [
              {
                id: "pending",
                severity: "warning" as const,
                message: "Server validation pending",
              },
            ]
        : validateDomain(domain);
    return {
      issues,
      errors: issues.filter((i) => i.severity === "error").length,
      warnings: issues.filter((i) => i.severity === "warning").length,
    };
  }, [domain, remote]);
}
