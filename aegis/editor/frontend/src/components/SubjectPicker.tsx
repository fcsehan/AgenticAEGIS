import { useTranslation } from "react-i18next";
import type { Domain } from "@/types/domain";
import { Select } from "@/components/ui";

interface SubjectPickerProps {
  domain: Domain;
  agentRole: string;
  code: string;
  onChangeRole: (role: string) => void;
  onChangeCode: (code: string) => void;
}

export function SubjectPicker({
  domain,
  agentRole,
  code,
  onChangeRole,
  onChangeCode,
}: SubjectPickerProps) {
  const { t } = useTranslation("rules");

  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">{t("selectSubject")}</p>
      <div className="flex flex-col gap-4">
        <Select
          id="agent-role"
          label={t("subject")}
          value={agentRole}
          onChange={(e) => onChangeRole(e.target.value)}
          options={[
            { value: "", label: "Select a role…" },
            ...domain.roles.map((r) => ({ value: r.name, label: r.name })),
          ]}
        />
        <Select
          id="code"
          label="Code of Conduct"
          value={code}
          onChange={(e) => onChangeCode(e.target.value)}
          options={[
            { value: "", label: "Select a code…" },
            ...domain.codes.map((c) => ({ value: c.id, label: c.name })),
          ]}
        />
      </div>
    </div>
  );
}
