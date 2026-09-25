import { editorFetch } from "@/api/client";
import { useState, useCallback } from "react";
import type { Action, Verdict } from "@/types/domain";

interface TestConsoleState {
  action: Partial<Action>;
  verdict: Verdict | null;
  history: Verdict[];
  loading: boolean;
  error: string | null;
  setAction: (action: Partial<Action>) => void;
  runCheck: (domainId: string) => Promise<void>;
  clearHistory: () => void;
}

export function useTestConsole(): TestConsoleState {
  const [action, setAction] = useState<Partial<Action>>({});
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [history, setHistory] = useState<Verdict[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runCheck = useCallback(
    async (domainId: string) => {
      if (!action.agent || !action.actionType) return;

      setLoading(true);
      setError(null);
      setVerdict(null);
      try {
        const res = await editorFetch(`/api/domains/${domainId}/check`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent: action.agent,
            actionType: action.actionType,
            description: action.description ?? "",
            parameters: action.parameters ?? {},
          }),
        });
        const data = await res.json();
        const v: Verdict = {
          decision: data.decision,
          justificationChain: data.justificationChain ?? [],
          appliedRules: data.normsApplied ?? [],
          explanation: data.explanation ?? "",
          timestamp: new Date().toISOString(),
        };
        setVerdict(v);
        setHistory((prev) => [v, ...prev].slice(0, 10));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Guard API unavailable");
      } finally {
        setLoading(false);
      }
    },
    [action],
  );

  const clearHistory = useCallback(() => {
    setHistory([]);
    setVerdict(null);
  }, []);

  return {
    action,
    verdict,
    history,
    loading,
    error,
    setAction,
    runCheck,
    clearHistory,
  };
}
