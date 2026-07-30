/**
 * ArbiCore X — UI v2 · Left icon rail (Slice 0)
 *
 * 64px vertical rail matching Binance Desktop conventions. Icon + micro
 * label per section. `NavLink` from react-router-dom keeps `aria-current`
 * accurate, which our CSS uses to draw the active-state amber marker.
 */
import { NavLink } from "react-router-dom";
import { NAV_SECTIONS } from "@/v2/lib/nav";

export function LeftNavRail() {
  return (
    <nav className="v2-rail" data-testid="v2-rail" aria-label="Primary sections">
      {NAV_SECTIONS.map(({ key, label, path, end, Icon }) => (
        <NavLink
          key={key}
          to={path}
          end={!!end}
          className="v2-rail__link"
          data-testid={`v2-rail-${key}`}
          title={label}
        >
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </NavLink>
      ))}
      <div className="v2-rail__spacer" />
    </nav>
  );
}
