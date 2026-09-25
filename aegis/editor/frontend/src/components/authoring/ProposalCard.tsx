import { useEditorText } from "@/hooks/useEditorText";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import type { RuleProposal, VerificationResult } from "@/hooks/useGeneration";

const modalityStyles = {
  OBLIGATORY: "bg-blue-100 text-blue-800",
  FORBIDDEN: "bg-red-100 text-red-800",
  PERMITTED: "bg-emerald-100 text-emerald-800",
};

const stageStatusIcons = {
  PASS: "text-emerald-600",
  FAIL: "text-red-600",
  SKIP: "text-slate-400",
};

interface ProposalCardProps {
  proposal: RuleProposal;
  index: number;
  verification?: VerificationResult;
  onAccept: () => void;
  onReject: () => void;
  onRefine: (feedback: string) => void;
  onVerify: () => void;
}

export function ProposalCard({
  proposal,
  index,
  verification,
  onAccept,
  onReject,
  onRefine,
  onVerify,
}: ProposalCardProps) {
  const tx = useEditorText();
  const { t } = useTranslation("authoring");
  const [showMeld, setShowMeld] = useState(false);
  const [refineMode, setRefineMode] = useState(false);
  const [refineFeedback, setRefineFeedback] = useState("");

  return (
    <Card className="space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${modalityStyles[proposal.modality]}`}
          >
            {proposal.modality}
          </span>
          <span className="text-sm text-slate-600">
            {proposal.agentRole}
            {proposal.codeOfConduct && (
              <span className="text-slate-400">
                {" "}
                @ {proposal.codeOfConduct}
              </span>
            )}
          </span>
        </div>
        <span className="text-xs text-slate-400 tabular-nums">
          #{index + 1}
        </span>
      </div>

      {/* Summary */}
      <p className="text-sm text-slate-800">
        {proposal.naturalLanguageSummary}
      </p>

      {/* Reasoning */}
      {proposal.reasoning && (
        <p className="text-xs text-slate-500 italic">{proposal.reasoning}</p>
      )}

      {/* MELD Preview (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowMeld(!showMeld)}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
        >
          {showMeld ? "Hide" : "Show"} {t("meldPreview")}
        </button>
        {showMeld && (
          <pre className="mt-1.5 rounded bg-slate-900 p-3 text-xs text-slate-100 font-mono overflow-x-auto">
            {proposal.meldExpression}
          </pre>
        )}
      </div>

      {/* Verification Status */}
      {verification && (
        <div className="rounded-md bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700 mb-2">
            {t("verificationStatus")}
          </p>
          <div className="grid grid-cols-4 gap-2">
            {verification.stages.map((stage) => (
              <div key={stage.stage} className="text-center">
                <div
                  className={`text-lg font-bold ${stageStatusIcons[stage.status]}`}
                >
                  {stage.status === "PASS"
                    ? "✓"
                    : stage.status === "FAIL"
                      ? "✕"
                      : "—"}
                </div>
                <p className="text-xs text-slate-600 capitalize">
                  {t(
                    stage.stage as
                      | "syntax"
                      | "symbol"
                      | "conflict"
                      | "functional",
                  )}
                </p>
              </div>
            ))}
          </div>
          {!verification.passed && (
            <p className="mt-2 text-xs text-red-600">
              {verification.stages.find((s) => s.status === "FAIL")?.message}
            </p>
          )}
        </div>
      )}

      {/* Refine input */}
      {refineMode && (
        <div className="space-y-2">
          <textarea
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 min-h-[80px]"
            placeholder={t("refinePlaceholder")}
            value={refineFeedback}
            onChange={(e) => setRefineFeedback(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => {
                onRefine(refineFeedback);
                setRefineMode(false);
                setRefineFeedback("");
              }}
              disabled={!refineFeedback.trim()}
            >
              {t("refine")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setRefineMode(false)}
            >
              {" "}
              {tx("Cancel")}{" "}
            </Button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1 border-t border-slate-100">
        <Button
          variant="primary"
          size="sm"
          disabled={!verification?.passed}
          onClick={onAccept}
        >
          {t("accept")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onVerify}>
          {" "}
          {tx("Verify")}{" "}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setRefineMode(!refineMode)}
        >
          {t("refine")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onReject}>
          {t("reject")}
        </Button>
      </div>
    </Card>
  );
}
