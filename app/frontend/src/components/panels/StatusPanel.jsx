import { fmtTime } from "@/lib/fmt";

const Dot = ({ ok, unknown }) => (
  <span className={`inline-block w-2 h-2 ${unknown ? "bg-[#6b7888]" : ok ? "bg-[#34d399] pulse-dot" : "bg-[#f87171]"}`} />
);

export const StatusPanel = ({ system }) => {
  const exchanges = system?.exchanges || {};
  const networks = system?.networks || {};
  const events = system?.events || [];
  const websockets = system?.websockets || {};
  return (
    <div className="panel" data-testid="status-panel">
      <div className="panel-title">System Status</div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Collectors</div>
          {Object.entries(exchanges).map(([ex, st]) => (
            <div key={ex} data-testid={`status-exchange-${ex}`} className="flex items-center gap-2 text-[11px] font-mono py-0.5">
              <Dot ok={st.listed && st.ticker_age_s != null && st.ticker_age_s < 30} unknown={st.listed == null} />
              <span className="uppercase font-bold w-16">{ex}</span>
              <span className="text-[#6b7888]">
                {st.listed === false ? "not listed" : st.ticker_age_s != null ? `tick ${Math.round(st.ticker_age_s)}s` : "—"}
              </span>
            </div>
          ))}
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mt-3 mb-1">WS Feeds (primary)</div>
          {Object.entries(websockets).map(([ex, ws]) => (
            <div key={ex} data-testid={`status-ws-${ex}`} className="flex items-center gap-2 text-[11px] font-mono py-0.5">
              <Dot ok={ws.mode === "ws"} />
              <span className="uppercase font-bold w-16">{ex}</span>
              <span className={ws.mode === "ws" ? "text-[#34d399]" : "text-[#fbbf24]"}>
                {ws.mode === "ws" ? `WS ${ws.last_msg_age_s != null ? Math.round(ws.last_msg_age_s) + "s" : ""}` : "REST fallback"}
              </span>
            </div>
          ))}
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mt-3 mb-1">Networks (RPC)</div>
          {Object.entries(networks).map(([key, n]) => (
            <div key={key} data-testid={`status-network-${key}`} className="flex items-center gap-2 text-[11px] font-mono py-0.5">
              <Dot ok={n.healthy} />
              <span className="uppercase font-bold w-20">{key}</span>
              <span className="text-[#6b7888]">
                {n.healthy ? `#${n.block_number} · ${n.latency_ms}ms` : "unreachable"}
              </span>
            </div>
          ))}
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-[#6b7888] mb-1">Events</div>
          <div className="max-h-44 overflow-y-auto pr-1" data-testid="events-list">
            {events.length === 0 && <div className="text-[11px] font-mono text-[#6b7888]">no events</div>}
            {events.map((e, i) => (
              <div key={i} className="text-[10px] font-mono py-0.5 border-b border-[#1f2a36]/40">
                <span className="text-[#6b7888]">{fmtTime(e.ts)}</span>{" "}
                <span className={e.level === "error" ? "text-[#f87171]" : e.level === "warn" ? "text-[#fbbf24]" : "text-[#38bdf8]"}>
                  [{e.source}]
                </span>{" "}
                <span className="text-[#c9d4e0]">{e.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
