import { useTranslation } from "react-i18next";
import { ClockCounterClockwise } from "@phosphor-icons/react";
import type { DomainVersion } from "@/types/domain";
import { Badge } from "@/components/ui";

interface VersionHistoryProps {
  versions: DomainVersion[];
}

export function VersionHistory({ versions }: VersionHistoryProps) {
  const { t } = useTranslation("governance");

  if (versions.length === 0) {
    return <p className="text-center text-sm text-slate-400">{t("noVersions")}</p>;
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <ClockCounterClockwise size={14} className="text-slate-400" />
        <h4 className="text-xs font-medium uppercase tracking-wider text-slate-400">
          {t("versionHistory")}
        </h4>
      </div>
      <div className="flex flex-col gap-2">
        {versions.map((v) => (
          <div
            key={v.id}
            className="rounded-md border border-border bg-white p-3 text-sm"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-medium text-slate-800">v{v.version}</span>
              <Badge status={v.status} />
            </div>
            <p className="mt-1 text-xs text-slate-500">{v.changeLog}</p>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-400">
              <span>{v.author}</span>
              <span>&middot;</span>
              <span>{new Date(v.timestamp).toLocaleDateString()}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
