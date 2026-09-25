import { useTranslation } from "react-i18next";
import { Warning, XCircle, CheckCircle } from "@phosphor-icons/react";
import type { ValidationIssue } from "@/lib/validation";

interface ValidationStatusProps {
  issues: ValidationIssue[];
}

export function ValidationStatus({ issues }: ValidationStatusProps) {
  const { t } = useTranslation("validation");

  if (issues.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        <CheckCircle size={16} weight="fill" />
        {t("noIssues")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {issues.map((issue) => (
        <div
          key={issue.id}
          className={`flex items-start gap-2 rounded-md px-3 py-2 text-sm ${
            issue.severity === "error"
              ? "bg-red-50 text-red-700"
              : "bg-amber-50 text-amber-700"
          }`}
        >
          {issue.severity === "error" ? (
            <XCircle size={16} weight="fill" className="mt-0.5 shrink-0" />
          ) : (
            <Warning size={16} weight="fill" className="mt-0.5 shrink-0" />
          )}
          <div>
            <p>{issue.message}</p>
            {issue.suggestion && (
              <p className="mt-0.5 text-xs opacity-75">{issue.suggestion}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
