import { useSessionDraft } from "./useSessionDraft";
import { runJob } from "@/api/jobs";
import { useDomainStore } from "@/store/domainStore";
import type { Domain } from "@/types/domain";
import { editorFetch } from "@/api/client";
import { useState, useCallback } from "react";

export interface PropositionParameters {
  [key: string]: string;
}

export interface RuleProposal {
  id: string;
  modality: "OBLIGATORY" | "FORBIDDEN" | "PERMITTED";
  agentRole: string;
  codeOfConduct: string;
  actionType: string;
  propositionParameters: PropositionParameters;
  defeasible: boolean;
  reasoning: string;
  naturalLanguageSummary: string;
  meldExpression: string;
}

export interface StageResult {
  stage: string;
  status: "PASS" | "FAIL" | "SKIP";
  message: string;
  details: Record<string, unknown>;
}

export interface VerificationResult {
  passed: boolean;
  stages: StageResult[];
  revision?: string;
}

export function useGeneration(domainId: string) {
  const [proposals, setProposals, recoveryError] = useSessionDraft<
    RuleProposal[]
  >(`proposals:${domainId}`, []);
  const [generating, setGenerating] = useState(false);
  const [jobId, setJobId] = useState("");
  const [verificationResults, setVerificationResults] = useState<
    Map<string, VerificationResult>
  >(new Map());

  const generate = useCallback(
    async (
      description: string,
      providerId: string,
      modelId: string,
      roles?: string[],
      actionTypes?: string[],
    ) => {
      setGenerating(true);
      try {
        const data = await runJob<{ proposals: RuleProposal[] }>(
          `/api/domains/${domainId}/jobs/generate`,
          {
            description,
            providerId,
            modelId,
            roles: roles ?? [],
            actionTypes: actionTypes ?? [],
          },
          setJobId,
        );
        setProposals(
          (data.proposals ?? []).map((p: Omit<RuleProposal, "id">) => ({
            ...p,
            id: crypto.randomUUID(),
          })),
        );
        setVerificationResults(new Map());
        return data.proposals as RuleProposal[];
      } finally {
        setGenerating(false);
      }
    },
    [domainId],
  );

  const refine = useCallback(
    async (
      index: number,
      feedback: string,
      providerId: string,
      modelId: string,
    ) => {
      const proposal = proposals[index];
      if (!proposal) return;

      const data = await runJob<{ proposals: RuleProposal[] }>(
        `/api/domains/${domainId}/jobs/refine`,
        {
          proposal,
          feedback,
          providerId,
          modelId,
        },
        setJobId,
      );
      const first = data.proposals[0];
      if (first) {
        setProposals((prev) => {
          return prev.map((p) =>
            p.id === proposal.id ? { ...first, id: crypto.randomUUID() } : p,
          );
        });
        setVerificationResults(new Map());
      }
    },
    [domainId, proposals],
  );

  const verify = useCallback(
    async (index: number) => {
      const proposal = proposals[index];
      if (!proposal) return;

      const resp = await editorFetch(`/api/domains/${domainId}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meldExpression: proposal.meldExpression,
          modality: proposal.modality,
          agentRole: proposal.agentRole,
          codeOfConduct: proposal.codeOfConduct,
          actionType: proposal.actionType,
          propositionParameters: proposal.propositionParameters,
          defeasible: proposal.defeasible,
        }),
      });
      const result: VerificationResult = await resp.json();
      const current = useDomainStore
        .getState()
        .domains.find((d) => d.id === domainId);
      if (result.revision !== current?.revision)
        throw new Error("Domain changed. Verify again.");
      setVerificationResults((prev) => new Map(prev).set(proposal.id, result));
      return result;
    },
    [domainId, proposals],
  );

  const removeProposal = useCallback((index: number) => {
    setProposals((prev) => prev.filter((_, i) => i !== index));
    setVerificationResults(new Map());
  }, []);

  const accept = useCallback(
    async (index: number) => {
      const proposal = proposals[index];
      const domain = useDomainStore
        .getState()
        .domains.find((d) => d.id === domainId);
      if (!proposal || !domain)
        throw new Error("Domain or proposal unavailable");
      const response = await editorFetch(
        `/api/domains/${domainId}/proposals/accept`,
        {
          method: "POST",
          body: JSON.stringify({ ...proposal, revision: domain.revision }),
        },
      );
      const saved: Domain = await response.json();
      useDomainStore.getState().updateDomain(domainId, saved);
      removeProposal(index);
    },
    [domainId, proposals, removeProposal],
  );

  return {
    proposals,
    recoveryError,
    generating,
    jobId,
    cancel: () =>
      jobId
        ? editorFetch(`/api/jobs/${jobId}/cancel`, { method: "POST" })
        : Promise.resolve(),
    verificationResults,
    generate,
    accept,
    refine,
    verify,
    removeProposal,
    setProposals,
  };
}
