import { useQuery } from '@tanstack/react-query'

export function Panel({ title, subtitle, children, action, testid }) {
  return (
    <section data-testid={testid} className="panel panel-pad">
      <header className="flex items-start justify-between gap-3">
        <div>
          {subtitle && <div className="label-mono mb-1">{subtitle}</div>}
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone = 'default', testid }) {
  const toneClass = {
    default: 'text-ink-50',
    green: 'text-accent-green',
    amber: 'text-accent-amber',
    red:   'text-accent-red',
    violet:'text-accent-violet',
  }[tone] || 'text-ink-50'
  return (
    <div className="flex flex-col gap-1" data-testid={testid}>
      <div className="label-mono">{label}</div>
      <div className={`num-xl ${toneClass}`}>{value ?? '—'}</div>
      {hint && <div className="text-xs text-ink-400">{hint}</div>}
    </div>
  )
}

export function Loader({ testid }) {
  return <div data-testid={testid} className="text-xs text-ink-400 animate-pulse">loading…</div>
}

export function ErrorBox({ error, testid }) {
  return <div data-testid={testid} className="text-xs text-accent-red">{error?.message || 'request failed'}</div>
}

export function EmptyState({ children, testid }) {
  return <div data-testid={testid} className="text-xs text-ink-400 italic">{children}</div>
}

// thin wrapper that renders Loader / ErrorBox / children for the common pattern
export function QueryView({ q, testidPrefix, children, empty }) {
  if (q.isLoading) return <Loader testid={`${testidPrefix}-loading`} />
  if (q.isError) return <ErrorBox error={q.error} testid={`${testidPrefix}-error`} />
  if (empty && empty(q.data)) return <EmptyState testid={`${testidPrefix}-empty`}>no data</EmptyState>
  return children(q.data)
}

// re-export so pages can import { useQuery } from this module if they want
export { useQuery }
