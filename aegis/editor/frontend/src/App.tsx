import { useEditorText } from "@/hooks/useEditorText";
import { parseProject } from "@/api/contracts";
import { DocumentImport } from "@/pages/DocumentImport";
import { useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import { useDomainStore } from "@/store/domainStore";
import { useProjectStore } from "@/store/projectStore";
import type { Project } from "@/types/domain";
import { ProviderSettings } from "@/pages/ProviderSettings";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Dashboard } from "@/pages/Dashboard";
import { DomainWorkspace } from "@/pages/DomainWorkspace";
import { AuthoringWizard } from "@/pages/AuthoringWizard";

const router = createBrowserRouter([
  { path: "/documents/import", element: <DocumentImport /> },
  { path: "/settings/providers", element: <ProviderSettings /> },
  { path: "/", element: <Dashboard /> },
  { path: "/domain/:id", element: <DomainWorkspace /> },
  { path: "/domain/:id/authoring", element: <AuthoringWizard /> },
]);

export function App() {
  const tx = useEditorText();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    requestJson<Project | null>("/api/project")
      .then((project) => {
        if (project) {
          parseProject(project);
          useProjectStore.getState().setProject(project);
          useDomainStore.getState().setDomains(project.domains);
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setReady(true));
  }, []);
  if (!ready) return <p className="p-8"> {tx("Loading editor…")} </p>;
  if (error)
    return (
      <p role="alert" className="p-8">
        {" "}
        {tx("Backend unavailable:")} {error}{" "}
        {tx(". Please reload the page.")}{" "}
      </p>
    );
  return <RouterProvider router={router} />;
}
