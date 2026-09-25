import { editorFetch } from "@/api/client";
import { useState, useCallback, useEffect } from "react";

export type WizardStep = 1 | 2 | 3 | 4 | 5;

export interface PreCondition {
  id: string;
  label: string;
  satisfied: boolean;
  detail: string;
}

export interface ReleaseResult {
  success: boolean;
  version: string;
  exportedFiles: string[];
  error?: string;
}

export function useAuthoringWizard(domainId: string) {
  const [step, setStep] = useState<WizardStep>(1);
  const [providerId, setProviderId] = useState("");
  const [modelId, setModelId] = useState("");
  const [preconditions, setPreconditions] = useState<PreCondition[]>([]);
  const [canRelease, setCanRelease] = useState(false);
  const [legalDocMarkdown, setLegalDocMarkdown] = useState("");
  const [legalDocLocale, setLegalDocLocale] = useState("en");

  useEffect(() => {
    editorFetch("/api/llm/settings")
      .then((r) => r.json())
      .then(
        (settings: {
          defaultProfile: string;
          profiles: { id: string; model: string }[];
        }) => {
          const profile = settings.profiles.find(
            (p) => p.id === settings.defaultProfile,
          );
          if (profile) {
            setProviderId(profile.id);
            setModelId(profile.model);
          }
        },
      )
      .catch(() => {
        /* Explicit selection remains available. */
      });
  }, []);

  const goToStep = useCallback(
    (target: WizardStep) => {
      // Only allow navigating to completed or current steps
      if (target <= step) {
        setStep(target);
      }
    },
    [step],
  );

  const nextStep = useCallback(() => {
    setStep((s) => Math.min(s + 1, 5) as WizardStep);
  }, []);

  const prevStep = useCallback(() => {
    setStep((s) => Math.max(s - 1, 1) as WizardStep);
  }, []);

  const fetchPreconditions = useCallback(async () => {
    try {
      const resp = await editorFetch(
        `/api/domains/${domainId}/release/preconditions`,
      );
      const data = await resp.json();
      setPreconditions(data.preconditions ?? []);
      setCanRelease(data.canRelease ?? false);
    } catch {
      setPreconditions([]);
      setCanRelease(false);
    }
  }, [domainId]);

  const fetchLegalDoc = useCallback(
    async (locale: string = "en") => {
      try {
        const resp = await editorFetch(
          `/api/domains/${domainId}/legal-doc?locale=${locale}`,
        );
        const data = await resp.json();
        setLegalDocMarkdown(data.markdown ?? "");
        setLegalDocLocale(locale);
      } catch {
        setLegalDocMarkdown("");
      }
    },
    [domainId],
  );

  const release = useCallback(
    async (version: string, message: string = ""): Promise<ReleaseResult> => {
      const resp = await editorFetch(`/api/domains/${domainId}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version, message }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        return {
          success: false,
          version: "",
          exportedFiles: [],
          error: err.detail ?? "Release failed",
        };
      }
      return (await resp.json()) as ReleaseResult;
    },
    [domainId],
  );

  return {
    step,
    providerId,
    modelId,
    preconditions,
    canRelease,
    legalDocMarkdown,
    legalDocLocale,
    setProviderId,
    setModelId,
    goToStep,
    resumeReview: () => setStep(3),
    nextStep,
    prevStep,
    fetchPreconditions,
    fetchLegalDoc,
    release,
  };
}
