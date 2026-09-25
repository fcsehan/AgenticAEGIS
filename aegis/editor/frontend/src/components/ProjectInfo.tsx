import { useTranslation } from "react-i18next";
import { File, FolderOpen, ArrowsClockwise } from "@phosphor-icons/react";
import type { Project } from "@/types/domain";
import { Card } from "@/components/ui";

interface ProjectInfoProps {
  project: Project;
}

const typeLabels: Record<string, string> = {
  vocabulary: "Vocabulary Mt",
  deontic: "Deontic Rules Mt",
  inference: "Inference Mt",
  ontology: "Ontology Mt",
};

const typeColors: Record<string, string> = {
  vocabulary: "bg-indigo-100 text-indigo-700",
  deontic: "bg-blue-100 text-blue-700",
  inference: "bg-amber-100 text-amber-700",
  ontology: "bg-slate-100 text-slate-600",
};

export function ProjectInfo({ project }: ProjectInfoProps) {
  const { t } = useTranslation("domains");

  return (
    <Card className="mb-6">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent-subtle">
          <FolderOpen size={18} className="text-accent" />
        </div>
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-slate-800">{project.name}</h2>
          <p className="font-mono text-[11px] text-slate-400">{project.path}</p>
        </div>
        <div className="text-right text-[11px] text-slate-400">
          <div className="flex items-center gap-1">
            <ArrowsClockwise size={10} />
            {new Date(project.loadedAt).toLocaleTimeString()}
          </div>
        </div>
      </div>

      <div className="mt-3 border-t border-border pt-3">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-slate-400">
          {t("meldFiles")} ({project.meldFiles.length})
        </p>
        <div className="flex flex-col gap-1">
          {project.meldFiles.map((mf) => (
            <div
              key={mf.path}
              className="flex items-center gap-2 rounded-sm px-2 py-1 text-xs hover:bg-surface-tertiary"
            >
              <File size={12} className="shrink-0 text-slate-400" />
              <span className="flex-1 font-mono text-slate-600">{mf.name}</span>
              <span
                className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${typeColors[mf.type] ?? "bg-slate-100 text-slate-500"}`}
              >
                {typeLabels[mf.type] ?? mf.type}
              </span>
              <span className="text-[10px] text-slate-400">
                {(mf.sizeBytes / 1024).toFixed(1)}KB
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
