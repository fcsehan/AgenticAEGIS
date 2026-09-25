import { useEditorText } from "@/hooks/useEditorText";
import { useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import { useDomainStore } from "@/store/domainStore";

interface ScenarioSet {
  revision: string;
  scenarios: unknown[];
}
export function ScenarioPanel({ domainId }: { domainId: string }) {
  const tx = useEditorText();
  const domain = useDomainStore((s) =>
    s.domains.find((d) => d.id === domainId),
  );
  const [text, setText] = useState("[]");
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const endpoint = `/api/domains/${domainId}/scenarios`;
  useEffect(() => {
    requestJson<ScenarioSet>(endpoint)
      .then((r) => setText(JSON.stringify(r.scenarios, null, 2)))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoaded(true));
  }, [endpoint]);
  function download() {
    try {
      const scenarios = JSON.parse(text);
      const url = URL.createObjectURL(
        new Blob(
          [JSON.stringify({ revision: domain?.revision, scenarios }, null, 2)],
          { type: "application/json" },
        ),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${domainId}-scenarios.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }
  async function run() {
    setBusy(true);
    setError("");
    setResult("");
    try {
      await requestJson(endpoint, {
        method: "PUT",
        body: JSON.stringify({
          revision: domain?.revision,
          scenarios: JSON.parse(text),
        }),
      });
      const response = await requestJson(`${endpoint}/run`, { method: "POST" });
      setResult(JSON.stringify(response, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Test failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-3 border-t p-5">
      <h2 className="font-semibold"> {tx("Saved test scenarios")} </h2>
      <p>
        {" "}
        {tx(
          "Each case has an ID, name, expected decision and exactly one action or plan. Results apply only to the tested MELD revision.",
        )}{" "}
      </p>
      <details>
        <summary> {tx("JSON example")} </summary>
        <pre className="overflow-auto text-xs">
          {JSON.stringify(
            [
              {
                id: "test-1",
                name: "Permitted action",
                expected: "PERMITTED",
                action: { agent: "role", actionType: "action", parameters: {} },
              },
            ],
            null,
            2,
          )}
        </pre>
        <p>
          {" "}
          {tx(
            "For plans, replace action with plan containing steps. Each step has action_type, agent_id and proposition, optionally pre_state, post_state and scheduled_duration_s.",
          )}{" "}
        </p>
      </details>
      <label className="block">
        {" "}
        {tx("Scenarios (JSON)")}{" "}
        <textarea
          disabled={!loaded || busy}
          className="block min-h-60 w-full rounded border p-3 font-mono text-xs"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setResult("");
          }}
        />
      </label>
      <button
        className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
        disabled={busy || !loaded}
        onClick={run}
      >
        {busy ? tx("Checking…") : tx("Save and run scenarios")}
      </button>
      <button
        className="ml-3 rounded border px-4 py-2"
        disabled={!loaded || busy}
        onClick={download}
      >
        {tx("Export scenarios")}
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
