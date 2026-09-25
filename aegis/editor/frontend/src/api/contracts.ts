import type { Domain, Project } from "@/types/domain";
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Invalid backend response: expected an object");
  return value as Record<string, unknown>;
}
export function parseDomain(value: unknown): Domain {
  const data = object(value);
  for (const key of ["id", "name", "status", "description", "lastModified"]) {
    if (typeof data[key] !== "string")
      throw new Error(`Invalid domain response: ${key}`);
  }
  for (const key of ["roles", "obligationTypes", "codes", "rules"]) {
    if (!Array.isArray(data[key]))
      throw new Error(`Invalid domain response: ${key}`);
  }
  if (
    !["Draft", "Review", "Published", "Archived"].includes(String(data.status))
  )
    throw new Error("Unbekannter Domainstatus");
  return data as unknown as Domain;
}
export function parseProject(value: unknown): Project {
  const data = object(value);
  for (const key of ["path", "name", "loadedAt"]) {
    if (typeof data[key] !== "string")
      throw new Error(`Invalid project response: ${key}`);
  }
  if (!Array.isArray(data.domains) || !Array.isArray(data.meldFiles))
    throw new Error("Invalid project lists");
  data.domains.forEach(parseDomain);
  for (const file of data.meldFiles) {
    const item = object(file);
    if (
      typeof item.path !== "string" ||
      typeof item.name !== "string" ||
      typeof item.sizeBytes !== "number"
    )
      throw new Error("Invalid MELD file metadata");
  }
  return data as unknown as Project;
}
export function parseVerdict(value: unknown): Record<string, unknown> & {
  decision: "PERMITTED" | "FORBIDDEN" | "UNDECIDABLE";
  reasonType: string;
  revision: string;
  justificationChain: string[];
} {
  const data = object(value);
  if (
    !["PERMITTED", "FORBIDDEN", "UNDECIDABLE"].includes(
      String(data.decision),
    ) ||
    typeof data.reasonType !== "string" ||
    typeof data.revision !== "string" ||
    !Array.isArray(data.justificationChain) ||
    !data.justificationChain.every((v) => typeof v === "string")
  )
    throw new Error("Invalid Guard verdict from backend");
  return data as ReturnType<typeof parseVerdict>;
}
