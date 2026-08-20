/**
 * ArbiCore X — UI v2 · Navigation registry (Slice 0)
 *
 * The 7 canonical top-level sections per docs/ui_v2/03_INFORMATION_ARCHITECTURE.md.
 * Single source of truth for the left icon rail, breadcrumb, and future ⌘K
 * palette scopes. Slice 0 mounts placeholder pages; individual slices (1-6)
 * activate real screens.
 *
 * `label` is what the operator sees. `key` is used for keyboard nav shortcuts
 * (`G` + first letter → jump to section, see design_language.md §6).
 */
import {
  Activity,
  Compass,
  LayoutGrid,
  Wallet,
  Brain,
  Settings2,
  Cog,
  Zap,
  Route as RouteIcon,
  ShieldCheck,
} from "lucide-react";

export const NAV_SECTIONS = [
  {
    key: "control",
    label: "Control",
    path: "/dashboard/control",
    Icon: ShieldCheck,
    shortcut: "C",
    lede: "Operator Control Center — readiness, modes, emergency stop.",
  },
  {
    key: "home",
    label: "Home",
    path: "/v2",
    end: true,
    Icon: Activity,
    shortcut: "H",
    lede: "Operator briefing — Pulse, Priorities, Vitals.",
  },
  {
    key: "discovery",
    label: "Discovery",
    path: "/v2/discovery",
    Icon: Compass,
    shortcut: "D",
    lede: "Inbox of candidate assets and venues surfaced from external sources.",
  },
  {
    key: "opportunities",
    label: "Opportunities",
    path: "/v2/opportunities",
    Icon: LayoutGrid,
    shortcut: "O",
    lede: "Universal opportunity feed across all 8 canonical arbitrage families.",
  },
  {
    key: "portfolio",
    label: "Portfolio",
    path: "/v2/portfolio",
    Icon: Wallet,
    shortcut: "P",
    lede: "Positions, ledger, transfers, deployable capital.",
  },
  {
    key: "intelligence",
    label: "Intelligence",
    path: "/v2/intelligence",
    Icon: Brain,
    shortcut: "I",
    lede: "Recommendations, confidence, analytics, learning, evidence.",
  },
  {
    key: "operations",
    label: "Operations",
    path: "/v2/operations",
    Icon: Cog,
    shortcut: "N",
    lede: "Scanners, cycles, venues, interlock, integrations.",
  },
  {
    key: "settings",
    label: "Settings",
    path: "/v2/settings",
    Icon: Settings2,
    shortcut: "S",
    lede: "Account, vault, alerts, execution config, docs & help.",
  },
  {
    key: "flash-loan-operator",
    label: "Flash Loan",
    path: "/v2/flash-loan-operator",
    Icon: Zap,
    shortcut: "F",
    lede: "Controlled LIMITED_LIVE flash-loan operator workflow (Phase 7B).",
  },
  {
    key: "journey",
    label: "Journey",
    path: "/v2/journey",
    Icon: RouteIcon,
    shortcut: "J",
    lede: "14-stage guided Flash Loan operator journey (Phase 10.7).",
  },
];
