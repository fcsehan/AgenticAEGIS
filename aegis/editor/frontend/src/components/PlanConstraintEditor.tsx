import { useEditorText } from "@/hooks/useEditorText";
import { useEffect, useState } from "react";
import { requestJson } from "@/api/client";
import type { Domain } from "@/types/domain";
import { useDomainStore } from "@/store/domainStore";
interface Constraint {
  id?: string;
  kind: string;
  action: string;
  argument: string;
}
const kinds = [
  "obligateSequence",
  "forbidAggregate",
  "obligateWithin",
  "requirePrecondition",
];
export function PlanConstraintEditor({ domain }: { domain: Domain }) {
  const tx = useEditorText();
  const [items, setItems] = useState<Constraint[]>([]);
  const [edit, setEdit] = useState<Constraint>({
    kind: "obligateSequence",
    action: "",
    argument: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const endpoint = `/api/domains/${domain.id}/plan-constraints`;
  useEffect(() => {
    requestJson<{ constraints: Constraint[] }>(endpoint)
      .then((r) => setItems(r.constraints))
      .catch((e: Error) => setError(e.message));
  }, [endpoint, domain.revision]);
  async function save(operation = "save") {
    setBusy(true);
    setError("");
    try {
      const result = await requestJson<Domain>(endpoint, {
        method: "POST",
        body: JSON.stringify({ ...edit, operation, revision: domain.revision }),
      });
      useDomainStore.getState().updateDomain(domain.id, result);
      setEdit({ kind: "obligateSequence", action: "", argument: "" });
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Save failed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="space-y-3 border-t p-4">
      <h2 className="font-semibold"> {tx("Plan constraints")} </h2>
      <p>
        {" "}
        {tx(
          "AEGIS evaluates supplied plans. Changes are saved as MELD and require new tests and review.",
        )}{" "}
      </p>
      {items.map((item) => (
        <button
          className="block rounded border p-2 font-mono text-xs"
          key={item.id}
          onClick={() => setEdit(item)}
        >
          {item.kind} · {item.action} · {item.argument}
        </button>
      ))}
      <label className="block">
        {" "}
        {tx("Predicate")}{" "}
        <select
          className="block rounded border p-2"
          value={edit.kind}
          onChange={(e) =>
            setEdit({ ...edit, kind: e.target.value, argument: "" })
          }
        >
          {kinds.map((kind) => (
            <option key={kind}>{kind}</option>
          ))}
        </select>
      </label>
      <label className="block">
        {" "}
        {tx("Action")}{" "}
        <select
          className="block rounded border p-2"
          value={edit.action}
          onChange={(e) => setEdit({ ...edit, action: e.target.value })}
        >
          <option value=""> {tx("Select…")} </option>
          {domain.actionTypes?.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </label>
      <label className="block">
        {edit.kind === "obligateSequence"
          ? tx("Required successor action")
          : edit.kind === "forbidAggregate"
            ? tx("Maximum count")
            : edit.kind === "obligateWithin"
              ? tx("Deadline: seconds / immediate / same-session / end-of-plan")
              : tx("Precondition, e.g. (testStatus passed)")}
        <input
          className="block w-full rounded border p-2"
          value={edit.argument}
          onChange={(e) => setEdit({ ...edit, argument: e.target.value })}
        />
      </label>
      <pre className="overflow-auto text-xs">
        ({edit.kind} {edit.action} {edit.argument})
      </pre>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      <div className="flex gap-4">
        <button
          disabled={busy || !edit.action || !edit.argument}
          onClick={() => save()}
        >
          {" "}
          {tx("Save plan constraint")}{" "}
        </button>
        {edit.id && (
          <>
            <button
              disabled={busy}
              onClick={() => setEdit({ ...edit, id: undefined })}
            >
              {" "}
              {tx("As a new constraint")}{" "}
            </button>
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm(tx("Delete plan constraint?")))
                  save("delete");
              }}
            >
              {" "}
              {tx("Delete")}{" "}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
