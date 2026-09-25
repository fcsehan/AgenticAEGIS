import { useTranslation } from "react-i18next";
import type { RuleWizardData } from "@/hooks/useRuleWizard";

interface RuleSummaryProps {
  data: RuleWizardData;
}

export function RuleSummary({ data }: RuleSummaryProps) {
  const { t } = useTranslation("rules");

  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">{t("summary")}</p>
      <div className="rounded-md border border-border bg-surface-tertiary p-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-slate-500">{t("modality")}</dt>
          <dd className="font-medium text-slate-800">{data.modality ?? "—"}</dd>

          <dt className="text-slate-500">{t("subject")}</dt>
          <dd className="font-medium text-slate-800">{data.agentRole || "—"}</dd>

          <dt className="text-slate-500">Code</dt>
          <dd className="font-medium text-slate-800">{data.code || "—"}</dd>

          <dt className="text-slate-500">{t("proposition")}</dt>
          <dd className="font-mono text-sm text-slate-800">{data.proposition || "—"}</dd>

          <dt className="text-slate-500">{t("specificity")}</dt>
          <dd className="font-medium text-slate-800">{data.specificity}</dd>

          <dt className="text-slate-500">{t("defeasible")}</dt>
          <dd className="font-medium text-slate-800">{data.defeasible ? "Yes" : "No"}</dd>
        </dl>
      </div>
    </div>
  );
}
