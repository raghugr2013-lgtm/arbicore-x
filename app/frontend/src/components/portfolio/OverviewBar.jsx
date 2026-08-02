import { fmtTime, fmtUsd } from "@/lib/fmt";

const STATUS_STYLE = {
  ok: { dot: "#34d399", label: "OK" },
  no_key: { dot: "#3d4a59", label: "NO KEY" },
  error: { dot: "#f87171", label: "ERROR" },
  rate_limited: { dot: "#fbbf24", label: "RATE LIMITED" },
};

export const OverviewBar = ({ data, onRefresh, refreshing }) => {
  const exchanges = data?.exchanges || {};
  const polling = data?.polling || {};
  const anyKey = Object.values(exchanges).some((e) => e.status && e.status !== "no_key");
  return (
    <div className="panel" data-testid="portfolio-overview">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-widest text-[#6b7888]">Total tracked equity</div>
          <div className="font-mono text-3xl font-bold" data-testid="portfolio-total-usd"
               style={{ color: data?.total_usd != null ? "#34d399" : "#6b7888" }}>
            {data?.total_usd != null ? fmtUsd(data.total_usd) : "—"}
          </div>
          {!anyKey && (
            <div className="font-mono text-[10px] text-[#6b7888]">add read-only keys to track real balances</div>
          )}
        </div>
        <div className="flex flex-wrap gap-2" data-testid="portfolio-exchange-chips">
          {Object.values(exchanges).map((e) => {
            const s = STATUS_STYLE[e.status] || STATUS_STYLE.no_key;
            return (
              <div key={e.exchange} data-testid={`portfolio-chip-${e.exchange}`}
                   className="border border-[#1f2a36] px-2.5 py-1.5 font-mono text-[10px]">
                <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: s.dot }} />
                <span className="font-bold uppercase">{e.exchange}</span>{" "}
                <span className="text-[#6b7888]">{s.label}</span>
                {e.total_usd != null && <span className="text-[#c9d4e0]"> · {fmtUsd(e.total_usd)}</span>}
                {e.latency_ms != null && e.status === "ok" && (
                  <span className="text-[#3d4a59]"> · {e.latency_ms}ms</span>
                )}
                {e.backoff_remaining_s != null && (
                  <span className="text-[#fbbf24]"> · retry in {e.backoff_remaining_s}s</span>
                )}
              </div>
            );
          })}
        </div>
        <div className="flex-1" />
        <div className="text-right">
          <button data-testid="portfolio-refresh-btn" onClick={onRefresh} disabled={refreshing}
                  className="font-mono text-[10px] font-bold tracking-widest px-3 py-1.5 border border-[#38bdf8] text-[#38bdf8] hover:bg-[#38bdf8]/10 disabled:opacity-50">
            {refreshing ? "POLLING…" : "↻ REFRESH NOW"}
          </button>
          <div className="font-mono text-[9px] text-[#3d4a59] mt-1" data-testid="portfolio-polling-status">
            auto-poll {polling.interval_s || 60}s · last cycle {polling.last_cycle_at ? fmtTime(polling.last_cycle_at) : "—"}
          </div>
        </div>
      </div>
    </div>
  );
};
