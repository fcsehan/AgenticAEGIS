import { useState } from "react";
import { requestJson } from "@/api/client";
import { useEditorText } from "@/hooks/useEditorText";
import type { Domain } from "@/types/domain";

export function PlanTestConsole({ domain }: { domain: Domain }) {
  const tx = useEditorText();
  const [agent, setAgent] = useState("");
  const [action, setAction] = useState("");
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [plan, setPlan] = useState('{"steps": [], "initial_state": {}}');
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  function addStep() {
    try {
      const current = JSON.parse(plan) as { steps: unknown[] };
      current.steps.push({
        step_id: crypto.randomUUID(),
        agent_id: agent,
        action_type: action,
        proposition: parameters,
        context: {},
        pre_state: {},
        post_state: {},
      });
      setPlan(JSON.stringify(current, null, 2));
      setResult("");
      setError("");
    } catch {
      setError(tx("Plan must be a JSON object with a steps array."));
    }
  }
  async function run() {
    setBusy(true);
    setError("");
    setResult("");
    try {
      setResult(
        JSON.stringify(
          await requestJson(`/api/domains/${domain.id}/plan_check`, {
            method: "POST",
            body: plan,
          }),
          null,
          2,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Test failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-3 border-t p-5">
      <h2 className="font-semibold">{tx("Plan test")}</h2>
      <label className="block">
        {tx("Role")}
        <select
          className="block rounded border p-2"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">{tx("Select…")}</option>
          {domain.roles.map((r) => (
            <option key={r.id} value={r.name}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        {tx("Action")}
        <select
          className="block rounded border p-2"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setParameters(
              Object.fromEntries(
                (domain.actionSchemas?.[e.target.value] ?? []).map((p) => [
                  p.name,
                  "",
                ]),
              ),
            );
          }}
        >
          <option value="">{tx("Select…")}</option>
          {domain.actionTypes?.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </label>
      {Object.entries(parameters).map(([name, value]) => (
        <label className="block" key={name}>
          {name}
          <input
            className="block rounded border p-2"
            value={value}
            onChange={(e) =>
              setParameters({ ...parameters, [name]: e.target.value })
            }
          />
        </label>
      ))}
      <button disabled={!agent || !action || busy} onClick={addStep}>
        {tx("Add step")}
      </button>
      <p>
        {tx(
          "Edit states, context, duration and order in the plan JSON. AEGIS does not generate a plan.",
        )}
      </p>
      <label className="block">
        {tx("Plan (JSON)")}
        <textarea
          className="block min-h-60 w-full rounded border p-3 font-mono text-xs"
          value={plan}
          onChange={(e) => {
            setPlan(e.target.value);
            setResult("");
          }}
        />
      </label>
      <button disabled={busy} onClick={run}>
        {tx("Check plan with Guard")}
      </button>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {result && (
        <pre
          role="status"
          className="overflow-auto whitespace-pre-wrap text-xs"
        >
          {result}
        </pre>
      )}
    </section>
  );
}
