import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import type { RuleProposal, VerificationResult } from "@/hooks/useGeneration";

interface TestMatrixProps {
  proposals: RuleProposal[];
  verificationResults: Map<string, VerificationResult>;
  onRunTests: () => void;
}

const expectedVerdict: Record<string, string> = {
  OBLIGATORY: "PERMITTED",
  FORBIDDEN: "FORBIDDEN",
  PERMITTED: "PERMITTED",
};

export function TestMatrix({
  proposals,
  verificationResults,
  onRunTests,
}: TestMatrixProps) {
  const { t } = useTranslation("authoring");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          {t("testMatrix")}
        </h3>
        <Button variant="secondary" size="sm" onClick={onRunTests}>
          {t("runAllTests")}
        </Button>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                #
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                {t("rule")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                {t("testAction")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                {t("expected")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                {t("actual")}
              </th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-slate-600">
                {t("status")}
              </th>
            </tr>
          </thead>
          <tbody>
            {proposals.map((proposal, index) => {
              const vr = verificationResults.get(proposal.id);
              const funcStage = vr?.stages.find(
                (s) => s.stage === "functional",
              );
              const expected = expectedVerdict[proposal.modality] ?? "?";
              const actual =
                funcStage?.status === "PASS"
                  ? expected
                  : funcStage?.status === "FAIL"
                    ? ((funcStage.details as Record<string, string>)?.verdict ??
                      "?")
                    : "—";
              const passed = funcStage?.status === "PASS";

              return (
                <tr
                  key={proposal.id}
                  className="border-b border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-3 py-2 text-xs text-slate-400 tabular-nums">
                    {index + 1}
                  </td>
                  <td className="px-3 py-2 text-slate-800 truncate max-w-[200px]">
                    {proposal.naturalLanguageSummary}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">
                    {proposal.actionType}
                  </td>
                  <td className="px-3 py-2">
                    <VerdictBadge verdict={expected} />
                  </td>
                  <td className="px-3 py-2">
                    <VerdictBadge verdict={actual} />
                  </td>
                  <td className="px-3 py-2">
                    {funcStage ? (
                      <span
                        className={`text-sm font-bold ${passed ? "text-emerald-600" : "text-red-600"}`}
                      >
                        {passed ? "✓" : "✕"}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const colors: Record<string, string> = {
    PERMITTED: "bg-emerald-100 text-emerald-800",
    FORBIDDEN: "bg-red-100 text-red-800",
    UNDECIDABLE: "bg-amber-100 text-amber-800",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[verdict] ?? "bg-slate-100 text-slate-600"}`}
    >
      {verdict}
    </span>
  );
}
