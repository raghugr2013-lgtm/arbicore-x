import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api.js'
import { Panel, QueryView } from '../components/Panel.jsx'

const LABELS = ['', 'smart_money', 'whale', 'influencer', 'sniper', 'retail_fomo', 'rug_wallet']
const SOURCES = ['', 'curated', 'algorithmic']
const CHAINS = ['', 'solana', 'ethereum', 'arbitrum', 'base', 'optimism', 'polygon']

export default function WalletIntelligence() {
  const [label, setLabel] = useState('')
  const [labelSource, setLabelSource] = useState('')
  const [chain, setChain] = useState('')

  const q = useQuery({
    queryKey: ['wallets', label, labelSource, chain],
    queryFn: () => api.wallets({
      label: label || undefined,
      label_source: labelSource || undefined,
      chain: chain || undefined,
      limit: 200,
    }),
    refetchInterval: 60_000,
  })

  const summary = q.data?.items || []
  const counts = summary.reduce((acc, w) => {
    const key = w.label || 'unlabeled'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-6" data-testid="page-wallet-intel">
      <header>
        <div className="label-mono">wallet intelligence</div>
        <h1 className="text-3xl font-semibold tracking-tight">Curated &amp; algorithmic profiles</h1>
        <p className="text-sm text-ink-400 mt-1">
          Read-only census of <code className="font-mono text-ink-200">arbicore_wallet_metrics</code>.
        </p>
      </header>

      <Panel title="Filters" subtitle="query" testid="card-filters">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label>
            <span className="label-mono mb-1 block">label</span>
            <select className="input" value={label} onChange={(e) => setLabel(e.target.value)} data-testid="filter-label">
              {LABELS.map((v) => <option key={v} value={v}>{v || 'any'}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">source</span>
            <select className="input" value={labelSource} onChange={(e) => setLabelSource(e.target.value)} data-testid="filter-source">
              {SOURCES.map((v) => <option key={v} value={v}>{v || 'any'}</option>)}
            </select>
          </label>
          <label>
            <span className="label-mono mb-1 block">chain</span>
            <select className="input" value={chain} onChange={(e) => setChain(e.target.value)} data-testid="filter-chain">
              {CHAINS.map((v) => <option key={v} value={v}>{v || 'any'}</option>)}
            </select>
          </label>
        </div>
      </Panel>

      <Panel title="Label distribution" subtitle="present in result set" testid="card-distribution">
        <div className="flex flex-wrap gap-2" data-testid="distribution">
          {Object.entries(counts).map(([k, v]) => (
            <span key={k} className="pill bg-bg-raised text-ink-200">
              <span className="font-mono">{k}</span>
              <span className="font-mono text-accent-amber">{v}</span>
            </span>
          ))}
          {!Object.keys(counts).length && <span className="text-xs text-ink-400">no wallets match filters</span>}
        </div>
      </Panel>

      <Panel title={`Wallets (${q.data?.count ?? 0} / ${q.data?.total ?? 0})`} subtitle="profile rows" testid="card-wallets">
        <QueryView q={q} testidPrefix="wallets" empty={(d) => !d?.items?.length}>
          {(d) => (
            <div className="overflow-auto">
              <table className="min-w-full text-xs" data-testid="wallets-table">
                <thead className="text-ink-400">
                  <tr className="border-b border-bg-line">
                    <th className="text-left font-medium px-2 py-2">wallet_id</th>
                    <th className="text-left font-medium px-2 py-2">chain</th>
                    <th className="text-left font-medium px-2 py-2">label</th>
                    <th className="text-left font-medium px-2 py-2">source</th>
                  </tr>
                </thead>
                <tbody>
                  {(d.items || []).map((w) => (
                    <tr key={w.wallet_id} className="border-b border-bg-line/60 table-row-hover" data-testid="wallet-row">
                      <td className="px-2 py-2 font-mono text-ink-200 truncate max-w-[28rem]">{w.wallet_id}</td>
                      <td className="px-2 py-2">{w.chain || '—'}</td>
                      <td className="px-2 py-2">{w.label || '—'}</td>
                      <td className="px-2 py-2 text-ink-400">{w.label_source || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryView>
      </Panel>
    </div>
  )
}
