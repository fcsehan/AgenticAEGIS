import { useProjectStore } from "@/store/projectStore";
import { parseDomain, parseProject } from "./contracts";
import { QueryClient } from "@tanstack/react-query";
import type { Domain, Project } from "@/types/domain";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 0, retry: 1 } },
});

export async function editorFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("X-Aegis-Editor", "1");
  const project = useProjectStore.getState().project;
  if (project) headers.set("X-Aegis-Project", encodeURIComponent(project.path));
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail = Array.isArray(body?.detail)
      ? body.detail
          .map(
            (e: { loc?: string[]; msg?: string }) =>
              `${e.loc?.join(".")}: ${e.msg}`,
          )
          .join("; ")
      : body?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status})`,
    );
  }
  return response;
}

export async function requestJson<T>(
  url: string,
  init: RequestInit = {},
): Promise<T> {
  return (await editorFetch(url, init)).json() as Promise<T>;
}

export const api = {
  openProject: (path: string) =>
    requestJson<Project>("/api/project/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    }).then(parseProject),
  listDomains: () =>
    requestJson<Domain[]>("/api/domains").then((values) => {
      if (!Array.isArray(values)) throw new Error("Invalid domain list");
      return values.map(parseDomain);
    }),
  getDomain: (id: string) =>
    requestJson<Domain>(`/api/domains/${encodeURIComponent(id)}`).then(
      parseDomain,
    ),
};
