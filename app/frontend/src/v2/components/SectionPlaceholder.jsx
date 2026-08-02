/**
 * ArbiCore X — UI v2 · SectionPlaceholder (Slice 0)
 *
 * A shared "not yet built" pane used by every section that isn't part of
 * Slice 0's scope. It:
 *   - Names the section and its purpose (from NAV_SECTIONS).
 *   - Cites which slice will activate it (per docs/ui_v2/05_IMPLEMENTATION_ROADMAP.md).
 *   - Never fakes UI. Explicitly signals "not shipped" so no one mistakes
 *     it for the eventual real page.
 */
import { NAV_SECTIONS } from "@/v2/lib/nav";

export function SectionPlaceholder({ sectionKey, slice, journeys }) {
  const section = NAV_SECTIONS.find((s) => s.key === sectionKey);
  return (
    <section data-testid={`v2-placeholder-${sectionKey}`}>
      <h1 className="v2-page__title">{section?.label}</h1>
      <p className="v2-page__lede">{section?.lede}</p>

      <div className="v2-empty">
{`> Section not yet shipped.
> Scheduled: Slice ${slice} — docs/ui_v2/05_IMPLEMENTATION_ROADMAP.md
> Journeys enabled: ${(journeys || []).join(", ") || "—"}
> Slice 0 delivers only the application shell (header + left rail + routing).`}
      </div>
    </section>
  );
}
