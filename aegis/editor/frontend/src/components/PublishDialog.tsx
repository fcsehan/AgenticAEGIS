import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Button, Input } from "@/components/ui";
import type { Domain } from "@/types/domain";
import { useDomainStore } from "@/store/domainStore";
import { useGovernanceStore } from "@/store/governanceStore";

interface PublishDialogProps {
  open: boolean;
  onClose: () => void;
  domain: Domain;
}

export function PublishDialog({ open, onClose, domain }: PublishDialogProps) {
  const { t } = useTranslation("governance");
  const { t: tc } = useTranslation("common");
  const updateDomain = useDomainStore((s) => s.updateDomain);
  const addVersion = useGovernanceStore((s) => s.addVersion);
  const [changeLog, setChangeLog] = useState("");

  const nextVersion = (() => {
    if (!domain.version) return "1.0.0";
    const parts = domain.version.split(".");
    return `${parts[0]}.${Number(parts[1]) + 1}.0`;
  })();

  const handlePublish = () => {
    updateDomain(domain.id, {
      status: "Published",
      version: nextVersion,
      lastModified: new Date().toISOString(),
    });
    addVersion(domain.id, {
      id: crypto.randomUUID(),
      version: nextVersion,
      status: "Published",
      author: "Current User",
      timestamp: new Date().toISOString(),
      changeLog: changeLog || "Published new version",
    });
    setChangeLog("");
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={t("publishDomain")}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-600">{t("publishConfirm")}</p>
        <div className="rounded-md bg-surface-tertiary p-3">
          <p className="text-xs text-slate-500">New version</p>
          <p className="font-mono text-sm font-medium">{nextVersion}</p>
        </div>
        <Input
          id="changelog"
          label={t("changeLog")}
          value={changeLog}
          onChange={(e) => setChangeLog(e.target.value)}
          placeholder="Describe the changes..."
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={handlePublish}>{t("publish")}</Button>
        </div>
      </div>
    </Modal>
  );
}
