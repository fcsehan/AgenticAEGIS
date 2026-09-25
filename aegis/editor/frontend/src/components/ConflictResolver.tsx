import { useTranslation } from "react-i18next";
import { Scales } from "@phosphor-icons/react";
import type { ValidationIssue } from "@/lib/validation";
import type { Domain } from "@/types/domain";
import { Card, Button } from "@/components/ui";

interface ConflictResolverProps {
  issue: ValidationIssue;
  domain: Domain;
}

export function ConflictResolver({ issue, domain }: ConflictResolverProps) {
  const { t } = useTranslation("validation");
  const ruleA = domain.rules.find((r) => r.id === issue.ruleId);
  const ruleB = domain.rules.find((r) => r.id === issue.relatedRuleId);

  if (!ruleA || !ruleB) return null;

  return (
    <Card className="border-status-warning">
      <div className="mb-3 flex items-center gap-2">
        <Scales size={16} className="text-status-warning" />
        <span className="text-sm font-medium">{t("conflictResolution")}</span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-3">
        <div className="rounded-sm bg-surface-tertiary p-2">
          <p className="text-xs font-medium text-slate-600">{ruleA.modality}</p>
          <p className="font-mono text-xs text-slate-800">{ruleA.proposition}</p>
          <p className="text-[10px] text-slate-400">
            Specificity: {ruleA.specificity} | Code: {ruleA.code}
          </p>
        </div>
        <div className="rounded-sm bg-surface-tertiary p-2">
          <p className="text-xs font-medium text-slate-600">{ruleB.modality}</p>
          <p className="font-mono text-xs text-slate-800">{ruleB.proposition}</p>
          <p className="text-[10px] text-slate-400">
            Specificity: {ruleB.specificity} | Code: {ruleB.code}
          </p>
        </div>
      </div>

      <div className="flex gap-2">
        <Button size="sm" variant="secondary">
          {t("specificity")}
        </Button>
        <Button size="sm" variant="secondary">
          {t("prevalence")}
        </Button>
      </div>
    </Card>
  );
}
