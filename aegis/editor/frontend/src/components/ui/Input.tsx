import { type InputHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id: providedId, ...props }, ref) => {
    const generatedId = useId();
    const id = providedId ?? generatedId;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={id} className="text-xs font-medium text-slate-600">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={id}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : undefined}
          className={cn(
            "h-9 rounded-md border bg-white px-3 text-sm transition-colors",
            "placeholder:text-slate-400",
            "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20",
            "disabled:cursor-not-allowed disabled:opacity-50",
            error ? "border-status-error" : "border-border",
            className,
          )}
          {...props}
        />
        {error && (
          <p
            id={`${id}-error`}
            role="alert"
            className="text-xs text-status-error"
          >
            {error}
          </p>
        )}
      </div>
    );
  },
);
Input.displayName = "Input";
