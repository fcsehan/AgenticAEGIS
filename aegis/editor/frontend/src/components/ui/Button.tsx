import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover shadow-sm",
  secondary:
    "bg-white text-slate-700 border border-border hover:bg-surface-tertiary shadow-sm",
  danger: "bg-status-error text-white hover:bg-red-600 shadow-sm",
  ghost: "text-slate-600 hover:bg-surface-tertiary hover:text-slate-900",
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs rounded-sm",
  md: "h-9 px-4 text-sm rounded-md",
  lg: "h-10 px-5 text-sm rounded-md",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", disabled, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2",
        "disabled:pointer-events-none disabled:opacity-50",
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
      disabled={disabled}
      {...props}
    />
  ),
);
Button.displayName = "Button";
