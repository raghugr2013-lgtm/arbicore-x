/**
 * Opportunity Ledger research view.
 * Reads /api/arbicore/ledger only. No execution controls.
 */
import { useEffect, useState } from "react";
import { v2Api } from "@/v2/lib/api";
import { displayMoney, displayScalar, orderedLegs, pageWindow, RESEARCH_ACTIONS } from "@/v2/lib/ledgerFormat.mjs";

const inputStyle = {
  background: "var(--v2-bg-panel)",
  color: "var(--v2-text-primary)",
  border: "1px solid var(--v2-border-subtle)",
  fontFamily: "var(--v2-font-mono)",
  fontSize: 11,
  padding: "4px 6px",
  borderRadius: 2,
};

function Field({ label, value }) {
  return (
    <div style={{ minWidth: 140 }}>
      <div style={{ color: "var(--v2-text-muted)", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>{label}</div>
      <div style={{ color: "var(--v2-text-primary)", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>{displayScalar(value)}</div>
    </div>
  );
}

export default function LedgerExplorerPage() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState("");
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [chain, setChain] = useState("");
  const [family, setFamily] = useState("");
  const [provider, setProvider] = useState("");
  const [bundle, setBundle] = useState("");
  const [gate7, setGate7] = useState("");
  const [netMin, setNetMin] = useState("");
  const [netMax, setNetMax] = useState("");
  const [tsFrom, setTsFrom] = useState("");
  const [tsTo, setTsTo] = useState("");
  const [sort, setSort] = useState("net");
  const [order, setOrder] = useState("desc");

  useEffect(() => {
    v2Api.ledgerRuns().then((body) => {
      const list = body.runs || [];
      setRuns(list);
      if (list[0]) setRunId(list[0].run_id);
    }).catch(() => setError("Ledger runs could not be loaded."));
  }, []);

  useEffect(() => {
    if (!runId) return;
    setError("");
    v2Api.ledgerSummary(runId).then(setSummary).catch(() => setError("Run summary could not be loaded."));
  }, [runId]);

  useEffect(() => {
    if (!runId) return;
    v2Api.ledgerOpportunities({
      run_id: runId,
      chain: chain || undefined,
      family: family || undefined,
      provider: provider || undefined,
      bundle: bundle || undefined,
      gate_7: gate7 || undefined,
      net_min: netMin === "" ? undefined : netMin,
      net_max: netMax === "" ? undefined : netMax,
      ts_from: tsFrom || undefined,
      ts_to: tsTo || undefined,
      sort,
      order,
      page,
      page_size: 25,
    }).then((body) => {
      setItems(body.items || []);
      setTotal(body.total || 0);
    }).catch(() => setError("Opportunity list could not be loaded."));
  }, [runId, chain, family, provider, bundle, gate7, netMin, netMax, tsFrom, tsTo, sort, order, page]);

  const openDetail = (ledgerId) => {
    v2Api.ledgerOpportunity(ledgerId).then(setDetail).catch(() => setError("Opportunity detail could not be loaded."));
  };

  const download = async () => {
    const blob = await v2Api.ledgerExport(runId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `opportunity_ledger_${runId}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const window = pageWindow(total, page, 25);
  const families = Object.keys(summary?.strategy_distribution || {});
  const chains = Object.keys(summary?.chain_distribution || {});
  const providers = Object.keys(summary?.provider_distribution || {});
  const evidence = detail?.evidence || {};
  const strategy = evidence.strategy || {};
  const economics = evidence.economics || {};
  const gates = evidence.gates || {};
  const provenance = evidence.provenance || {};
  const legs = orderedLegs(evidence.legs);

  return (
    <section data-testid="ledger-explorer">
      <h1 className="v2-page__title">Opportunity Ledger</h1>
      <p className="v2-page__lede">
        Research view of stored ledger projections. Numbers come from the ledger API.
      </p>
      {error && <div data-testid="ledger-error" style={{ color: "var(--v2-text-muted)", marginBottom: 12 }}>{error}</div>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14, alignItems: "center" }} data-testid="ledger-filters">
        <select data-testid="ledger-run" style={inputStyle} value={runId} onChange={(e) => { setPage(1); setRunId(e.target.value); }}>
          {runs.map((run) => <option key={run.run_id} value={run.run_id}>{run.run_id}</option>)}
        </select>
        <select style={inputStyle} value={chain} onChange={(e) => { setPage(1); setChain(e.target.value); }}>
          <option value="">All chains</option>
          {chains.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select style={inputStyle} value={family} onChange={(e) => { setPage(1); setFamily(e.target.value); }}>
          <option value="">All families</option>
          {families.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select style={inputStyle} value={provider} onChange={(e) => { setPage(1); setProvider(e.target.value); }}>
          <option value="">All providers</option>
          {providers.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
        <select style={inputStyle} value={bundle} onChange={(e) => { setPage(1); setBundle(e.target.value); }}>
          <option value="">All bundle states</option>
          <option value="backed">Verifier bundle</option>
          <option value="decision_only">Decision only</option>
        </select>
        <select style={inputStyle} value={gate7} onChange={(e) => { setPage(1); setGate7(e.target.value); }}>
          <option value="">All Gate 7</option>
          <option value="FAIL">FAIL</option>
          <option value="PASS">PASS</option>
          <option value="NOT_EVALUATED">NOT_EVALUATED</option>
          <option value="unavailable">unavailable</option>
        </select>
        <input style={inputStyle} placeholder="Net min" value={netMin} onChange={(e) => { setPage(1); setNetMin(e.target.value); }} />
        <input style={inputStyle} placeholder="Net max" value={netMax} onChange={(e) => { setPage(1); setNetMax(e.target.value); }} />
        <input style={inputStyle} placeholder="From ISO or unix" value={tsFrom} onChange={(e) => { setPage(1); setTsFrom(e.target.value); }} />
        <input style={inputStyle} placeholder="To ISO or unix" value={tsTo} onChange={(e) => { setPage(1); setTsTo(e.target.value); }} />
        <select style={inputStyle} value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="net">Net</option>
          <option value="timestamp">Timestamp</option>
          <option value="chain">Chain</option>
          <option value="family">Strategy family</option>
        </select>
        <select style={inputStyle} value={order} onChange={(e) => setOrder(e.target.value)}>
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
        <button type="button" data-testid="ledger-export" onClick={download} style={inputStyle}>{RESEARCH_ACTIONS[0]}</button>
      </div>

      {summary && (
        <div data-testid="ledger-summary" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 10, marginBottom: 16 }}>
          <Field label="Run ID" value={summary.run_id} />
          <Field label="First verified" value={summary.period?.first_verified_at_iso} />
          <Field label="Last verified" value={summary.period?.last_verified_at_iso} />
          <Field label="Total" value={summary.total} />
          <Field label="Verifier backed" value={summary.verifier_backed} />
          <Field label="Decision only" value={summary.decision_only} />
          <Field label="Mean net" value={displayMoney(summary.net?.mean)} />
          <Field label="Best net" value={displayMoney(summary.net?.best)} />
          <Field label="Worst net" value={displayMoney(summary.net?.worst)} />
          <Field label="Count >= $0" value={summary.net?.ge_0} />
          <Field label="Count >= $25" value={summary.net?.ge_25} />
          <Field label="Best opportunity" value={summary.best_opportunity?.opportunity_id} />
          <Field label="Worst opportunity" value={summary.worst_opportunity?.opportunity_id} />
        </div>
      )}

      {summary && (
        <div data-testid="ledger-families" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12, fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
          {Object.entries(summary.strategy_distribution || {}).map(([name, count]) => (
            <span key={name}>{name} {count}</span>
          ))}
          <span>Gate 7 {Object.entries(summary.gate_7_status || {}).map(([name, count]) => `${name}:${count}`).join(" ")}</span>
        </div>
      )}

      <table data-testid="ledger-table" style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--v2-font-mono)", fontSize: 12 }}>
        <thead>
          <tr>
            {["Opportunity", "Run", "Timestamp", "Chain", "Family", "Provider", "Bundle", "Decision net", "Gate 7", "Final status"].map((heading) => (
              <th key={heading} style={{ textAlign: "left", padding: 8, color: "var(--v2-text-muted)", fontSize: 10 }}>{heading}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.ledger_id} data-testid={`ledger-row-${row.ledger_id}`} onClick={() => openDetail(row.ledger_id)} style={{ cursor: "pointer" }}>
              <td style={{ padding: 8 }}>{displayScalar(row.opportunity_id)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.run_id)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.timestamp)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.chain)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.strategy_family)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.provider)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.bundle_status)}</td>
              <td style={{ padding: 8 }}>{displayMoney(row.decision_net_usd)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.gate_7)}</td>
              <td style={{ padding: 8 }}>{displayScalar(row.final_status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div data-testid="ledger-pager" style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center" }}>
        <button type="button" style={inputStyle} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</button>
        <span style={{ fontFamily: "var(--v2-font-mono)", fontSize: 11 }}>
          {total === 0 ? "0" : `${window.start + 1}-${window.end}`} of {total}
        </span>
        <button type="button" style={inputStyle} onClick={() => setPage((value) => value + 1)}>Next</button>
      </div>

      {detail && (
        <article data-testid="ledger-detail" style={{ marginTop: 20 }}>
          <h2 style={{ fontSize: 16 }}>Opportunity detail</h2>
          <h3 style={{ fontSize: 13 }}>Identity</h3>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Field label="opportunity_id" value={detail.opportunity_id} />
            <Field label="ledger_id" value={detail.ledger_id} />
            <Field label="run_id" value={detail.run_id} />
            <Field label="candidate_id" value={detail.candidate_id} />
            <Field label="verifier_bundle_id" value={detail.verifier_bundle_id} />
          </div>
          <h3 style={{ fontSize: 13 }}>Strategy intelligence</h3>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Field label="Primary family" value={strategy.primary_family} />
            <Field label="Secondary tags" value={(strategy.secondary_tags || []).join(", ")} />
            <Field label="Confidence" value={strategy.confidence} />
            <Field label="Classifier" value={strategy.classifier_version} />
            <Field label="Completeness" value={strategy.classification_completeness} />
          </div>
          <pre data-testid="ledger-evidence" style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>{(strategy.evidence || []).join("\n") || "unavailable"}</pre>
          <h3 style={{ fontSize: 13 }}>Route / price path</h3>
          <table data-testid="ledger-legs">
            <thead>
              <tr>
                {["#", "In", "Out", "Protocol", "Venue", "Pool", "Input", "Output", "Quote", "Fee", "Quote time", "Block", "Source"].map((heading) => (
                  <th key={heading} style={{ textAlign: "left", fontSize: 10, padding: 4 }}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {legs.map((leg) => (
                <tr key={`${leg.leg_index}-${leg.pool}`}>
                  <td>{displayScalar(leg.leg_index)}</td>
                  <td>{displayScalar(leg.token_in)}</td>
                  <td>{displayScalar(leg.token_out)}</td>
                  <td>{displayScalar(leg.protocol)}</td>
                  <td>{displayScalar(leg.venue)}</td>
                  <td>{displayScalar(leg.pool)}</td>
                  <td>{displayScalar(leg.input_amount)}</td>
                  <td>{displayScalar(leg.output_amount)}</td>
                  <td>{displayScalar(leg.quote)}</td>
                  <td>{displayScalar(leg.fee_bps)}</td>
                  <td>{displayScalar(leg.quote_timestamp)}</td>
                  <td>{displayScalar(leg.block)}</td>
                  <td>{displayScalar(leg.source)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 style={{ fontSize: 13 }}>Economics</h3>
          <div data-testid="ledger-economics" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Field label="Gross spread" value={economics.gross_spread_pct} />
            <Field label="Gross profit" value={economics.gross_profit_usd} />
            <Field label="DEX fee %" value={economics.dex_fee_pct} />
            <Field label="DEX fee $" value={economics.dex_fee_usd} />
            <Field label="Flash-loan fee" value={economics.flash_loan_fee_usd} />
            <Field label="Gas" value={economics.gas_cost_usd} />
            <Field label="Slippage" value={economics.slippage_pct} />
            <Field label="MEV" value={economics.mev_penalty} />
            <Field label="Total cost" value={economics.total_cost_usd} />
            <Field label="True net" value={economics.true_net_usd} />
            <Field label="Net %" value={economics.true_net_pct} />
          </div>
          <h3 style={{ fontSize: 13 }}>Gates</h3>
          <div data-testid="ledger-gates">
            <Field label="Gate 7" value={gates.gate_7?.status} />
            <div data-testid="ledger-gate7-reason">{displayScalar(gates.gate_7?.reason)}</div>
            <Field label="Gate 8" value={gates.gate_8?.status} />
            <div>{displayScalar(gates.gate_8?.reason)}</div>
            <Field label="Gate 9" value={gates.gate_9?.status} />
            <div>{displayScalar(gates.gate_9?.reason)}</div>
          </div>
          <h3 style={{ fontSize: 13 }}>Provenance</h3>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <Field label="Provider" value={provenance.flash_loan_provider} />
            <Field label="Quote source" value={provenance.quote_source} />
            <Field label="Verifier" value={provenance.verifier_component} />
            <Field label="Calculator" value={provenance.calculator_version} />
            <Field label="Classifier" value={provenance.classifier_version} />
            <Field label="Git" value={provenance.git_sha} />
            <Field label="Config revision" value={provenance.network_config_revision} />
            <Field label="Verified at" value={detail.display_timestamp} />
          </div>
        </article>
      )}
    </section>
  );
}
