import React from "react";
import { cn } from "@/lib/utils";

/**
 * StatCard — small headline metric used on dashboard overviews.
 *
 * Three-card row at the top of SuperAdminDashboard and LocalAdminDashboard.
 * Keeps the icon, label, and value aligned the same way everywhere so a
 * tenant operator can scan the row without re-orienting.
 *
 * Props:
 *   icon       — lucide icon component
 *   label      — uppercase eyebrow text
 *   value      — main number / string
 *   valueClass?— extra classes on the value (e.g. "capitalize")
 */
export function StatCard({ icon: Icon, label, value, valueClass }) {
  return (
    <div className="rounded-lg border border-border bg-card px-5 py-4 shadow-sm flex items-center gap-4">
      {Icon && (
        <div className="h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center shrink-0">
          <Icon className="h-5 w-5 text-primary" aria-hidden />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
          {label}
        </p>
        <p className={cn("text-2xl font-semibold tracking-tight text-foreground mt-0.5", valueClass)}>
          {value}
        </p>
      </div>
    </div>
  );
}
