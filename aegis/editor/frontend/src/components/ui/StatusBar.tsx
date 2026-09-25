import { cn } from "@/lib/utils";

interface StatusBarProps {
  errors: number;
  warnings: number;
  className?: string;
}

export function StatusBar({ errors, warnings, className }: StatusBarProps) {
  const isClean = errors === 0 && warnings === 0;

  return (
    <div
      className={cn(
        "flex h-7 items-center gap-4 border-t border-border px-4 text-xs",
        isClean ? "bg-surface-secondary text-slate-500" : "bg-status-error-light text-slate-700",
        className,
      )}
    >
      {isClean ? (
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-status-success" />
          Valid
        </span>
      ) : (
        <>
          {errors > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-status-error" />
              {errors} error{errors !== 1 ? "s" : ""}
            </span>
          )}
          {warnings > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-status-warning" />
              {warnings} warning{warnings !== 1 ? "s" : ""}
            </span>
          )}
        </>
      )}
    </div>
  );
}
