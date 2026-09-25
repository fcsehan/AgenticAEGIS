import { useEditorText } from "@/hooks/useEditorText";
import { useState } from "react";
import { requestJson } from "@/api/client";
import { useTranslation } from "react-i18next";
import { Modal, Button } from "@/components/ui";
import type { Domain, NormFrame } from "@/types/domain";
import { useRuleWizard } from "@/hooks/useRuleWizard";
import { useDomainStore } from "@/store/domainStore";
import { ModalityPicker } from "./ModalityPicker";
import { SubjectPicker } from "./SubjectPicker";
import { PropositionBuilder } from "./PropositionBuilder";
import { ContextPanel } from "./ContextPanel";
import { RuleSummary } from "./RuleSummary";

interface RuleEditorProps {
  domain: Domain;
  rule?: NormFrame;
  copy?: boolean;
  open: boolean;
  onClose: () => void;
}

export function RuleEditor({
  domain,
  rule,
  copy = false,
  open,
  onClose,
}: RuleEditorProps) {
  const tx = useEditorText();
  const { t } = useTranslation("rules");
  const { t: tc } = useTranslation("common");
  const addRule = useDomainStore((s) => s.addRule);
  const updateRule = useDomainStore((s) => s.updateRule);
  const [baseRevision] = useState(domain.revision);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const wizard = useRuleWizard(rule);

  const handleSave = async () => {
    const frame = wizard.toNormFrame(rule?.id);
    if (!frame) return;

    if (domain.revision) {
      setBusy(true);
      setError("");
      try {
        const saved = await requestJson<Domain>(
          `/api/domains/${domain.id}/source-rules${rule && !copy ? `/${rule.id}` : ""}`,
          {
            method: rule && !copy ? "PUT" : "POST",
            body: JSON.stringify({ ...frame, revision: baseRevision }),
          },
        );
        useDomainStore.getState().updateDomain(domain.id, saved);
        onClose();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : tx("Save failed"),
        );
      } finally {
        setBusy(false);
      }
      return;
    }
    if (rule) {
      updateRule(domain.id, rule.id, frame);
    } else {
      addRule(domain.id, frame);
    }

    wizard.reset();
    onClose();
  };

  const handleClose = () => {
    wizard.reset();
    onClose();
  };

  const stepContent = () => {
    switch (wizard.step) {
      case 1:
        return (
          <ModalityPicker
            value={wizard.data.modality}
            onChange={(m) => wizard.update({ modality: m })}
          />
        );
      case 2:
        return (
          <SubjectPicker
            domain={domain}
            agentRole={wizard.data.agentRole}
            code={wizard.data.code}
            onChangeRole={(r) => wizard.update({ agentRole: r })}
            onChangeCode={(c) => wizard.update({ code: c })}
          />
        );
      case 3:
        return (
          <PropositionBuilder
            domain={domain}
            value={wizard.data.proposition}
            onChange={(p) => wizard.update({ proposition: p })}
          />
        );
      case 4:
        return (
          <>
            {domain.revision ? (
              <p>
                {" "}
                {tx(
                  "Specificity is derived from the role hierarchy. The MELD predicate determines the rule kind.",
                )}{" "}
              </p>
            ) : (
              <ContextPanel
                specificity={wizard.data.specificity}
                defeasible={wizard.data.defeasible}
                onChangeSpecificity={(s) => wizard.update({ specificity: s })}
                onChangeDefeasible={(d) => wizard.update({ defeasible: d })}
              />
            )}
            <div className="mt-4">
              <RuleSummary data={wizard.data} />
            </div>
          </>
        );
      default:
        return null;
    }
  };

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={rule && !copy ? t("editRule") : t("addRule")}
      className="max-w-xl"
    >
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>
            {t("step", { current: wizard.step, total: wizard.totalSteps })}
          </span>
          <div className="flex gap-1">
            {Array.from({ length: wizard.totalSteps }, (_, i) => (
              <div
                key={i}
                className={`h-1.5 w-6 rounded-full ${
                  i < wizard.step ? "bg-accent" : "bg-slate-200"
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {stepContent()}

      <div className="mt-6 flex justify-between">
        <Button variant="ghost" onClick={handleClose}>
          {tc("cancel")}
        </Button>
        <div className="flex gap-2">
          {!wizard.isFirstStep && (
            <Button variant="secondary" onClick={wizard.back}>
              {tc("back")}
            </Button>
          )}
          {wizard.isLastStep ? (
            <Button onClick={handleSave} disabled={!wizard.canProceed || busy}>
              {tc("save")}
            </Button>
          ) : (
            <Button onClick={wizard.next} disabled={!wizard.canProceed || busy}>
              {tc("next")}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
