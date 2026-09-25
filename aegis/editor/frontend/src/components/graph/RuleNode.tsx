import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { DeonticModality } from "@/types/domain";

interface RuleNodeData {
  label: string;
  modality: DeonticModality;
  proposition: string;
  [key: string]: unknown;
}

const modalityColors: Record<DeonticModality, { bg: string; border: string; text: string }> = {
  OBLIGATORY: { bg: "bg-blue-50", border: "border-blue-300", text: "text-blue-700" },
  FORBIDDEN: { bg: "bg-red-50", border: "border-red-300", text: "text-red-700" },
  PERMITTED: { bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-700" },
};

export function RuleNode({ data }: NodeProps) {
  const d = data as RuleNodeData;
  const colors = modalityColors[d.modality];

  return (
    <div className={`rounded-md border px-3 py-2 shadow-sm ${colors.bg} ${colors.border}`}>
      <Handle type="target" position={Position.Top} className="!bg-slate-300" />
      <div className="flex items-center gap-2">
        <span className={`text-[10px] font-bold uppercase ${colors.text}`}>{d.modality}</span>
      </div>
      <p className="mt-0.5 font-mono text-[11px] text-slate-700">{d.proposition}</p>
      <p className="mt-0.5 text-[10px] text-slate-400">{d.label}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-300" />
    </div>
  );
}
