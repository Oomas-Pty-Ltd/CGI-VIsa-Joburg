import React from "react";
import { cn } from "@/lib/utils";

/**
 * Section — titled content block used across all admin tabs.
 *
 * Replaces the ad-hoc `<div className="rounded-lg border bg-white p-4">`
 * variants that drift between tabs. Use this any time you have a titled
 * group of fields, a table, or a sub-panel inside a tab.
 *
 * Props:
 *   title         — string  (required)
 *   description?  — string shown below the title
 *   actions?      — React node on the right side of the header
 *   children      — section body
 *   className?    — extra classes on the outer container
 *   bodyClassName?— extra classes on the body wrapper (e.g. padding tweaks)
 */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-border bg-card shadow-sm",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-4 px-5 py-4 border-b border-border">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight text-foreground">
            {title}
          </h3>
          {description && (
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
              {description}
            </p>
          )}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </header>
      <div className={cn("px-5 py-4", bodyClassName)}>{children}</div>
    </section>
  );
}
