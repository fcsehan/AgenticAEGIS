import { useEditorText } from "@/hooks/useEditorText";
import { requestJson } from "@/api/client";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Button, Input } from "@/components/ui";
import { useDomainStore } from "@/store/domainStore";
import type { Domain } from "@/types/domain";

interface CreateDomainDialogProps {
  open: boolean;
  onClose: () => void;
}

export function CreateDomainDialog({ open, onClose }: CreateDomainDialogProps) {
  const tx = useEditorText();
  const { t } = useTranslation("domains");
  const { t: tc } = useTranslation("common");
  const addDomain = useDomainStore((s) => s.addDomain);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const handleCreate = async () => {
    if (!name.trim()) return;

    setBusy(true);
    setError("");
    try {
      const domain = await requestJson<Domain>("/api/domains", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim(),
        }),
      });
      addDomain(domain);
      setName("");
      setDescription("");
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Creation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={t("createDomain")}>
      <div className="flex flex-col gap-4">
        {error && <p role="alert">{error}</p>}
        <Input
          id="domain-name"
          label={t("domainName")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={tx("e.g. Medical Ethics")}
          autoFocus
        />
        <Input
          id="domain-description"
          label={t("domainDescription")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={tx("Brief description of the domain")}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button onClick={handleCreate} disabled={!name.trim() || busy}>
            {tc("create")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
