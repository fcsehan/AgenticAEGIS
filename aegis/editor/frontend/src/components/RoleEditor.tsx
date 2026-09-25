import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal, Button, Input } from "@/components/ui";
import { useDomainStore } from "@/store/domainStore";
import type { Role } from "@/types/domain";

interface RoleEditorProps {
  domainId: string;
  role?: Role;
  open: boolean;
  onClose: () => void;
}

export function RoleEditor({ domainId, role, open, onClose }: RoleEditorProps) {
  const { t } = useTranslation("common");
  const addRole = useDomainStore((s) => s.addRole);
  const updateRole = useDomainStore((s) => s.updateRole);
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");

  const handleSave = () => {
    if (!name.trim()) return;
    if (role) {
      updateRole(domainId, role.id, { name: name.trim(), description: description.trim() });
    } else {
      addRole(domainId, {
        id: crypto.randomUUID(),
        name: name.trim(),
        description: description.trim(),
        ruleCount: 0,
      });
    }
    onClose();
  };

  return (
    <Modal open={open} onClose={onClose} title={role ? t("edit") : t("create")}>
      <div className="flex flex-col gap-4">
        <Input
          id="role-name"
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
        />
        <Input
          id="role-desc"
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
