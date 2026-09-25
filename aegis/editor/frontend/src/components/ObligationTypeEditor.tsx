import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Button, Input } from "@/components/ui";
import { useDomainStore } from "@/store/domainStore";
import type { ObligationType } from "@/types/domain";

interface ObligationTypeEditorProps {
  domainId: string;
  obligationType?: ObligationType;
  open: boolean;
  onClose: () => void;
}

export function ObligationTypeEditor({
  domainId,
  obligationType,
  open,
  onClose,
}: ObligationTypeEditorProps) {
  const { t } = useTranslation("common");
  const addOt = useDomainStore((s) => s.addObligationType);
  const updateOt = useDomainStore((s) => s.updateObligationType);
  const [name, setName] = useState(obligationType?.name ?? "");
  const [description, setDescription] = useState(obligationType?.description ?? "");

  const handleSave = () => {
    if (!name.trim()) return;
    if (obligationType) {
      updateOt(domainId, obligationType.id, {
        name: name.trim(),
        description: description.trim(),
      });
    } else {
      addOt(domainId, {
        id: crypto.randomUUID(),
        name: name.trim(),
        description: description.trim(),
        children: [],
      });
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={obligationType ? t("edit") : t("create")}>
      <div className="flex flex-col gap-4">
        <Input
          id="ot-name"
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
        <Input
          id="ot-desc"
          label="Description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button onClick={handleSave} disabled={!name.trim()}>
            {t("save")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
