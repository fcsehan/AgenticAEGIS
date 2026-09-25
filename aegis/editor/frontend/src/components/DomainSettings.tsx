import { useEditorText } from "@/hooks/useEditorText";
import { useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import type { Domain } from "@/types/domain";
import { useDomainStore } from "@/store/domainStore";
interface Metadata {
  metadataRevision: number;
  name: string;
  description: string;
  archived: boolean;
  classification: string;
}
export function DomainSettings({ domain }: { domain: Domain }) {
  const tx = useEditorText();
  const [data, setData] = useState<Metadata | null>(null);
  const [error, setError] = useState("");
  const endpoint = `/api/domains/${domain.id}/metadata`;
  useEffect(() => {
    requestJson<Metadata>(endpoint)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [endpoint]);
  async function save() {
    try {
      const saved = await requestJson<Domain>(endpoint, {
        method: "PUT",
        body: JSON.stringify(data),
      });
      useDomainStore.getState().updateDomain(domain.id, saved);
      setData(await requestJson<Metadata>(endpoint));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Save failed"));
    }
  }
  async function download() {
    try {
      const result = await requestJson(`/api/domains/${domain.id}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(result, null, 2)], {
          type: "application/json",
        }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `${domain.id}.meld-package.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Export failed"));
    }
  }
  return (
    <details className="border-b p-4">
      <summary> {tx("Domain settings and MELD export")} </summary>
      {data && (
        <div className="space-y-3 py-3">
          <label className="block">
            {" "}
            {tx("Name")}{" "}
            <input
              className="block rounded border p-2"
              value={data.name}
              onChange={(e) => setData({ ...data, name: e.target.value })}
            />
          </label>
          <label className="block">
            {" "}
            {tx("Description")}{" "}
            <textarea
              className="block w-full rounded border p-2"
              value={data.description}
              onChange={(e) =>
                setData({ ...data, description: e.target.value })
              }
            />
          </label>
          <label className="block">
            {" "}
            {tx("Information classification for inference")}{" "}
            <select
              className="block rounded border p-2"
              value={data.classification}
              onChange={(e) =>
                setData({ ...data, classification: e.target.value })
              }
            >
              <option value="confidentialData">
                {" "}
                {tx("Confidential (default)")}{" "}
              </option>
              <option value="internalData"> {tx("Internal")} </option>
              <option value="publicData"> {tx("Public")} </option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={data.archived}
              onChange={(e) => setData({ ...data, archived: e.target.checked })}
            />{" "}
            {tx("Archived (recoverable)")}{" "}
          </label>
          <p className="text-xs">
            {" "}
            {tx(
              "Archiving blocks new releases. An active Guard version remains active until explicitly replaced.",
            )}{" "}
          </p>
          <div className="flex gap-4">
            <button onClick={save}> {tx("Save metadata")} </button>
            <button onClick={download}>
              {" "}
              {tx("Download MELD package")}{" "}
            </button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
    </details>
  );
}
