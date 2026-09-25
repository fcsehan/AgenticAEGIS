import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SidebarProps {
  children: ReactNode;
  className?: string;
  open?: boolean;
}

export function Sidebar({ children, className, open = true }: SidebarProps) {
  return (
    <aside
      className={cn(
        "flex h-full w-sidebar flex-col border-r border-border bg-surface-secondary",
        "transition-[width,opacity] duration-200",
        !open && "w-0 overflow-hidden opacity-0",
        className,
      )}
    >
      {children}
    </aside>
  );
}
