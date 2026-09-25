import type { DomainStatus } from "@/types/domain";
import { cn } from "@/lib/utils";

const statusStyles: Record<DomainStatus, string> = {
  Draft: "bg-slate-100 text-slate-700",
  Review: "bg-amber-100 text-amber-800",
  Published: "bg-emerald-100 text-emerald-800",
  Archived: "bg-slate-200 text-slate-500",
};

interface BadgeProps {
  status: DomainStatus;
  className?: string;
}

export function Badge({ status, className }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        statusStyles[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
