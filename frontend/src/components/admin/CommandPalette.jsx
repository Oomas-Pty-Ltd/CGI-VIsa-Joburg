import React, { useEffect } from "react";
import { Building2, ChevronRight } from "lucide-react";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandShortcut,
} from "@/components/ui/command";

/**
 * CommandPalette — ⌘K / Ctrl+K launcher for the admin shells.
 *
 * Lists the current console's tabs (always) and the platform's tenants
 * (super-admin only). Choosing a tab switches to it. Choosing a tenant
 * jumps to the Bot config tab and asks the parent to pre-select that
 * tenant via `onTenantSelect` — that's the most common reason an
 * operator hops between tenants ("configure tenant X").
 *
 * The parent owns the `open` state so a header chip can also pop it.
 *
 * Props:
 *   open              — controlled boolean
 *   onOpenChange      — (boolean) => void
 *   tabs              — [{key, label, icon, group?}, …]
 *   onTabChange       — (key) => void
 *   companies?        — [{id, name}, …]    (super-admin only)
 *   onTenantSelect?   — (companyId) => void (super-admin only)
 */
export function CommandPalette({
  open,
  onOpenChange,
  tabs = [],
  onTabChange,
  companies = [],
  onTenantSelect,
}) {
  // Group tabs by their optional `group` field so the palette mirrors the
  // sidebar structure. Tabs without a group land under "Pages".
  const groupedTabs = React.useMemo(() => {
    const out = new Map();
    for (const t of tabs) {
      const key = t.group || "Pages";
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(t);
    }
    return Array.from(out.entries());
  }, [tabs]);

  const handleTab = (key) => {
    onOpenChange?.(false);
    onTabChange?.(key);
  };

  const handleTenant = (id) => {
    onOpenChange?.(false);
    onTenantSelect?.(id);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Type a page or tenant…" />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>

        {groupedTabs.map(([groupName, items]) => (
          <CommandGroup key={groupName} heading={groupName}>
            {items.map(({ key, label, icon: Icon }) => (
              <CommandItem
                key={key}
                value={`${groupName} ${label}`}
                onSelect={() => handleTab(key)}
              >
                {Icon && <Icon className="text-muted-foreground" />}
                <span>{label}</span>
                <CommandShortcut>↵</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}

        {companies.length > 0 && (
          <CommandGroup heading="Tenants">
            {companies.map((c) => (
              <CommandItem
                key={c.id}
                value={`tenant ${c.name} ${c.id}`}
                onSelect={() => handleTenant(c.id)}
              >
                <Building2 className="text-muted-foreground" />
                <span className="flex-1 truncate">{c.name}</span>
                <ChevronRight className="text-muted-foreground" />
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}

/**
 * Hook — registers the global ⌘K / Ctrl+K keyboard shortcut to toggle
 * the palette. Lives here so every shell gets the same binding without
 * each one re-implementing the listener.
 *
 * Usage:
 *   const [paletteOpen, setPaletteOpen] = useState(false);
 *   useCommandPaletteHotkey(setPaletteOpen);
 */
export function useCommandPaletteHotkey(setOpen) {
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setOpen]);
}
