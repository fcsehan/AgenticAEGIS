import { useEditorText } from "@/hooks/useEditorText";
import { useEffect, useState } from "react";
import type { Domain } from "@/types/domain";
import { requestJson } from "@/api/client";
import { useDomainStore } from "@/store/domainStore";
import { Button, Input, Modal } from "@/components/ui";

type Kind = "role" | "obligation" | "code" | "action";
interface Edit {
  kind: Kind;
  name: string;
  previous?: string;
  description: string;
  parent: string;
  parameters: string;
}
const titles: Record<Kind, string> = {
  role: "Roles",
  obligation: "Obligation types",
  code: "Codes of Conduct",
  action: "Action types",
};
export function StructurePanel({ domain }: { domain: Domain }) {
  const tx = useEditorText();
  const [prevalence, setPrevalence] = useState(
    (domain.codePrevalence ?? []).join("\n"),
  );
  useEffect(() => {
    setPrevalence((domain.codePrevalence ?? []).join("\n"));
  }, [domain.revision, domain.codePrevalence]);
  const [edit, setEdit] = useState<Edit | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const groups: Record<
    Kind,
    { name: string; description: string; parent?: string }[]
  > = {
    role: domain.roles.map((r) => ({ ...r, parent: r.obligationType })),
    obligation: domain.obligationTypes.map((o) => ({
      ...o,
      parent: o.parentId,
    })),
    code: domain.codes,
    action: (domain.actionTypes ?? []).map((name) => ({
      name,
      description: "",
    })),
  };
  function open(
    kind: Kind,
    value?: { name: string; description: string; parent?: string },
  ) {
    setError("");
    setEdit({
      kind,
      name: value?.name ?? "",
      previous: value?.name,
      description: value?.description ?? "",
      parent: value?.parent ?? "",
      parameters: value
        ? JSON.stringify(domain.actionSchemas?.[value.name] ?? [], null, 2)
        : "[]",
    });
  }
  async function save(operation: "create" | "update" | "delete") {
    if (!edit) return;
    setBusy(true);
    setError("");
    try {
      const result = await requestJson<Domain>(
        `/api/domains/${domain.id}/structure`,
        {
          method: "POST",
          body: JSON.stringify({
            ...edit,
            operation,
            revision: domain.revision,
            parent: edit.parent || null,
            parameters:
              edit.kind === "action" ? JSON.parse(edit.parameters) : [],
          }),
        },
      );
      useDomainStore.getState().updateDomain(domain.id, result);
      setEdit(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Save failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="w-full max-w-xl space-y-4 overflow-auto border-r p-4">
      <h2 className="font-semibold"> {tx("Domain structure")} </h2>
      <Input
        label={tx("Search")}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {(Object.keys(groups) as Kind[]).map((kind) => (
        <section key={kind} className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">{tx(titles[kind])}</h3>
            <Button size="sm" onClick={() => open(kind)}>
              {" "}
              {tx("Add")}{" "}
            </Button>
          </div>
          {groups[kind]
            .filter((v) => v.name.toLowerCase().includes(search.toLowerCase()))
            .map((value) => (
              <button
                key={value.name}
                className="block w-full rounded border p-2 text-left text-sm"
                onClick={() => open(kind, value)}
              >
                {value.name}
                {value.parent && (
                  <span className="text-slate-500"> → {value.parent}</span>
                )}
                <p className="text-xs text-slate-500">{value.description}</p>
              </button>
            ))}
        </section>
      ))}
      <details>
        <summary> {tx("Code precedence (schema 1)")} </summary>
        <label>
          {" "}
          {tx("Highest-priority code first, one name per line")}{" "}
          <textarea
            className="block w-full rounded border p-2"
            value={prevalence}
            onChange={(e) => setPrevalence(e.target.value)}
          />
        </label>
        <p className="text-xs">
          {" "}
          {tx(
            "Unlisted codes remain tied below listed codes. Schema 2 uses MELD formula priorities instead.",
          )}{" "}
        </p>
        <button
          onClick={async () => {
            setError("");
            try {
              const saved = await requestJson<Domain>(
                `/api/domains/${domain.id}/code-prevalence`,
                {
                  method: "POST",
                  body: JSON.stringify({
                    revision: domain.revision,
                    codes: prevalence.split(/\s+/).filter(Boolean),
                  }),
                },
              );
              useDomainStore.getState().updateDomain(domain.id, saved);
            } catch (e) {
              setError(
                e instanceof Error ? e.message : tx("Save failed"),
              );
            }
          }}
        >
          {" "}
          {tx("Save precedence in MELD")}{" "}
        </button>
      </details>
      {error && !edit && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      <Modal
        open={!!edit}
        onClose={() => setEdit(null)}
        title={edit ? tx(titles[edit.kind]) : tx("Structure")}
      >
        {edit && (
          <div className="space-y-3">
            <Input
              label={tx("MELD symbol")}
              value={edit.name}
              onChange={(e) => setEdit({ ...edit, name: e.target.value })}
            />
            <Input
              label={tx("Description")}
              value={edit.description}
              onChange={(e) =>
                setEdit({ ...edit, description: e.target.value })
              }
            />
            {(edit.kind === "role" || edit.kind === "obligation") && (
              <label className="block">
                {" "}
                {tx("Assigned / parent obligation type")}{" "}
                <select
                  className="block w-full rounded border p-2"
                  value={edit.parent}
                  onChange={(e) => setEdit({ ...edit, parent: e.target.value })}
                >
                  <option value=""> {tx("No assignment")} </option>
                  {domain.obligationTypes
                    .filter((o) => o.name !== edit.name)
                    .map((o) => (
                      <option key={o.id} value={o.name}>
                        {o.name}
                      </option>
                    ))}
                </select>
              </label>
            )}
            {edit.kind === "action" && (
              <label className="block">
                {" "}
                {tx(
                  "Parameters in declared order (JSON: name, type)",
                )}{" "}
                <textarea
                  className="block min-h-40 w-full rounded border p-2 font-mono text-xs"
                  value={edit.parameters}
                  onChange={(e) =>
                    setEdit({ ...edit, parameters: e.target.value })
                  }
                />
              </label>
            )}
            {edit.kind === "code" && (
              <p>
                {" "}
                {tx(
                  "Edit precedence separately as a MELD declaration in Code precedence.",
                )}{" "}
              </p>
            )}
            {error && (
              <p role="alert" className="text-red-700">
                {error}
              </p>
            )}
            <div className="flex gap-3">
              <Button
                disabled={busy || !edit.name}
                onClick={() => save(edit.previous ? "update" : "create")}
              >
                {" "}
                {tx("Save in MELD")}{" "}
              </Button>
              {edit.previous && (
                <Button
                  variant="danger"
                  disabled={busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        tx(
                          "Delete declaration? Referenced symbols cannot be deleted.",
                        ),
                      )
                    )
                      save("delete");
                  }}
                >
                  {" "}
                  {tx("Delete")}{" "}
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}
