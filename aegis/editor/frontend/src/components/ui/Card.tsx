import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

export function Card({
  className,
  interactive,
  children,
  ...props
}: CardProps) {
  return (
    <div
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={(event) => {
        if (interactive && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          event.currentTarget.click();
        }
      }}
      className={cn(
        "rounded-md border border-border bg-white p-4 shadow-sm",
        interactive &&
          "cursor-pointer transition-colors hover:bg-surface-secondary",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
