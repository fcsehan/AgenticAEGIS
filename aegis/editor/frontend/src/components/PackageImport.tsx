import { useEditorText } from "@/hooks/useEditorText";
import { useState } from "react";
import { requestJson } from "@/api/client";
import type { Project } from "@/types/domain";
import { useDomainStore } from "@/store/domainStore";
import { useProjectStore } from "@/store/projectStore";
interface Preview {
  revision: string;
  files: string[];
  collision: boolean;
}
export function PackageImport() {
  const tx = useEditorText();
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  async function inspect() {
    try {
      setPreview(
        await requestJson<Preview>("/api/project/import/preview", {
          method: "POST",
          body: JSON.stringify({ name, files }),
        }),
      );
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : tx("Import validation failed"),
      );
    }
  }
  async function adopt() {
    try {
      const project = await requestJson<Project>("/api/project/import", {
        method: "POST",
        body: JSON.stringify({
          name,
          files,
          previewRevision: preview?.revision,
        }),
      });
      useProjectStore.getState().setProject(project);
      useDomainStore.getState().setDomains(project.domains);
      setFiles({});
      setPreview(null);
      setName("");
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Import failed"));
    }
  }
  return (
    <details className="my-4 rounded border p-4">
      <summary> {tx("Import MELD package")} </summary>
      <p>
        {" "}
        {tx(
          "Choose .meld files or a previously exported .json package. Existing domains are not overwritten.",
        )}{" "}
      </p>
      <label className="block">
        {" "}
        {tx("New directory name")}{" "}
        <input
          className="block rounded border p-2"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setPreview(null);
          }}
        />
      </label>
      <label className="block">
        {" "}
        {tx("Files")}{" "}
        <input
          type="file"
          accept=".meld,.json"
          multiple
          onChange={async (e) => {
            try {
              const selected = Array.from(e.target.files ?? []);
              if (
                selected.length > 50 ||
                selected.some((f) => f.size > 2_000_000)
              )
                throw new Error("Maximal 50 Dateien mit je 2 MB.");
              const incoming: Record<string, string> = {};
              for (const file of selected) {
                if (file.name.endsWith(".json"))
                  Object.assign(
                    incoming,
                    (
                      JSON.parse(await file.text()) as {
                        files: Record<string, string>;
                      }
                    ).files,
                  );
                else incoming[file.name] = await file.text();
              }
              setFiles(incoming);
              setPreview(null);
              setError("");
            } catch (error) {
              setError(
                error instanceof Error
                  ? error.message
                  : tx("Cannot read file"),
              );
            }
          }}
        />
      </label>
      <button disabled={!name || !Object.keys(files).length} onClick={inspect}>
        {" "}
        {tx("Check package")}{" "}
      </button>
      {preview && (
        <>
          <pre className="text-xs">{preview.files.join("\n")}</pre>
          <p>
            {preview.collision
              ? tx("Name collision: choose another directory name.")
              : tx("Compiled. Ready to adopt as a new draft.")}
          </p>
          <button disabled={preview.collision} onClick={adopt}>
            {" "}
            {tx("Confirm import")}{" "}
          </button>
        </>
      )}
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
    </details>
  );
}
