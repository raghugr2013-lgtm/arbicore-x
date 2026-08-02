/**
 * ArbiCore X — UI v2 · Command palette (Slice 1)
 * Reuses shadcn <Command*> primitives. Scopes: Sections + Opportunities.
 * Opens on ⌘K (via useKeyboardShortcuts) or Header trigger.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { NAV_SECTIONS } from "@/v2/lib/nav";
import { v2Api } from "@/v2/lib/api";

export function CommandPalette({ open, onOpenChange }) {
  const navigate = useNavigate();
  const [opps, setOpps] = useState([]);

  useEffect(() => {
    if (!open) return;
    v2Api.opportunitiesList({ limit: 20 }).then((d) => setOpps(d.items || [])).catch(() => setOpps([]));
  }, [open]);

  const go = (path) => {
    onOpenChange(false);
    navigate(path);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <DialogTitle className="sr-only">Command palette</DialogTitle>
      <DialogDescription className="sr-only">
        Search assets, venues, and opportunities. Use arrow keys to navigate and Enter to select.
      </DialogDescription>
      <CommandInput placeholder="Search assets, venues, opportunities…" data-testid="v2-palette-input" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {NAV_SECTIONS.map((s) => (
            <CommandItem
              key={s.key}
              value={`nav ${s.key} ${s.label} ${s.lede}`}
              onSelect={() => go(s.path)}
              data-testid={`v2-palette-nav-${s.key}`}
            >
              <span>{s.label}</span>
              <span style={{ marginLeft: "auto", opacity: 0.55, fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
                G {s.shortcut}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
        {opps.length > 0 && (
          <>
            <CommandSeparator />
            <CommandGroup heading="Opportunities">
              {opps.slice(0, 12).map((o) => (
                <CommandItem
                  key={o.id}
                  value={`opp ${o.id} ${o.subject_id} ${o.opportunity_type} ${o.chain}`}
                  onSelect={() => go(`/v2/opportunities?id=${o.id}`)}
                  data-testid={`v2-palette-opp-${o.id}`}
                >
                  <span>{o.subject_id}</span>
                  <span style={{ marginLeft: 8, color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
                    {o.opportunity_type} · {o.chain}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        )}
      </CommandList>
    </CommandDialog>
  );
}
