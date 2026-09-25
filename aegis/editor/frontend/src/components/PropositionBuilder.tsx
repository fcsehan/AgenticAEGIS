import { useEditorText } from "@/hooks/useEditorText";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui";
import type { Domain } from "@/types/domain";

interface PropositionBuilderProps {
  value: string;
  onChange: (value: string) => void;
  domain?: Domain;
}
export function PropositionBuilder({
  value,
  onChange,
  domain,
}: PropositionBuilderProps) {
  const tx = useEditorText();
  const { t } = useTranslation("rules");
  const [action, ...values] = value.trim().split(/\s+/);
  const parameters = domain?.actionSchemas?.[action ?? ""] ?? [];
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">{t("defineProposition")}</p>
      {domain?.revision && (
        <>
          <label className="block">
            {" "}
            {tx("Action")}{" "}
            <select
              className="block w-full rounded border p-2"
              value={action}
              onChange={(e) => onChange(e.target.value)}
            >
              <option value=""> {tx("Select…")} </option>
              {domain.actionTypes?.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </select>
          </label>
          {parameters.map((parameter, index) => (
            <label key={parameter.name} className="block">
              {parameter.name} ({parameter.type})
              <input
                className="block w-full rounded border p-2"
                value={values[index] ?? ""}
                onChange={(e) => {
                  const next = parameters.map((_, i) =>
                    i === index ? e.target.value : (values[i] ?? "?"),
                  );
                  onChange([action, ...next].join(" "));
                }}
              />
            </label>
          ))}
        </>
      )}
      <Input
        id="proposition"
        label={tx("MELD action with parameters in declared order")}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="font-mono"
      />
      <p className="text-xs text-slate-500">
        {tx(
          "Types and references are checked by the server on save. Edit complex terms in the MELD field.",
        )}
      </p>
    </div>
  );
}
