import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Button } from "@/components/ui";
import type { Domain, DomainVersion } from "@/types/domain";
import { useDomainStore } from "@/store/domainStore";

interface RollbackDialogProps {
  open: boolean;
  onClose: () => void;
  domain: Domain;
  versions: DomainVersion[];
}

export function RollbackDialog({ open, onClose, domain, versions }: RollbackDialogProps) {
  const { t } = useTranslation("governance");
  const { t: tc } = useTranslation("common");
  const updateDomain = useDomainStore((s) => s.updateDomain);
  const [selectedVersion, setSelectedVersion] = useState<string | null>(null);

  const archivedVersions = versions.filter((v) => v.status === "Archived");

  const handleRollback = () => {
    if (!selectedVersion) return;
    const target = versions.find((v) => v.id === selectedVersion);
    if (!target) return;

    updateDomain(domain.id, {
      version: target.version,
      lastModified: new Date().toISOString(),
    });
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={t("rollback")}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-600">
          {t("rollbackConfirm", { version: selectedVersion ?? "..." })}
        </p>
        <div className="flex flex-col gap-2">
          {archivedVersions.map((v) => (
            <label
              key={v.id}
              className={`flex cursor-pointer items-center gap-3 rounded-md border p-3 text-sm transition-colors ${
                selectedVersion === v.id
                  ? "border-accent bg-accent-subtle"
                  : "border-border hover:bg-surface-secondary"
              }`}
            >
              <input
                type="radio"
                name="rollback-version"
                checked={selectedVersion === v.id}
                onChange={() => setSelectedVersion(v.id)}
                className="accent-accent"
              />
              <div>
                <span className="font-mono font-medium">v{v.version}</span>
                <p className="text-xs text-slate-500">{v.changeLog}</p>
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant="danger" onClick={handleRollback} disabled={!selectedVersion}>
            {t("rollback")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
