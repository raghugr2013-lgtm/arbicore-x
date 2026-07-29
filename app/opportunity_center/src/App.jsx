import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './lib/api.js'
import Login from './pages/Login.jsx'
import Home from './pages/Home.jsx'
import Opportunities from './pages/Opportunities.jsx'
import WalletIntelligence from './pages/WalletIntelligence.jsx'
import Analytics from './pages/Analytics.jsx'
import SystemHealth from './pages/SystemHealth.jsx'
import { Activity, ListTree, Wallet, BarChart3, HeartPulse, LogOut } from 'lucide-react'

function Sidebar({ onLogout }) {
  const items = [
    { to: '/',                 label: 'Home',                Icon: Activity,    testid: 'nav-home' },
    { to: '/opportunities',    label: 'Opportunities',       Icon: ListTree,    testid: 'nav-opportunities' },
    { to: '/wallet-intel',     label: 'Wallet Intelligence', Icon: Wallet,      testid: 'nav-wallet-intel' },
    { to: '/analytics',        label: 'Analytics',           Icon: BarChart3,   testid: 'nav-analytics' },
    { to: '/system-health',    label: 'System Health',       Icon: HeartPulse,  testid: 'nav-system-health' },
  ]
  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col border-r border-bg-line bg-bg-panel/60 backdrop-blur">
      <div className="px-5 py-5 border-b border-bg-line">
        <div className="font-mono text-xs uppercase tracking-[0.18em] text-accent-amber">ArbiCore X</div>
        <div className="mt-1 text-lg font-semibold">Opportunity Center</div>
        <div className="mt-1 text-xs text-ink-400">read-only · phase 1</div>
      </div>
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {items.map(({ to, label, Icon, testid }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            data-testid={testid}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-accent-amber/10 text-accent-amber'
                  : 'text-ink-200 hover:bg-bg-raised hover:text-ink-50'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
      <button
        onClick={onLogout}
        data-testid="logout-btn"
        className="mx-3 mb-4 mt-2 flex items-center gap-2 rounded-md border border-bg-line px-3 py-2 text-sm text-ink-400 hover:border-accent-red/40 hover:text-accent-red"
      >
        <LogOut size={14} /> Logout
      </button>
    </aside>
  )
}

function Shell({ children, onLogout }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar onLogout={onLogout} />
      <main className="flex-1 min-w-0">
        <div className="mx-auto max-w-7xl px-6 py-6">{children}</div>
      </main>
    </div>
  )
}

export default function App() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const meQuery = useQuery({
    queryKey: ['me'],
    queryFn: api.me,
    retry: false,
  })

  const onLogout = async () => {
    try { await api.logout() } catch { /* ignore */ }
    qc.clear()
    navigate('/login', { replace: true })
  }

  if (meQuery.isLoading) {
    return (
      <div className="grid min-h-screen place-items-center text-ink-400" data-testid="app-loading">
        <div className="animate-pulse text-sm">authenticating…</div>
      </div>
    )
  }

  if (meQuery.isError || !meQuery.data) {
    return <Login onAuthed={() => meQuery.refetch()} />
  }

  return (
    <Shell onLogout={onLogout}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/wallet-intel" element={<WalletIntelligence />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/system-health" element={<SystemHealth />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </Shell>
  )
}
