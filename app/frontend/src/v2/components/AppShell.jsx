/**
 * ArbiCore X — UI v2 · Application shell (Slice 1)
 * Header + LeftNavRail + Content + CommandPalette + global keyboard hook.
 */
import { useCallback, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Header } from "@/v2/components/Header";
import { LeftNavRail } from "@/v2/components/LeftNavRail";
import { CommandPalette } from "@/v2/components/CommandPalette";
import { useKeyboardShortcuts } from "@/v2/hooks/useKeyboardShortcuts";
import HomePage from "@/v2/pages/HomePage";
import OpsCenter from "@/v2/pages/OpsCenter";
import DiscoveryPage from "@/v2/pages/DiscoveryPage";
import OpportunitiesPage from "@/v2/pages/OpportunitiesPage";
import PortfolioPage from "@/v2/pages/PortfolioPage";
import IntelligencePage from "@/v2/pages/IntelligencePage";
import OperationsPage from "@/v2/pages/OperationsPage";
import SettingsPage from "@/v2/pages/SettingsPage";
import FlashLoanOperatorPage from "@/v2/pages/FlashLoanOperatorPage";
import LimitedLiveWizardPage from "@/v2/pages/LimitedLiveWizardPage";
import FlashLoanJourneyPage from "@/v2/pages/FlashLoanJourneyPage";
import ExecutorVerifyPage from "@/v2/pages/ExecutorVerifyPage";
import PostTradeDashboardPage from "@/v2/pages/PostTradeDashboardPage";

import "@/v2/theme/tokens.css";

export function AppShell() {
  const { user, logout } = useAuth() || {};
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  useKeyboardShortcuts({ onPalette: openPalette, onEscape: closePalette });
  return (
    <div className="ui-v2-root" data-testid="v2-root">
      <div className="v2-app">
        <div className="v2-app__header">
          <Header username={user?.username} onLogout={logout} onOpenPalette={openPalette} />
        </div>
        <div className="v2-app__rail">
          <LeftNavRail />
        </div>
        <main className="v2-app__content" data-testid="v2-content">
          <Routes>
            <Route index element={<OpsCenter />} />
            <Route path="ops" element={<OpsCenter />} />
            <Route path="home" element={<HomePage />} />
            <Route path="discovery/*" element={<DiscoveryPage />} />
            <Route path="opportunities/*" element={<OpportunitiesPage />} />
            <Route path="portfolio/*" element={<PortfolioPage />} />
            <Route path="intelligence/*" element={<IntelligencePage />} />
            <Route path="operations/*" element={<OperationsPage />} />
            <Route path="settings/*" element={<SettingsPage />} />
            <Route path="flash-loan-operator/*" element={<FlashLoanOperatorPage />} />
            <Route path="wizard/*" element={<LimitedLiveWizardPage />} />
            <Route path="journey/*" element={<FlashLoanJourneyPage />} />
            <Route path="executor-verify/*" element={<ExecutorVerifyPage />} />
            <Route path="post-trade/*" element={<PostTradeDashboardPage />} />
          </Routes>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: "var(--v2-bg-surface)",
            border: "1px solid var(--v2-border-subtle)",
            color: "var(--v2-text-primary)",
            borderRadius: 2,
            fontFamily: "var(--v2-font-mono)",
            fontSize: 12,
          },
        }}
      />
    </div>
  );
}
