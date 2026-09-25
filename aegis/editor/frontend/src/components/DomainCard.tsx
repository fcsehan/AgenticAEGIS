import { useEditorText } from "@/hooks/useEditorText";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { BookOpen, Scales, Warning } from "@phosphor-icons/react";
import type { Domain } from "@/types/domain";
import { Card, Badge } from "@/components/ui";

interface DomainCardProps {
  domain: Domain;
}

export function DomainCard({ domain }: DomainCardProps) {
  const tx = useEditorText();
  const navigate = useNavigate();
  const { t } = useTranslation("domains");

  return (
    <Card
      interactive
      onClick={() => navigate(`/domain/${domain.id}`)}
      className="flex flex-col gap-3"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900">{domain.name}</h3>
          <p className="mt-1 line-clamp-2 text-xs text-slate-500">
            {domain.description}
          </p>
        </div>
        <Badge status={domain.status} />
      </div>

      {domain.loadError && (
        <p role="alert" className="text-red-700">
          {domain.loadError}{" "}
          {tx("— Correct the MELD files and reopen the project.")}{" "}
        </p>
      )}
      <div className="flex items-center gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <BookOpen size={14} />
          {domain.rules.length} {t("rules")}
        </span>
        <span className="flex items-center gap-1">
          <Scales size={14} />
          {domain.roles.length} {t("roles")}
        </span>
        {domain.conflictCount > 0 && (
          <span className="flex items-center gap-1 text-status-warning">
            <Warning size={14} />
            {domain.conflictCount} {t("conflicts")}
          </span>
        )}
      </div>

      <div className="text-[11px] text-slate-400">
        {t("lastModified")}:{" "}
        {new Date(domain.lastModified).toLocaleDateString()}
        {domain.version && <span className="ml-2">v{domain.version}</span>}
      </div>
    </Card>
  );
}
