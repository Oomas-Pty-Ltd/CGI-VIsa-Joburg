import React from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * AdminShell — shared layout for SuperAdminDashboard + LocalAdminDashboard.
 *
 * Modern-SaaS layout: fixed left sidebar with grouped navigation, a slim
 * top header for tenant context + user actions, and a constrained-width
 * content area. Every colour/spacing token comes from `index.css`; nothing
 * is hardcoded here so the per-tenant theme override picks up cleanly.
 *
 * Props:
 *   tabs              — [{key, label, icon, group?}, …]
 *   activeTab         — string  (currently-selected key)
 *   onTabChange       — (key) => void
 *   user              — { email, type, company?, company_name? }
 *   onLogout          — () => void
 *   title             — string shown in the header (e.g. "Super Admin")
 *   pageTitle         — string shown at the top of the content area
 *   pageDescription?  — string shown beneath pageTitle
 *   pageActions?      — React node (buttons aligned to the right)
 *   children          — the active tab's content
 */
export default function AdminShell({
  tabs = [],
  activeTab,
  onTabChange,
  user,
  onLogout,
  title = "Admin",
  pageTitle,
  pageDescription,
  pageActions,
  topBarSlot,
  children,
}) {
  const navigate = useNavigate();

  const handleLogout = () => {
    if (onLogout) return onLogout();
    sessionStorage.clear();
    localStorage.removeItem("token");
    navigate("/login");
  };

  // Group tabs by their optional `group` field. Tabs without a group land
  // under a single un-labelled bucket rendered first.
  const grouped = React.useMemo(() => {
    const out = new Map();
    for (const t of tabs) {
      const key = t.group || "";
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(t);
    }
    return Array.from(out.entries());
  }, [tabs]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ── Sidebar ────────────────────────────────────────────── */}
      <aside
        className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col border-r border-border bg-card"
        aria-label="Primary navigation"
      >
        {/* Brand row */}
        <div className="flex h-14 items-center gap-2 px-5 border-b border-border">
          <div className="h-6 w-6 rounded-md bg-primary flex items-center justify-center text-primary-foreground text-xs font-semibold">
            {title.slice(0, 1)}
          </div>
          <span className="text-sm font-semibold tracking-tight">{title}</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-4 space-y-6">
          {grouped.map(([groupName, items], gi) => (
            <div key={gi}>
              {groupName && (
                <div className="px-3 mb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {groupName}
                </div>
              )}
              <ul className="space-y-0.5">
                {items.map(({ key, label, icon: Icon }) => {
                  const active = activeTab === key;
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        onClick={() => onTabChange?.(key)}
                        className={cn(
                          "w-full group flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                          active
                            ? "bg-secondary text-foreground font-medium"
                            : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                        )}
                        aria-current={active ? "page" : undefined}
                      >
                        {Icon && (
                          <Icon
                            className={cn(
                              "h-4 w-4 shrink-0",
                              active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"
                            )}
                          />
                        )}
                        <span className="truncate">{label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* User row. We always render this so the sidebar has a stable
            footer; an unknown user shows up as "Signed in" + a logout
            icon, but never as the broken "?" + "—" + "→" placeholder
            row from before. */}
        <div className="border-t border-border px-3 py-3">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-secondary flex items-center justify-center text-xs font-medium text-foreground shrink-0">
              {(user?.email || user?.type || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-foreground truncate">
                {user?.email || (user?.type === "super_admin" ? "Super admin" : "Signed in")}
              </div>
              {user?.company_name && (
                <div className="text-[11px] text-muted-foreground truncate">{user.company_name}</div>
              )}
              {!user?.company_name && user?.type && (
                <div className="text-[11px] text-muted-foreground truncate capitalize">
                  {user.type.replace(/_/g, " ")}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="text-muted-foreground hover:text-foreground hover:bg-secondary p-1.5 rounded transition-colors"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main column ───────────────────────────────────────── */}
      <div className="pl-60">
        {/* Top header — kept slim. Shows breadcrumb-style context (app
            title › active tab) on the left so operators always know
            where they are without reading the page heading; the right
            slot is reserved for global actions and accepts a custom
            ``topBarSlot`` node. The page heading itself sits in the
            scrolling body. */}
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/80 backdrop-blur px-8">
          <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground">
            <span>{title}</span>
            {pageTitle && (
              <>
                <span className="mx-2 text-border" aria-hidden="true">/</span>
                <span className="text-foreground font-medium">{pageTitle}</span>
              </>
            )}
          </nav>
          <div className="flex items-center gap-2">
            {topBarSlot}
          </div>
        </header>

        <main className="px-8 py-8 max-w-7xl mx-auto">
          {(pageTitle || pageDescription || pageActions) && (
            <div className="mb-6 flex items-start justify-between gap-4">
              <div className="min-w-0">
                {pageTitle && (
                  <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                    {pageTitle}
                  </h1>
                )}
                {pageDescription && (
                  <p className="mt-1 text-sm text-muted-foreground">{pageDescription}</p>
                )}
              </div>
              {pageActions && <div className="shrink-0">{pageActions}</div>}
            </div>
          )}

          {children}
        </main>
      </div>
    </div>
  );
}
