/**
 * ArbiCore X — UI v2 · Application shell (Slice 0)
 *
 * Composes Header + LeftNavRail + a scrollable content area, and mounts
 * the section routes. Legacy UI is unaffected — this component is only
 * rendered under the /v2/* route tree.
 */
import { Route, Routes } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Header } from "@/v2/components/Header";
import { LeftNavRail } from "@/v2/components/LeftNavRail";
import HomePage from "@/v2/pages/HomePage";
import DiscoveryPage from "@/v2/pages/DiscoveryPage";
import OpportunitiesPage from "@/v2/pages/OpportunitiesPage";
import PortfolioPage from "@/v2/pages/PortfolioPage";
import IntelligencePage from "@/v2/pages/IntelligencePage";
import OperationsPage from "@/v2/pages/OperationsPage";
import SettingsPage from "@/v2/pages/SettingsPage";

import "@/v2/theme/tokens.css";

export function AppShell() {
  const { user, logout } = useAuth() || {};
  return (
    <div className="ui-v2-root" data-testid="v2-root">
      <div className="v2-app">
        <div className="v2-app__header">
          <Header username={user?.username} onLogout={logout} />
        </div>
        <div className="v2-app__rail">
          <LeftNavRail />
        </div>
        <main className="v2-app__content" data-testid="v2-content">
          <Routes>
            <Route index element={<HomePage />} />
            <Route path="discovery/*" element={<DiscoveryPage />} />
            <Route path="opportunities/*" element={<OpportunitiesPage />} />
            <Route path="portfolio/*" element={<PortfolioPage />} />
            <Route path="intelligence/*" element={<IntelligencePage />} />
            <Route path="operations/*" element={<OperationsPage />} />
            <Route path="settings/*" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
