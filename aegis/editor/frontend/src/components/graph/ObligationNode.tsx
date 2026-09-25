import { Handle, Position, type NodeProps } from "@xyflow/react";
import { TreeStructure } from "@phosphor-icons/react";

interface ObligationNodeData {
  label: string;
  description: string;
  [key: string]: unknown;
}

export function ObligationNode({ data }: NodeProps) {
  const d = data as ObligationNodeData;
  return (
    <div className="rounded-md border border-border bg-white px-3 py-2 shadow-sm">
      <Handle type="target" position={Position.Top} className="!bg-slate-300" />
      <div className="flex items-center gap-2">
        <TreeStructure size={14} className="text-accent" />
        <span className="text-xs font-medium text-slate-800">{d.label}</span>
      </div>
      <p className="mt-0.5 text-[10px] text-slate-400">{d.description}</p>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-300" />
    </div>
  );
}
