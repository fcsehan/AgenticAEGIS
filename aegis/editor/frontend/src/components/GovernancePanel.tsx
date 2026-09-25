import { useDomainStore } from "@/store/domainStore";
import { useEditorText } from "@/hooks/useEditorText";
import { useCallback, useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import type { Domain } from "@/types/domain";

interface Governance {
  canPublish: boolean;
  reviewCurrent: boolean;
  activeVersion: string | null;
  versions: {
    version: string;
    revision: string;
    actor: string;
    message: string;
    timestamp: string;
  }[];
  evidence: {
    revision: string;
    checks: Record<string, boolean>;
    document: string;
    documentHash: string;
  };
}
export function GovernancePanel({ domain }: { domain: Domain }) {
  const tx = useEditorText();
  const endpoint = `/api/domains/${domain.id}/governance`;
  const [data, setData] = useState<Governance | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [ack, setAck] = useState(false);
  const load = useCallback(
    () =>
      requestJson<Governance>(endpoint)
        .then(setData)
        .catch((e: Error) => setError(e.message)),
    [endpoint],
  );
  useEffect(() => {
    load();
  }, [load, domain.revision]);
  async function operation(path: string, body: unknown) {
    setBusy(true);
    setError("");
    try {
      setData(
        await requestJson<Governance>(`${endpoint}/${path}`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      );
      useDomainStore
        .getState()
        .updateDomain(
          domain.id,
          await requestJson<Domain>(`/api/domains/${domain.id}`),
        );
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Operation failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4 p-5">
      <h2 className="font-semibold">
        {" "}
        {tx("Review, publication and activation")}{" "}
      </h2>
      <p>
        {" "}
        {tx(
          "Local single-user mode: reviews are recorded as localOperator. This does not demonstrate independent review by a second person.",
        )}{" "}
      </p>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {!data ? (
        <p> {tx("Loading governance…")} </p>
      ) : (
        <>
          <p>
            {" "}
            {tx("Draft:")} <code>{data.evidence.revision.slice(0, 12)}</code>{" "}
            {tx("· Active version in editor runtime:")}{" "}
            <strong>{data.activeVersion ?? "none"}</strong>
          </p>
          <ul>
            {Object.entries(data.evidence.checks).map(([name, ok]) => (
              <li key={name}>
                {ok ? "✓" : "✕"} {name}
              </li>
            ))}
          </ul>
          <p>
            {" "}
            {tx("Review for this revision:")}{" "}
            {data.reviewCurrent ? tx("current") : tx("missing or stale")}
          </p>
          <details>
            <summary> {tx("Documentation of the exact MELD revision")} </summary>
            <pre className="overflow-auto whitespace-pre-wrap text-xs">
              {data.evidence.document}
            </pre>
          </details>
          <label className="block">
            {" "}
            {tx("Review / change description")}{" "}
            <textarea
              className="block w-full rounded border p-2"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </label>
          <label className="block">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
            />{" "}
            {tx(
              "I reviewed the rules and tests. Tests demonstrate the declared cases, not complete coverage of every situation.",
            )}{" "}
          </label>
          <button
            disabled={
              busy ||
              !ack ||
              message.length < 5 ||
              !Object.values(data.evidence.checks).every(Boolean)
            }
            onClick={() =>
              operation("review", {
                revision: data.evidence.revision,
                message,
                acknowledgeLimits: ack,
              })
            }
          >
            {" "}
            {tx("Confirm review")}{" "}
          </button>
          <label className="block">
            {" "}
            {tx("New version")}{" "}
            <input
              className="ml-3 rounded border p-2"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </label>
          <button
            disabled={busy || !data.canPublish || !message}
            onClick={() =>
              operation("publish", {
                revision: data.evidence.revision,
                version,
                message,
              })
            }
          >
            {" "}
            {tx("Publish snapshot")}{" "}
          </button>
          <h3 className="font-semibold"> {tx("Published versions")} </h3>
          {data.versions.map((v) => (
            <article
              key={v.version}
              className="flex items-center justify-between rounded border p-3"
            >
              <div>
                <strong>{v.version}</strong> · {v.revision.slice(0, 12)}
                <p>{v.message}</p>
                <small>
                  {v.actor} · {new Date(v.timestamp).toLocaleString()}
                </small>
              </div>
              <button
                disabled={busy || data.activeVersion === v.version}
                onClick={() => {
                  if (
                    window.confirm(
                      `Activate version ${v.version} in the editor runtime? External Guard instances are unaffected.`,
                    )
                  )
                    operation("activate", { version: v.version });
                }}
              >
                {data.activeVersion === v.version
                  ? tx("Active")
                  : tx("Activate / rollback")}
              </button>
            </article>
          ))}
          <p>
            {" "}
            {tx(
              "Activation applies to this editor's runtime API. Draft tests continue to use the current draft.",
            )}{" "}
          </p>
        </>
      )}
    </section>
  );
}
