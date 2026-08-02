import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { CertificationPanel } from "@/components/execution/CertificationPanel";
import { CertificationReportPanel } from "@/components/execution/CertificationReportPanel";
import { FundTrackingPanel } from "@/components/execution/FundTrackingPanel";
import { FundingCalculator } from "@/components/execution/FundingCalculator";
import { IntegrationPrepPanel } from "@/components/execution/IntegrationPrepPanel";
import { ShadowModePanel } from "@/components/execution/ShadowModePanel";
import { ShadowCampaignPanel } from "@/components/execution/ShadowCampaignPanel";
import { CertificationReviewPanel } from "@/components/execution/CertificationReviewPanel";
import { CertificationEvidencePanel } from "@/components/execution/CertificationEvidencePanel";
import { VenueRegistryPanel } from "@/components/execution/VenueRegistryPanel";
import { ExchangeIntelligencePanel } from "@/components/execution/ExchangeIntelligencePanel";
import { ProductionWorkflowPanel } from "@/components/execution/ProductionWorkflowPanel";
import { PermanentLedgerPanel } from "@/components/execution/PermanentLedgerPanel";
import { SafetyInterlockPanel } from "@/components/execution/SafetyInterlockPanel";
import { OpportunityGatePanel } from "@/components/execution/OpportunityGatePanel";
import { PriceVerificationPanel } from "@/components/execution/PriceVerificationPanel";
import { ArbitrageIntelPanel } from "@/components/execution/ArbitrageIntelPanel";
import { FeeMatrixPanel } from "@/components/execution/FeeMatrixPanel";
import { FeeProvenancePanel } from "@/components/execution/FeeProvenancePanel";
import { FreshCycleAnalyticsPanel } from "@/components/execution/FreshCycleAnalyticsPanel";
import { FreshCycleWatchPanel } from "@/components/execution/FreshCycleWatchPanel";
import { RealCyclePanel } from "@/components/execution/RealCyclePanel";
import { BdagTransferEvidencePanel } from "@/components/execution/BdagTransferEvidencePanel";
import { EvidenceAccuracyPanel } from "@/components/execution/EvidenceAccuracyPanel";
import { BuyPriceAuditPanel } from "@/components/execution/BuyPriceAuditPanel";
import { ExecutableQuoteResolverPanel } from "@/components/execution/ExecutableQuoteResolverPanel";
import { QuoteResolverPanel } from "@/components/execution/QuoteResolverPanel";
import { QuoteCapturePanel } from "@/components/execution/QuoteCapturePanel";
import { ArbitrageCyclesPanel } from "@/components/execution/ArbitrageCyclesPanel";
import { WalletObserverPanel } from "@/components/execution/WalletObserverPanel";
import { CycleTimingPanel } from "@/components/execution/CycleTimingPanel";
import { HistoricalDriftPanel } from "@/components/execution/HistoricalDriftPanel";
import { LedgerPanel } from "@/components/execution/LedgerPanel";
import { RecoveryProofPanel } from "@/components/execution/RecoveryProofPanel";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Execution() {
  const [status, setStatus] = useState(null);

  const loadStatus = useCallback(() => {
    axios.get(`${API}/execution/status`).then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    loadStatus();
    const t = setInterval(loadStatus, 8000);
    return () => clearInterval(t);
  }, [loadStatus]);

  const shadowOn = status?.shadow_enabled;

  return (
    <div className="px-4 pb-10 max-w-[1500px] mx-auto" data-testid="execution-page">
      <div className="flex flex-wrap items-center gap-3 py-3 border-b border-[#1f2a36] mb-4">
        <div className="font-mono text-sm font-bold tracking-wider">EXECUTION FRAMEWORK</div>
        <span data-testid="execution-phase" className="text-[10px] font-mono text-[#38bdf8]">{status?.phase || "loading…"}</span>
        <div className="flex-1" />
        <span data-testid="execution-mode" className="text-[10px] font-mono font-bold px-2 py-0.5 border"
              style={{ borderColor: shadowOn ? "#38bdf8" : "#6b7888", color: shadowOn ? "#38bdf8" : "#6b7888" }}>
          {status?.mode || "—"}
        </span>
      </div>

      <div className="mb-4 border px-3 py-2 font-mono text-[11px]"
           data-testid="execution-sim-banner"
           style={{ borderColor: shadowOn ? "rgba(56,189,248,0.4)" : "rgba(255,178,36,0.4)",
                    background: shadowOn ? "rgba(56,189,248,0.05)" : "rgba(255,178,36,0.05)",
                    color: shadowOn ? "#38bdf8" : "#ffb224" }}>
        {shadowOn
          ? "◆ SHADOW MODE ACTIVE — running the full workflow off LIVE market data, recording would-purchase / would-transfer / would-sell decisions. STILL NON-EXECUTING: no wallet transactions, no exchange transactions, no withdrawals, no fund movement."
          : "⚠ SIMULATION / DRY-RUN — Execution & wallet signing DISABLED. Enable Shadow Mode below to validate the workflow against live data (still non-executing). No fund movement occurs in any mode."}
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12"><ArbitrageCyclesPanel /></div>
        <div className="col-span-12"><WalletObserverPanel /></div>
        <div className="col-span-12"><CycleTimingPanel /></div>
        <div className="col-span-12"><HistoricalDriftPanel /></div>
        <div className="col-span-12"><QuoteCapturePanel /></div>
        <div className="col-span-12"><QuoteResolverPanel /></div>
        <div className="col-span-12"><ExecutableQuoteResolverPanel /></div>
        <div className="col-span-12"><BuyPriceAuditPanel /></div>
        <div className="col-span-12"><RealCyclePanel /></div>
        <div className="col-span-12"><EvidenceAccuracyPanel /></div>
        <div className="col-span-12"><BdagTransferEvidencePanel /></div>
        <div className="col-span-12"><FreshCycleAnalyticsPanel /></div>
        <div className="col-span-12"><FeeProvenancePanel /></div>
        <div className="col-span-12"><FreshCycleWatchPanel /></div>
        <div className="col-span-12"><SafetyInterlockPanel /></div>
        <div className="col-span-12 xl:col-span-7"><VenueRegistryPanel /></div>
        <div className="col-span-12 xl:col-span-5"><CertificationPanel onChanged={loadStatus} /></div>
        <div className="col-span-12"><ExchangeIntelligencePanel /></div>
        <div className="col-span-12"><ProductionWorkflowPanel /></div>
        <div className="col-span-12"><OpportunityGatePanel /></div>
        <div className="col-span-12"><PriceVerificationPanel /></div>
        <div className="col-span-12 xl:col-span-7"><ShadowModePanel onChanged={loadStatus} /></div>
        <div className="col-span-12 xl:col-span-5"><FundingCalculator /></div>
        <div className="col-span-12"><FundTrackingPanel status={status} onChanged={loadStatus} /></div>
        <div className="col-span-12"><ArbitrageIntelPanel /></div>
        <div className="col-span-12"><PermanentLedgerPanel /></div>
        <div className="col-span-12 xl:col-span-7"><LedgerPanel /></div>
        <div className="col-span-12 xl:col-span-5"><FeeMatrixPanel /></div>
        <div className="col-span-12"><RecoveryProofPanel /></div>
        <div className="col-span-12"><ShadowCampaignPanel onChanged={loadStatus} /></div>
        <div className="col-span-12"><IntegrationPrepPanel /></div>
        <div className="col-span-12"><CertificationReportPanel /></div>
        <div className="col-span-12"><CertificationReviewPanel /></div>
        <div className="col-span-12"><CertificationEvidencePanel /></div>
      </div>
    </div>
  );
}
