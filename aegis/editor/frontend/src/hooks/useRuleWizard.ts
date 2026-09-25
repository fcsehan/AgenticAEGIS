import { useState, useCallback } from "react";
import type { DeonticModality, NormFrame } from "@/types/domain";

export interface RuleWizardData {
  modality: DeonticModality | null;
  agentRole: string;
  code: string;
  proposition: string;
  specificity: number;
  defeasible: boolean;
}

const TOTAL_STEPS = 4;

const initialData: RuleWizardData = {
  modality: null,
  agentRole: "",
  code: "",
  proposition: "",
  specificity: 1,
  defeasible: true,
};

export function useRuleWizard(existingRule?: NormFrame) {
  const [step, setStep] = useState(1);
  const [data, setData] = useState<RuleWizardData>(
    existingRule
      ? {
          modality: existingRule.modality,
          agentRole: existingRule.agentRole,
          code: existingRule.code,
          proposition: existingRule.proposition,
          specificity: existingRule.specificity,
          defeasible: existingRule.defeasible,
        }
      : initialData,
  );

  const canProceed = useCallback((): boolean => {
    switch (step) {
      case 1:
        return data.modality !== null;
      case 2:
        return data.agentRole !== "" && data.code !== "";
      case 3:
        return data.proposition.trim() !== "";
      case 4:
        return true;
      default:
        return false;
    }
  }, [step, data]);

  const next = useCallback(() => {
    if (step < TOTAL_STEPS && canProceed()) setStep(step + 1);
  }, [step, canProceed]);

  const back = useCallback(() => {
    if (step > 1) setStep(step - 1);
  }, [step]);

  const update = useCallback((updates: Partial<RuleWizardData>) => {
    setData((prev) => ({ ...prev, ...updates }));
  }, []);

  const reset = useCallback(() => {
    setStep(1);
    setData(initialData);
  }, []);

  const toNormFrame = useCallback(
    (id?: string): NormFrame | null => {
      if (!data.modality) return null;
      return {
        id: id ?? crypto.randomUUID(),
        code: data.code,
        agentRole: data.agentRole,
        modality: data.modality,
        proposition: data.proposition.trim(),
        specificity: data.specificity,
        defeasible: data.defeasible,
      };
    },
    [data],
  );

  return {
    step,
    totalSteps: TOTAL_STEPS,
    data,
    canProceed: canProceed(),
    isFirstStep: step === 1,
    isLastStep: step === TOTAL_STEPS,
    next,
    back,
    update,
    reset,
    toNormFrame,
  };
}
