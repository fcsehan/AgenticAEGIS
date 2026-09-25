import { useEditorText } from "@/hooks/useEditorText";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ProviderSelector } from "@/components/authoring/ProviderSelector";
import { requestJson } from "@/api/client";
import { runJob } from "@/api/jobs";
import { useProjectStore } from "@/store/projectStore";
import { useDomainStore } from "@/store/domainStore";
import type { Project } from "@/types/domain";

interface Result {
  summary: string;
  reports: Record<string, string>;
  files: Record<string, string>;
}
export function DocumentImport() {
  const tx = useEditorText();
  const project = useProjectStore((s) => s.project);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [language, setLanguage] = useState("en");
  const [sourceType, setSourceType] = useState("text");
  const [jobId, setJobId] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [adopted, setAdopted] = useState(false);
  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    setAdopted(false);
    try {
      setResult(
        await runJob<Result>(
          "/api/dip/jobs",
          {
            name,
            title,
            content,
            sourceType,
            language,
            providerId: provider,
            modelId: model,
          },
          setJobId,
        ),
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : tx("Document processing failed"),
      );
    } finally {
      setBusy(false);
    }
  }
  async function adopt() {
    setBusy(true);
    setError("");
    try {
      const saved = await requestJson<Project>(`/api/dip/jobs/${jobId}/adopt`, {
        method: "POST",
      });
      useProjectStore.getState().setProject(saved);
      useDomainStore.getState().setDomains(saved.domains);
      setAdopted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Adoption failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-4xl space-y-5 p-8">
      <Link to="/"> {tx("← Projects")} </Link>
      <h1 className="text-2xl font-semibold">
        {" "}
        {tx("Rules from documents")}{" "}
      </h1>
      <p>
        {" "}
        {tx("Project:")} {project?.name ?? "Open a project first"}{" "}
        {tx(
          ". DIP creates a new draft. Existing domains are not overwritten.",
        )}{" "}
      </p>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      <ProviderSelector
        selectedProviderId={provider}
        selectedModelId={model}
        onProviderChange={setProvider}
        onModelChange={setModel}
      />
      <label className="block">
        {" "}
        {tx("Domain identifier")}{" "}
        <input
          className="ml-3 rounded border p-2"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="organisation-policy"
        />
      </label>
      <label className="block">
        {" "}
        {tx("Document title")}{" "}
        <input
          className="ml-3 rounded border p-2"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label className="block">
        {" "}
        {tx("Language")}{" "}
        <select
          className="ml-3 rounded border p-2"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          <option value="en"> {tx("English")} </option>
          <option value="auto"> {tx("Automatic")} </option>
        </select>
      </label>
      <label className="block">
        {" "}
        {tx("Text or HTML file (up to 500 KB)")}{" "}
        <input
          type="file"
          accept=".txt,.md,.html,.htm"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            if (file.size > 500_000) {
              setError(tx("File is too large"));
              return;
            }
            setContent(await file.text());
            setTitle(file.name);
            setSourceType(/\.html?$/.test(file.name) ? "html" : "text");
          }}
        />
      </label>
      <label className="block">
        {" "}
        {tx("Document content")}{" "}
        <textarea
          className="block min-h-60 w-full rounded border p-3"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
      </label>
      <button
        disabled={
          busy || !project || !content || !title || !name || !provider || !model
        }
        onClick={run}
      >
        {" "}
        {tx("Review document and extract rules")}{" "}
      </button>
      {busy && jobId && (
        <p role="status">
          {" "}
          {tx("Job")} {jobId} {tx("is running.")}{" "}
          <button
            onClick={() => {
              requestJson(`/api/jobs/${jobId}/cancel`, {
                method: "POST",
              }).catch((e: Error) => setError(e.message));
            }}
          >
            {" "}
            {tx("Cancel")}{" "}
          </button>
        </p>
      )}
      {result && (
        <section className="space-y-3">
          <h2 className="font-semibold"> {tx("Review result")} </h2>
          <pre className="whitespace-pre-wrap">{result.summary}</pre>
          {Object.entries({ ...result.reports, ...result.files }).map(
            ([filename, text]) => (
              <details key={filename}>
                <summary>{filename}</summary>
                <pre className="overflow-auto whitespace-pre-wrap text-xs">
                  {text}
                </pre>
              </details>
            ),
          )}
          <button disabled={busy || adopted} onClick={adopt}>
            {adopted
              ? tx("Adopted as draft")
              : tx("Adopt reviewed result as a new domain")}
          </button>
        </section>
      )}
    </main>
  );
}
