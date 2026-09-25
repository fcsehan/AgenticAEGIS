import type { Verdict } from "@/types/domain";

interface VerdictDisplayProps {
  verdict: Verdict;
}

const decisionStyles = {
  PERMITTED: {
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    text: "text-emerald-800",
    icon: "✓",
    label: "PERMITTED",
  },
  FORBIDDEN: {
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-800",
    icon: "✕",
    label: "FORBIDDEN",
  },
  UNDECIDABLE: {
    bg: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-800",
    icon: "?",
    label: "UNDECIDABLE",
  },
} as const;

export function VerdictDisplay({ verdict }: VerdictDisplayProps) {
  const style = decisionStyles[verdict.decision] ?? decisionStyles.UNDECIDABLE;

  return (
    <div className={`rounded-lg border ${style.border} ${style.bg} p-4`}>
      <div className={`flex items-center gap-2 ${style.text}`}>
        <span className="text-2xl font-bold">{style.icon}</span>
        <span className="text-lg font-semibold">{style.label}</span>
      </div>

      {verdict.explanation && (
        <p className="mt-2 text-sm text-slate-700">{verdict.explanation}</p>
      )}

      {verdict.appliedRules.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-slate-500 mb-1">Applied rules:</p>
          {verdict.appliedRules.map((rule, i) => (
            <span
              key={i}
              className="inline-block text-xs bg-white/60 rounded px-2 py-0.5 mr-1 mb-1 font-mono"
            >
              {rule}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
