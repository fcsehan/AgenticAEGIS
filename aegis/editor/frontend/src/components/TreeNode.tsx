import { useState, type ReactNode } from "react";
import { CaretRight, CaretDown } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

interface TreeNodeProps {
  label: string;
  count?: number;
  children?: ReactNode;
  icon?: ReactNode;
  selected?: boolean;
  onSelect?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}

export function TreeNode({
  label,
  count,
  children,
  icon,
  selected,
  onSelect,
  onEdit,
  onDelete,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = !!children;

  return (
    <div>
      <div
        className={cn(
          "group flex cursor-pointer items-center gap-1.5 rounded-sm px-2 py-1 text-sm",
          "hover:bg-surface-hover",
          selected && "bg-accent-subtle text-accent",
        )}
        onClick={onSelect}
      >
        {hasChildren ? (
          <button
            className="shrink-0 text-slate-400"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
          >
            {expanded ? <CaretDown size={12} /> : <CaretRight size={12} />}
          </button>
        ) : (
          <span className="w-3" />
        )}
        {icon}
        <span className="flex-1 truncate">{label}</span>
        {count !== undefined && (
          <span className="text-[11px] text-slate-400">{count}</span>
        )}
        <span className="hidden items-center gap-0.5 group-hover:flex">
          {onEdit && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
              className="rounded p-0.5 text-slate-400 hover:text-slate-600"
              title="Edit"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path
                  d="M8.5 1.5l2 2-7 7H1.5v-2l7-7z"
                  stroke="currentColor"
                  strokeWidth="1"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="rounded p-0.5 text-slate-400 hover:text-status-error"
              title="Delete"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path
                  d="M9 3L3 9M3 3l6 6"
                  stroke="currentColor"
                  strokeWidth="1"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          )}
        </span>
      </div>
      {hasChildren && expanded && <div className="ml-3 border-l border-border pl-1">{children}</div>}
    </div>
  );
}
