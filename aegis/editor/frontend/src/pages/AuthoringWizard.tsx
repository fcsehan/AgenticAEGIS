import { useEditorText } from "@/hooks/useEditorText";
import { useState } from "react";
import { useDomainStore } from "@/store/domainStore";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { ProviderSelector } from "@/components/authoring/ProviderSelector";
import { RuleDescriptionForm } from "@/components/authoring/RuleDescriptionForm";
import { ProposalReview } from "@/components/authoring/ProposalReview";
import { ScenarioPanel } from "@/components/ScenarioPanel";
import { GovernancePanel } from "@/components/GovernancePanel";
import {
  useAuthoringWizard,
  type WizardStep,
} from "@/hooks/useAuthoringWizard";
import { useGeneration } from "@/hooks/useGeneration";

const STEP_KEYS = ["step1", "step2", "step3", "step4", "step5"] as const;

export function AuthoringWizard() {
  const tx = useEditorText();
  const { id: domainId = "" } = useParams<{ id: string }>();
  const { t } = useTranslation("authoring");

  const wizard = useAuthoringWizard(domainId);
  const generation = useGeneration(domainId);

  // Domain info for context (roles, action types)
  const domain = useDomainStore((s) =>
    s.domains.find((d) => d.id === domainId),
  );
  const domainRoles = domain?.roles.map((r) => r.name) ?? [];
  const domainActionTypes = domain?.actionTypes ?? [];
  const [error, setError] = useState("");

  const handleGenerate = async (
    description: string,
    roles: string[],
    actionTypes: string[],
  ) => {
    setError("");
    try {
      await generation.generate(
        description,
        wizard.providerId,
        wizard.modelId,
        roles,
        actionTypes,
      );
      wizard.nextStep();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-6 py-4">
        <Link to={`/domain/${domainId}`}>← Domain</Link>
        <h1 className="text-lg font-semibold text-slate-900">{t("title")}</h1>
        <p className="text-sm text-slate-500 mt-0.5">{t("subtitle")}</p>
        <p className="text-xs">
          {" "}
          {tx("Provider:")} {wizard.providerId || "not selected"}{" "}
          {tx("· Model:")} {wizard.modelId || "not selected"}{" "}
          {tx("· Classification:")}{" "}
          {domain?.classification ?? "confidentialData"}{" "}
          {tx(
            ". Description and domain context will be sent to this provider.",
          )}{" "}
        </p>
      </div>

      {/* Stepper */}
      <div className="border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-1">
          {STEP_KEYS.map((key, idx) => {
            const stepNum = (idx + 1) as WizardStep;
            const isActive = wizard.step === stepNum;
            const isCompleted = wizard.step > stepNum;
            const isClickable = wizard.step >= stepNum;

            return (
              <div key={key} className="flex items-center">
                {idx > 0 && (
                  <div
                    className={`h-px w-8 mx-1 ${isCompleted ? "bg-indigo-500" : "bg-slate-200"}`}
                  />
                )}
                <button
                  type="button"
                  onClick={() => isClickable && wizard.goToStep(stepNum)}
                  disabled={!isClickable}
                  className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? "bg-indigo-100 text-indigo-800"
                      : isCompleted
                        ? "bg-emerald-100 text-emerald-800 cursor-pointer"
                        : "bg-slate-100 text-slate-400"
                  }`}
                >
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                      isActive
                        ? "bg-indigo-600 text-white"
                        : isCompleted
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-300 text-white"
                    }`}
                  >
                    {isCompleted ? "✓" : stepNum}
                  </span>
                  {t(key)}
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Step Content */}
      <div className="mx-auto max-w-3xl px-6 py-6">
        {generation.generating && (
          <p role="status">
            {" "}
            {tx("Inference job")} {generation.jobId || "starting"}{" "}
            {tx("is running.")}{" "}
            <button
              onClick={() => {
                generation.cancel().catch((e: Error) => setError(e.message));
              }}
            >
              {" "}
              {tx("Cancel")}{" "}
            </button>
          </p>
        )}
        {wizard.step < 3 && generation.proposals.length > 0 && (
          <button onClick={wizard.resumeReview}>
            {" "}
            {tx("Resume saved proposals")}{" "}
          </button>
        )}
        {generation.recoveryError && (
          <p role="alert">{generation.recoveryError}</p>
        )}
        {error && (
          <p role="alert" className="text-red-700">
            {error}
          </p>
        )}
        <Card className="p-6">
          {wizard.step === 1 && (
            <div className="space-y-6">
              <ProviderSelector
                selectedProviderId={wizard.providerId}
                selectedModelId={wizard.modelId}
                onProviderChange={wizard.setProviderId}
                onModelChange={wizard.setModelId}
              />
              <Button
                size="lg"
                className="w-full"
                disabled={!wizard.providerId || !wizard.modelId}
                onClick={wizard.nextStep}
              >
                {t("startAuthoring")}
              </Button>
            </div>
          )}

          {wizard.step === 2 && (
            <RuleDescriptionForm
              draftKey={domainId}
              roles={domainRoles}
              actionTypes={domainActionTypes}
              generating={generation.generating}
              onGenerate={handleGenerate}
            />
          )}

          {wizard.step === 3 && (
            <ProposalReview
              proposals={generation.proposals}
              verificationResults={generation.verificationResults}
              onAccept={(i) => {
                generation.accept(i).catch((e: Error) => setError(e.message));
              }}
              onReject={(i) => generation.removeProposal(i)}
              onRefine={(i, feedback) => {
                generation
                  .refine(i, feedback, wizard.providerId, wizard.modelId)
                  .catch((e: Error) => setError(e.message));
              }}
              onVerify={(i) => {
                generation.verify(i).catch((e: Error) => setError(e.message));
              }}
            />
          )}

          {wizard.step === 4 && <ScenarioPanel domainId={domainId} />}
          {wizard.step === 5 && domain && <GovernancePanel domain={domain} />}
        </Card>

        {/* Navigation */}
        {wizard.step > 1 && wizard.step < 5 && (
          <div className="flex justify-between mt-4">
            <Button variant="secondary" onClick={wizard.prevStep}>
              {t("back")}
            </Button>
            <Button
              disabled={
                wizard.step === 2 ||
                (wizard.step === 3 && generation.proposals.length > 0)
              }
              onClick={wizard.nextStep}
            >
              {t("next")}
            </Button>
          </div>
        )}
        {wizard.step === 5 && (
          <div className="mt-4">
            <Button variant="secondary" onClick={wizard.prevStep}>
              {t("back")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
