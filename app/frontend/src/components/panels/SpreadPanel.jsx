import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtPct, fmtPrice, fmtTime, pctClass } from "@/lib/fmt";

const Row = ({ label, value, cls = "", testId }) => (
  <div className="flex justify-between items-baseline py-1 border-b border-[#1f2a36]/50">
    <span className="text-[10px] uppercase tracking-widest text-[#6b7888]">{label}</span>
    <span data-testid={testId} className={`font-mono text-sm font-bold ${cls}`}>{value}</span>
  </div>
);

export const SpreadPanel = ({ evaluation, history }) => {
  const sp = evaluation?.spread || {};
  const be = evaluation?.breakeven || {};
  const buy = evaluation?.inputs?.buy_price;
  const srcMap = { portal: "live portal", position: "position cost", manual_override: "manual override", manual_fallback: "manual fallback" };
  const src = srcMap[evaluation?.inputs?.price_source];
  const data = (history || []).map((h) => ({ t: fmtTime(h.ts), net: h.net_pct, gross: h.gross_pct }));
  return (
    <div className="panel" data-testid="spread-panel">
      <div className="panel-title">Spread Analysis</div>
      <Row label={`Buy price${src ? ` · ${src}` : ""}`} value={fmtPrice(buy)} testId="spread-buy-price" />
      <Row label="Gross spread" value={fmtPct(sp.gross_pct)} cls={pctClass(sp.gross_pct)} testId="spread-gross" />
      <Row label="Net spread (fees in)" value={fmtPct(sp.net_pct)} cls={pctClass(sp.net_pct)} testId="spread-net" />
      <Row label="Exec VWAP @ qty" value={fmtPrice(sp.vwap_at_qty)} />
      <Row label="Breakeven price" value={fmtPrice(be.price)} testId="breakeven-price" />
      <Row label="Breakeven distance" value={fmtPct(be.distance_pct)} cls={pctClass(be.distance_pct)} testId="breakeven-distance" />
      <div className="h-28 mt-3" data-testid="spread-history-chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
            <XAxis dataKey="t" tick={{ fontSize: 8, fill: "#6b7888" }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 8, fill: "#6b7888" }} domain={["auto", "auto"]} />
            <Tooltip
              contentStyle={{ background: "#10161e", border: "1px solid #1f2a36", fontSize: 11, fontFamily: "IBM Plex Mono" }}
              formatter={(v) => (v == null ? "—" : v.toFixed(2) + "%")}
            />
            <ReferenceLine y={0} stroke="#6b7888" strokeDasharray="3 3" />
            <Line type="linear" dataKey="net" stroke="#38bdf8" dot={false} strokeWidth={1.5} isAnimationActive={false} name="net %" />
            <Line type="linear" dataKey="gross" stroke="#ffb224" dot={false} strokeWidth={1} isAnimationActive={false} name="gross %" />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex gap-4 text-[9px] font-mono text-[#6b7888] mt-1">
        <span><span className="text-[#38bdf8]">━</span> NET</span>
        <span><span className="text-[#ffb224]">━</span> GROSS</span>
      </div>
    </div>
  );
};
