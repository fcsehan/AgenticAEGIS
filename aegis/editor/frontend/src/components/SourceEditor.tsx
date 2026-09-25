import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useEditorText } from "@/hooks/useEditorText";
import { useSessionDraft } from "@/hooks/useSessionDraft";
import { useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import { useDomainStore } from "@/store/domainStore";
import type { Domain } from "@/types/domain";

interface Sources {
  sources: Record<string, string>;
  revision: string;
}
export function SourceEditor({ domainId }: { domainId: string }) {
  const tx = useEditorText();
  const [data, setData, recoveryError, clearRecovery] =
    useSessionDraft<Sources | null>(`sources:${domainId}`, null);
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const endpoint = `/api/domains/${encodeURIComponent(domainId)}/sources`;
  useEffect(() => {
    requestJson<Sources>(endpoint)
      .then((saved) => {
        if (data && JSON.stringify(data) !== JSON.stringify(saved)) {
          setDirty(true);
          setNotice(
            tx(
              "Recovered unsaved browser draft. Saving is blocked if its revision is stale.",
            ),
          );
        } else setData(saved);
      })
      .catch((e: Error) => setError(e.message));
  }, [endpoint]);
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (dirty) e.preventDefault();
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [dirty]);
  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const domain = await requestJson<Domain>(endpoint, {
        method: "PUT",
        body: JSON.stringify(data),
      });
      useDomainStore.getState().updateDomain(domainId, domain);
      setData(await requestJson<Sources>(endpoint));
      setDirty(false);
      clearRecovery();
      setNotice(
        tx(
          "MELD draft saved and its Guard reloaded. It has not been published or activated.",
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Save failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-4 p-5">
      <h2 className="font-semibold"> {tx("MELD sources")} </h2>
      <p>
        {" "}
        {tx(
          "Edit sources without conversion to the legacy rule format. Saving checks the complete files and updates the preview Guard.",
        )}{" "}
      </p>
      {recoveryError && <p role="alert">{recoveryError}</p>}
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {data &&
        Object.entries(data.sources).map(([name, content]) => (
          <label className="block" key={name}>
            {name}
            <textarea
              className="mt-2 block min-h-64 w-full rounded border p-3 font-mono text-xs"
              value={content}
              spellCheck={false}
              onChange={(e) => {
                setData({
                  ...data,
                  sources: { ...data.sources, [name]: e.target.value },
                });
                setDirty(true);
                setNotice("");
              }}
            />
          </label>
        ))}
      <button
        disabled={!dirty || busy}
        onClick={save}
        className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
      >
        {busy
          ? tx("Checking and saving…")
          : tx("Check and save draft")}
      </button>
      <button
        className="ml-3"
        disabled={busy}
        onClick={() => {
          if (
            window.confirm(
              tx(
                "Discard the browser draft and reload saved sources?",
              ),
            )
          ) {
            requestJson<Sources>(endpoint)
              .then((saved) => {
                setData(saved);
                setDirty(false);
                setNotice("");
              })
              .catch((e: Error) => setError(e.message));
          }
        }}
      >
        {" "}
        {tx("Load saved version")}{" "}
      </button>
      <span className="ml-3 text-sm">
        {dirty ? tx("Unsaved changes") : tx("Saved version")}
      </span>
    </section>
  );
}
