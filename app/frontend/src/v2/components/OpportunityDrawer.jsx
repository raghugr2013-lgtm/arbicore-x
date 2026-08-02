/**
 * ArbiCore X — UI v2 · Opportunity Drawer (Slice 1)
 * Reuses shadcn <Sheet*> + <Tabs*>. 6 tabs per design_language.md:
 * Overview · Reasoning · Verification · Quote · Sizing · Evidence
 */
import { useEffect, useState } from "react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { v2Api } from "@/v2/lib/api";
import {
  VerdictBadge,
  ConfidencePill,
  SafetyPill,
  FreshnessBadge,
  fmtUsd,
  fmtPct,
  fmtBps,
} from "@/v2/components/Primitives";
import { toast } from "sonner";
import { ExecutionTimeline } from "@/v2/components/ExecutionTimeline";

function Row({ k, v, mono }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
      <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>{k}</span>
      <span style={{ color: "var(--v2-text-primary)", fontFamily: mono ? "var(--v2-font-mono)" : "var(--v2-font-body)", fontSize: 12 }}>{v ?? "—"}</span>
    </div>
  );
}

function TabHeading({ children }) {
  return (
    <div style={{ color: "var(--v2-text-secondary)", fontSize: 11, letterSpacing: 1, textTransform: "uppercase", fontFamily: "var(--v2-font-mono)", margin: "8px 0 6px" }}>
      {children}
    </div>
  );
}

export function OpportunityDrawer({ id, open, onOpenChange, onActioned }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !id) return;
    setLoading(true);
    v2Api.opportunityDetail(id)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [id, open]);

  const doApprove = async () => {
    if (!id || busy) return;
    setBusy(true);
    try {
      await v2Api.approveOpportunity(id);
      toast.success(`Approved ${data?.subject_id || id}`);
      onActioned && onActioned("approve", id);
      onOpenChange(false);
    } catch (e) {
      toast.error("Approval failed");
    } finally {
      setBusy(false);
    }
  };
  const doReject = async () => {
    if (!id || busy) return;
    setBusy(true);
    try {
      await v2Api.rejectOpportunity(id);
      toast.success(`Rejected ${data?.subject_id || id}`);
      onActioned && onActioned("reject", id);
      onOpenChange(false);
    } catch (e) {
      toast.error("Reject failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="ui-v2-root"
        style={{ background: "var(--v2-bg-surface)", borderLeft: "1px solid var(--v2-border-subtle)", color: "var(--v2-text-primary)", width: 480, maxWidth: "100vw", padding: 0 }}
        data-testid="v2-opp-drawer"
      >
        <div style={{ padding: 16, borderBottom: "1px solid var(--v2-border-subtle)" }}>
          <SheetHeader>
            <SheetTitle style={{ color: "var(--v2-text-strong)", fontSize: 15, letterSpacing: 0.5, fontFamily: "var(--v2-font-body)" }} data-testid="v2-drawer-title">
              {loading ? "Loading…" : (data?.subject_id || "Opportunity")}
            </SheetTitle>
          </SheetHeader>
          {data && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <VerdictBadge verdict={data.verdict} testid="v2-drawer-verdict" />
              <ConfidencePill value={data.confidence} testid="v2-drawer-conf" />
              <SafetyPill value={data.safety} testid="v2-drawer-safety" />
              <FreshnessBadge ageSeconds={data.age_s} testid="v2-drawer-fresh" />
              <span style={{ color: "var(--v2-text-muted)", fontFamily: "var(--v2-font-mono)", fontSize: 10 }}>
                {data.opportunity_type} · {data.chain}
              </span>
            </div>
          )}
        </div>

        {data && (
          <div style={{ padding: 16 }}>
            <Tabs defaultValue="overview" data-testid="v2-drawer-tabs">
              <TabsList
                style={{ background: "var(--v2-bg-panel)", border: "1px solid var(--v2-border-subtle)", padding: 2, borderRadius: 2, gap: 2, display: "flex", width: "100%", justifyContent: "flex-start", overflowX: "auto", flexWrap: "nowrap" }}
              >
                <TabsTrigger value="overview" data-testid="v2-tab-overview" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Overview</TabsTrigger>
                <TabsTrigger value="reasoning" data-testid="v2-tab-reasoning" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Reasoning</TabsTrigger>
                <TabsTrigger value="verification" data-testid="v2-tab-verification" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Verify</TabsTrigger>
                <TabsTrigger value="quote" data-testid="v2-tab-quote" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Quote</TabsTrigger>
                <TabsTrigger value="sizing" data-testid="v2-tab-sizing" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Sizing</TabsTrigger>
                <TabsTrigger value="evidence" data-testid="v2-tab-evidence" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Evidence</TabsTrigger>
                <TabsTrigger value="timeline" data-testid="v2-tab-timeline" style={{ flex: "0 0 auto", whiteSpace: "nowrap" }}>Timeline</TabsTrigger>
              </TabsList>

              <TabsContent value="overview">
                <TabHeading>Route</TabHeading>
                <Row k="Route" v={data.route} mono />
                <Row k="Spread" v={fmtBps(data.spread_bps)} mono />
                <Row k="Depth" v={fmtUsd(data.depth_usd)} mono />
                <TabHeading>Return estimate</TabHeading>
                <Row k="Low" v={fmtPct(data.return_low)} mono />
                <Row k="High" v={fmtPct(data.return_high)} mono />
              </TabsContent>

              <TabsContent value="reasoning">
                <TabHeading>Confidence breakdown</TabHeading>
                {data.reasoning?.confidence_breakdown?.map((f, i) => (
                  <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--v2-border-subtle)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span style={{ color: "var(--v2-text-primary)", fontSize: 12 }}>{f.factor}</span>
                      <span className="v2-num" style={{ color: f.delta >= 0 ? "var(--v2-verdict-go)" : "var(--v2-verdict-no-hard)", fontSize: 12 }}>
                        {f.delta >= 0 ? "+" : ""}{f.delta}
                      </span>
                    </div>
                    <div style={{ color: "var(--v2-text-muted)", fontSize: 11 }}>{f.notes}</div>
                  </div>
                ))}
                <TabHeading>Gates</TabHeading>
                <Row k="Passed" v={(data.reasoning?.gates_passed || []).join(", ") || "—"} mono />
                <Row k="Dropped" v={(data.reasoning?.gates_dropped || []).join(", ") || "—"} mono />
              </TabsContent>

              <TabsContent value="verification">
                <TabHeading>Source</TabHeading>
                <Row k="Quote source" v={data.verification?.quote_source} mono />
                <Row k="Last verified" v={data.verification?.last_verified_at} mono />
                <Row k="Fresh window" v={`${data.verification?.fresh_window_s}s`} mono />
                <Row k="Stale" v={data.verification?.stale ? "YES" : "NO"} mono />
              </TabsContent>

              <TabsContent value="quote">
                <TabHeading>Legs</TabHeading>
                <Row k="Buy venue" v={data.quote?.buy_venue} mono />
                <Row k="Sell venue" v={data.quote?.sell_venue} mono />
                <TabHeading>Prices</TabHeading>
                <Row k="Buy" v={data.quote?.buy_price} mono />
                <Row k="Sell" v={data.quote?.sell_price} mono />
                <Row k="Size" v={fmtUsd(data.quote?.size_usd)} mono />
                <Row k="Est. gas" v={fmtUsd(data.quote?.estimated_gas_usd)} mono />
              </TabsContent>

              <TabsContent value="sizing">
                <TabHeading>Recommendations</TabHeading>
                <Row k="Recommended" v={fmtUsd(data.sizing?.recommended_usd)} mono />
                <Row k="Max" v={fmtUsd(data.sizing?.max_usd)} mono />
                <Row k="Min" v={fmtUsd(data.sizing?.min_usd)} mono />
              </TabsContent>

              <TabsContent value="evidence">
                <div className="v2-empty">
                  {"> No cycle attached yet.\n> Evidence bundle becomes available after execution.\n> Press E to download in a cycle context (Slice 4)."}
                </div>
              </TabsContent>

              <TabsContent value="timeline">
                <TabHeading>Per-opportunity Execution Timeline</TabHeading>
                <ExecutionTimeline opportunityId={id} />
              </TabsContent>
            </Tabs>

            <div style={{ display: "flex", gap: 8, marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--v2-border-subtle)" }}>
              <button
                type="button"
                onClick={doApprove}
                disabled={busy}
                data-testid="v2-drawer-approve"
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: "var(--v2-accent-base)",
                  color: "var(--v2-accent-onSolid)",
                  border: "1px solid var(--v2-accent-base)",
                  fontFamily: "var(--v2-font-mono)",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 1.5,
                  borderRadius: 2,
                  cursor: busy ? "not-allowed" : "pointer",
                  opacity: busy ? 0.5 : 1,
                }}
              >
                APPROVE (A)
              </button>
              <button
                type="button"
                onClick={doReject}
                disabled={busy}
                data-testid="v2-drawer-reject"
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  background: "transparent",
                  color: "var(--v2-verdict-no-hard)",
                  border: "1px solid var(--v2-verdict-no-hard)",
                  fontFamily: "var(--v2-font-mono)",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 1.5,
                  borderRadius: 2,
                  cursor: busy ? "not-allowed" : "pointer",
                  opacity: busy ? 0.5 : 1,
                }}
              >
                REJECT (R)
              </button>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
