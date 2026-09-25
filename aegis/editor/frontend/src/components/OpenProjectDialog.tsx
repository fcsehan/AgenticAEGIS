import { useEditorText } from "@/hooks/useEditorText";
import type { Project } from "@/types/domain";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "@phosphor-icons/react";
import { Modal, Button, Input } from "@/components/ui";
import { useProjectStore } from "@/store/projectStore";
import { useDomainStore } from "@/store/domainStore";
import { api, requestJson } from "@/api/client";

interface OpenProjectDialogProps {
  open: boolean;
  onClose: () => void;
}

export function OpenProjectDialog({ open, onClose }: OpenProjectDialogProps) {
  const tx = useEditorText();
  const { t } = useTranslation("domains");
  const { t: tc } = useTranslation("common");
  const { setProject, setLoading, setError } = useProjectStore();
  const { setDomains } = useDomainStore();
  const [create, setCreate] = useState(false);
  const [path, setPath] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleOpen = async () => {
    if (!path.trim()) return;

    setIsLoading(true);
    setLocalError(null);
    setLoading(true);

    try {
      const project = create
        ? await requestJson<Project>("/api/project/create", {
            method: "POST",
            body: JSON.stringify({ path: path.trim() }),
          })
        : await api.openProject(path.trim());
      setProject(project);
      setDomains(project.domains);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to open project";
      setLocalError(msg);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={t("openProject")}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-500">{t("openProjectDesc")}</p>
        <label>
          <input
            type="checkbox"
            checked={create}
            onChange={(e) => setCreate(e.target.checked)}
          />{" "}
          {tx("Create a new project directory")}{" "}
        </label>
        <Input
          id="project-path"
          label={t("projectPath")}
          value={path}
          onChange={(e) => {
            setPath(e.target.value);
            setLocalError(null);
          }}
          placeholder="/path/to/your/domain/project"
          className="font-mono text-xs"
          error={localError ?? undefined}
        />
        <div className="rounded-md border border-border bg-surface-tertiary p-3">
          <p className="text-[11px] text-slate-400">{t("projectPathHint")}</p>
          <pre className="mt-1 font-mono text-[11px] text-slate-500">
            {
              "project/\n├── meld/\n│   ├── *-LogicMt.meld\n│   ├── *-InferenceMt.meld\n│   └── *VocabMt.meld\n└── bps/  (optional)"
            }
          </pre>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={handleOpen} disabled={!path.trim() || isLoading}>
            <FolderOpen size={16} />
            {isLoading ? tc("loading") : t("openProject")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
