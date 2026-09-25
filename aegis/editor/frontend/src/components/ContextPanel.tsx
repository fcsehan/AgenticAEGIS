import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui";

interface ContextPanelProps {
  specificity: number;
  defeasible: boolean;
  onChangeSpecificity: (val: number) => void;
  onChangeDefeasible: (val: boolean) => void;
}

export function ContextPanel({
  specificity,
  defeasible,
  onChangeSpecificity,
  onChangeDefeasible,
}: ContextPanelProps) {
  const { t } = useTranslation("rules");

  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">{t("setContext")}</p>
      <div className="flex flex-col gap-4">
        <Input
          id="specificity"
          label={t("specificity")}
          type="number"
          min={1}
          max={10}
          value={specificity}
          onChange={(e) => onChangeSpecificity(Number(e.target.value))}
        />
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={defeasible}
            onChange={(e) => onChangeDefeasible(e.target.checked)}
            className="h-4 w-4 rounded border-border accent-accent"
          />
          <div>
            <span className="text-sm font-medium text-slate-700">{t("defeasible")}</span>
            <p className="text-[11px] text-slate-400">
              Defeasible rules can be overridden by more specific rules.
            </p>
          </div>
        </label>
      </div>
    </div>
  );
}
