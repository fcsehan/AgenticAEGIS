import { type SelectHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, label, options, id: providedId, ...props }, ref) => {
    const generatedId = useId();
    const id = providedId ?? generatedId;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-xs font-medium text-slate-600">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={id}
          className={cn(
            "h-9 rounded-md border border-border bg-white px-3 text-sm transition-colors",
            "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20",
            "disabled:cursor-not-allowed disabled:opacity-50",
            className,
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  },
);
Select.displayName = "Select";
