import { useEditorText } from "@/hooks/useEditorText";
import { parseVerdict } from "@/api/contracts";
import { editorFetch } from "@/api/client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDomainStore } from "@/store/domainStore";
import { Button } from "./ui/Button";
import { Select } from "./ui/Select";
import { Input } from "./ui/Input";
import { VerdictDisplay } from "./VerdictDisplay";
import { ReasoningChain } from "./ReasoningChain";
import type { Action, Verdict } from "@/types/domain";

interface TestConsoleProps {
  domainId: string;
  onClose?: () => void;
  prefillAction?: Partial<Action>;
}

export function TestConsole({
  domainId,
  onClose,
  prefillAction,
}: TestConsoleProps) {
  const tx = useEditorText();
  const { t } = useTranslation();
  const { domains } = useDomainStore();
  const domain = domains.find((d) => d.id === domainId);

  const [agent, setAgent] = useState(prefillAction?.agent ?? "");
  const [actionType, setActionType] = useState(prefillAction?.actionType ?? "");
  const [params, setParams] = useState<Record<string, string>>(
    prefillAction?.parameters ?? {},
  );
  const [context, setContext] = useState("{}");
  const [paramKey, setParamKey] = useState("");
  const [paramValue, setParamValue] = useState("");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<Verdict[]>([]);

  const roles = domain?.roles ?? [];

  async function handleCheck() {
    setLoading(true);
    setError(null);
    setVerdict(null);
    try {
      const res = await editorFetch(`/api/domains/${domainId}/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent,
          actionType,
          parameters: params,
          context: JSON.parse(context),
        }),
      });
      const data = parseVerdict(await res.json());
      const v: Verdict = {
        decision: data.decision,
        reasonType: data.reasonType,
        revision: data.revision,
        justificationChain: data.justificationChain ?? [],
        appliedRules: Array.isArray(data.normsApplied)
          ? data.normsApplied.map(String)
          : [],
        explanation:
          typeof data.explanation === "string" ? data.explanation : "",
        timestamp: new Date().toISOString(),
      };
      setVerdict(v);
      setHistory((prev) => [v, ...prev].slice(0, 10));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Guard API unavailable");
    } finally {
      setLoading(false);
    }
  }

  function addParam() {
    if (paramKey.trim()) {
      setParams((prev) => ({ ...prev, [paramKey.trim()]: paramValue }));
      setParamKey("");
      setParamValue("");
    }
  }

  function removeParam(key: string) {
    setParams((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  return (
    <div className="flex flex-col h-full bg-white border-l border-slate-200">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
        <h2 className="text-sm font-semibold text-slate-900">
          {t("validation.testConsole", "Test Console")}
        </h2>
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600"
          >
            ✕
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            {t("common.agent", "Agent")}
          </label>
          <Select
            value={agent}
            onChange={(e) => setAgent(e.target.value)}
            options={[
              { value: "", label: "Select agent…" },
              ...roles.map((r) => ({ value: r.name, label: r.name })),
            ]}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            {t("common.actionType", "Action Type")}
          </label>
          <Input
            list="domain-action-types"
            value={actionType}
            onChange={(e) => {
              setActionType(e.target.value);
              setParams(
                Object.fromEntries(
                  (domain?.actionSchemas?.[e.target.value] ?? []).map((p) => [
                    p.name,
                    "",
                  ]),
                ),
              );
            }}
            placeholder={tx("e.g. shareIntelligence")}
          />
        </div>

        <datalist id="domain-action-types">
          {domain?.actionTypes?.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </datalist>
        <details>
          <summary> {tx("Context (JSON)")} </summary>
          <textarea
            aria-label={tx("Context (JSON)")}
            className="w-full rounded border p-2 font-mono text-xs"
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />
        </details>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            {t("common.parameters", "Parameters")}
          </label>
          {Object.entries(params).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 mb-1">
              <span className="text-xs font-mono text-slate-700">
                {k}: {v}
              </span>
              <button
                onClick={() => removeParam(k)}
                className="text-xs text-red-400 hover:text-red-600"
              >
                ✕
              </button>
            </div>
          ))}
          <div className="flex gap-2 mt-1">
            <Input
              value={paramKey}
              onChange={(e) => setParamKey(e.target.value)}
              placeholder={tx("key")}
              className="flex-1"
            />
            <Input
              value={paramValue}
              onChange={(e) => setParamValue(e.target.value)}
              placeholder={tx("value")}
              className="flex-1"
            />
            <Button onClick={addParam} variant="secondary" size="sm">
              +
            </Button>
          </div>
        </div>

        <Button
          onClick={handleCheck}
          disabled={!agent || !actionType || loading}
          className="w-full"
        >
          {loading
            ? t("validation.checking", "Checking...")
            : t("validation.checkGuard", "▶ Check Guard")}
        </Button>

        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
        {verdict && (
          <div className="space-y-3">
            <p className="text-xs">
              {verdict.reasonType} {tx("· Revision")} {verdict.revision}
            </p>
            <VerdictDisplay verdict={verdict} />
            <ReasoningChain chain={verdict.justificationChain} />
          </div>
        )}

        {history.length > 1 && (
          <div className="mt-6">
            <h3 className="text-xs font-medium text-slate-500 mb-2">
              {t("validation.history", "History")}
            </h3>
            {history.slice(1).map((v, i) => (
              <div
                key={i}
                className="text-xs text-slate-500 py-1 border-b border-slate-100"
              >
                <span
                  className={
                    v.decision === "PERMITTED"
                      ? "text-emerald-600"
                      : v.decision === "FORBIDDEN"
                        ? "text-red-600"
                        : "text-amber-600"
                  }
                >
                  {v.decision}
                </span>{" "}
                — {v.timestamp}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
