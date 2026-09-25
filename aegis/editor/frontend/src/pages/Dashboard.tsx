import { useEditorText } from "@/hooks/useEditorText";
import { PackageImport } from "@/components/PackageImport";
import { CreateDomainDialog } from "@/components/CreateDomainDialog";
import { requestJson } from "@/api/client";
import { Link } from "react-router-dom";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, X } from "@phosphor-icons/react";
import { useDomainStore } from "@/store/domainStore";
import { useProjectStore } from "@/store/projectStore";
import { Button } from "@/components/ui";
import { DomainCard } from "@/components/DomainCard";
import { OpenProjectDialog } from "@/components/OpenProjectDialog";
import { ProjectInfo } from "@/components/ProjectInfo";

export function Dashboard() {
  const tx = useEditorText();
  const { t } = useTranslation("domains");
  const { t: tc } = useTranslation("common");
  const { domains } = useDomainStore();
  const { project, closeProject } = useProjectStore();
  const { setDomains } = useDomainStore();
  const [createVisible, setCreateVisible] = useState(false);
  const [openDialogVisible, setOpenDialogVisible] = useState(false);


  const handleCloseProject = async () => {
    try {
      await requestJson("/api/project/close", { method: "POST" });
      closeProject();
      setDomains([]);
    } catch (e) {
      window.alert(e instanceof Error ? e.message : "Closing failed");
    }
  };

  return (
    <div className="mx-auto min-h-screen max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">{tc("appName")}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {project ? project.name : t("title")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {project && (
            <Link to="/documents/import" className="text-sm">
              {" "}
              {tx("Document import")}{" "}
            </Link>
          )}
          {project && (
            <Button onClick={() => setCreateVisible(true)}>
              {" "}
              {tx("New domain")}{" "}
            </Button>
          )}
          <Link to="/settings/providers" className="text-sm">
            {" "}
            {tx("Inference settings")}{" "}
          </Link>
          {project ? (
            <Button variant="secondary" size="sm" onClick={handleCloseProject}>
              <X size={14} />
              {t("closeProject")}
            </Button>
          ) : null}
          <Button onClick={() => setOpenDialogVisible(true)}>
            <FolderOpen size={16} weight="bold" />
            {t("openProject")}
          </Button>
        </div>
      </header>

      {!project ? (
        /* No project loaded — show welcome / open prompt */
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-subtle">
            <FolderOpen size={32} className="text-accent" />
          </div>
          <h2 className="text-lg font-semibold text-slate-700">
            {t("welcomeTitle")}
          </h2>
          <p className="mt-2 max-w-md text-sm text-slate-400">
            {t("welcomeDesc")}
          </p>
          <Button className="mt-6" onClick={() => setOpenDialogVisible(true)}>
            <FolderOpen size={16} weight="bold" />
            {t("openProject")}
          </Button>
        </div>
      ) : (
        /* Project loaded — show info + domain cards */
        <>
          <ProjectInfo project={project} />
          <PackageImport />

          {domains.length === 0 ? (
            <p className="py-12 text-center text-sm text-slate-400">
              {t("noDomainsInProject")}
            </p>
          ) : (
            <>
              <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-slate-400">
                {t("loadedDomains")} ({domains.length})
              </h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {domains.map((d) => (
                  <DomainCard key={d.id} domain={d} />
                ))}
              </div>
            </>
          )}
        </>
      )}

      <CreateDomainDialog
        open={createVisible}
        onClose={() => setCreateVisible(false)}
      />
      <OpenProjectDialog
        open={openDialogVisible}
        onClose={() => setOpenDialogVisible(false)}
      />
    </div>
  );
}
