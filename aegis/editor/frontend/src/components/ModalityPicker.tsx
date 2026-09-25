import { useTranslation } from "react-i18next";
import { ShieldCheck, Prohibit, CheckCircle } from "@phosphor-icons/react";
import type { DeonticModality } from "@/types/domain";
import { cn } from "@/lib/utils";

interface ModalityPickerProps {
  value: DeonticModality | null;
  onChange: (modality: DeonticModality) => void;
}

const modalities: { value: DeonticModality; icon: typeof ShieldCheck; color: string }[] = [
  { value: "OBLIGATORY", icon: ShieldCheck, color: "border-blue-300 bg-blue-50 text-blue-700" },
  { value: "FORBIDDEN", icon: Prohibit, color: "border-red-300 bg-red-50 text-red-700" },
  { value: "PERMITTED", icon: CheckCircle, color: "border-emerald-300 bg-emerald-50 text-emerald-700" },
];

export function ModalityPicker({ value, onChange }: ModalityPickerProps) {
  const { t } = useTranslation("rules");

  return (
    <div>
      <p className="mb-3 text-sm text-slate-600">{t("selectModality")}</p>
      <div className="grid grid-cols-3 gap-3">
        {modalities.map(({ value: m, icon: Icon, color }) => (
          <button
            key={m}
            onClick={() => onChange(m)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-lg border-2 p-4 transition-all",
              value === m ? color : "border-border bg-white text-slate-500 hover:border-slate-300",
            )}
          >
            <Icon size={24} weight={value === m ? "fill" : "regular"} />
            <span className="text-xs font-medium">{t(m.toLowerCase())}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
