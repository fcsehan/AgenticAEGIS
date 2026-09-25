import { useState } from "react";

interface ReasoningChainProps {
  chain: string[];
}

export function ReasoningChain({ chain }: ReasoningChainProps) {
  const [expanded, setExpanded] = useState(false);

  if (chain.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 transition-colors"
      >
        <span>Reasoning Chain ({chain.length} steps)</span>
        <span className="text-slate-400">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-3 space-y-1">
          {chain.map((step, i) => (
            <div key={i} className="flex gap-2 text-xs">
              <span className="text-slate-400 font-mono w-5 text-right flex-shrink-0">
                {i + 1}.
              </span>
              <span className="text-slate-700">{step}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
