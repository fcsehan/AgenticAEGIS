import { useEditorText } from "@/hooks/useEditorText";
import { useTranslation } from "react-i18next";
import { ProposalCard } from "./ProposalCard";
import type { RuleProposal, VerificationResult } from "@/hooks/useGeneration";

interface ProposalReviewProps {
  proposals: RuleProposal[];
  verificationResults: Map<string, VerificationResult>;
  onAccept: (index: number) => void;
  onReject: (index: number) => void;
  onRefine: (index: number, feedback: string) => void;
  onVerify: (index: number) => void;
}

export function ProposalReview({
  proposals,
  verificationResults,
  onAccept,
  onReject,
  onRefine,
  onVerify,
}: ProposalReviewProps) {
  const tx = useEditorText();
  const { t } = useTranslation("authoring");

  if (proposals.length === 0) {
    return (
      <p className="text-sm text-slate-500 text-center py-8">
        {" "}
        {tx("No proposals yet. Go back and describe your rules.")}{" "}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          {t("proposals")}
        </h3>
        <span className="text-xs text-slate-500">
          {t("proposalCount", { count: proposals.length })}
        </span>
      </div>

      <div className="space-y-3">
        {proposals.map((proposal, index) => (
          <ProposalCard
            key={proposal.id}
            proposal={proposal}
            index={index}
            verification={verificationResults.get(proposal.id)}
            onAccept={() => onAccept(index)}
            onReject={() => onReject(index)}
            onRefine={(feedback) => onRefine(index, feedback)}
            onVerify={() => onVerify(index)}
          />
        ))}
      </div>
    </div>
  );
}
