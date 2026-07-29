import "@/App.css";
import { BrowserRouter, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import ApprovalConsole from "@/pages/ApprovalConsole";
import Dashboard from "@/pages/Dashboard";
import DocsViewer from "@/pages/DocsViewer";
import Execution from "@/pages/Execution";
import Login from "@/pages/Login";
import OperatorConsole from "@/pages/OperatorConsole";
import Portfolio from "@/pages/Portfolio";
import Settings from "@/pages/Settings";
import VenueMonitor from "@/pages/VenueMonitor";

const Header = () => {
  const { user, logout } = useAuth();
  return (
    <header className="term-header" data-testid="app-header">
      <div className="brand">
        <span className="brand-mark">▰▰</span>
        <span className="brand-name">ARBICORE</span>
        <span className="brand-sub">UNIVERSAL ARBITRAGE INTELLIGENCE</span>
      </div>
      {user && (
        <nav className="flex items-center gap-1" data-testid="main-nav">
          <NavLink to="/" end data-testid="nav-terminal"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            TERMINAL
          </NavLink>
          <NavLink to="/portfolio" data-testid="nav-portfolio"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            PORTFOLIO
          </NavLink>
          <NavLink to="/execution" data-testid="nav-execution"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            EXECUTION
          </NavLink>
          <NavLink to="/approval" data-testid="nav-approval"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            APPROVAL
          </NavLink>
          <NavLink to="/venues" data-testid="nav-venues"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            VENUES
          </NavLink>
          <NavLink to="/console" data-testid="nav-console"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            CONSOLE
          </NavLink>
          <NavLink to="/docs" data-testid="nav-docs"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            ARCHITECTURE
          </NavLink>
          <NavLink to="/settings" data-testid="nav-settings"
                   className={({ isActive }) => `term-nav-link ${isActive ? "active" : ""}`}>
            SETTINGS
          </NavLink>
          <span className="font-mono text-[10px] text-[#6b7888] px-2" data-testid="header-username">
            ◉ {user.username}
          </span>
          <button data-testid="header-logout-btn" onClick={logout}
                  className="font-mono text-[10px] font-bold tracking-wider px-2.5 py-1 border border-[#1f2a36] text-[#6b7888] hover:text-[#f87171] hover:border-[#f87171]/50 transition-colors">
            LOGOUT
          </button>
        </nav>
      )}
    </header>
  );
};

const ProtectedRoute = ({ children }) => {
  const { user } = useAuth();
  if (user === null) {
    return <div className="p-10 font-mono text-sm text-[#6b7888]" data-testid="auth-checking">authenticating…</div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
};

function App() {
  return (
    <div className="terminal">
      <BrowserRouter>
        <AuthProvider>
          <Header />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/portfolio" element={<ProtectedRoute><Portfolio /></ProtectedRoute>} />
            <Route path="/execution" element={<ProtectedRoute><Execution /></ProtectedRoute>} />
            <Route path="/approval" element={<ProtectedRoute><ApprovalConsole /></ProtectedRoute>} />
            <Route path="/venues" element={<ProtectedRoute><VenueMonitor /></ProtectedRoute>} />
            <Route path="/console" element={<ProtectedRoute><OperatorConsole /></ProtectedRoute>} />
            <Route path="/docs" element={<ProtectedRoute><DocsViewer /></ProtectedRoute>} />
            <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
      <Toaster position="bottom-right" theme="dark" toastOptions={{
        style: { background: "#10161e", border: "1px solid #1f2a36", color: "#c9d4e0", borderRadius: 0, fontFamily: "IBM Plex Mono, monospace", fontSize: 12 },
      }} />
    </div>
  );
}

export default App;
