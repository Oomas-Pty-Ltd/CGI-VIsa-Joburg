import React from "react";
import { cn } from "@/lib/utils";

/**
 * EmptyState — uniform "no rows yet" placeholder for tables, lists,
 * dialogs, and tabs. Use instead of `<div>No records found</div>` so
 * every empty state in the admin surface gets the same visual weight
 * and gentle suggestion.
 *
 * Props:
 *   icon?       — lucide icon component
 *   title       — string
 *   description?— string
 *   action?     — React node (typically a Button)
 *   className?  — extra classes
 */
export function EmptyState({ icon: Icon, title, description, action, className }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center py-12 px-6",
        className,
      )}
    >
      {Icon && (
        <div className="h-10 w-10 rounded-full bg-secondary flex items-center justify-center mb-4">
          <Icon className="h-5 w-5 text-muted-foreground" aria-hidden />
        </div>
      )}
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      {description && (
        <p className="mt-1 text-xs text-muted-foreground max-w-sm">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
