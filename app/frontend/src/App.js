import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { AppShell as DashboardShell } from "@/v2/components/AppShell";
import LoginPage from "@/v2/pages/LoginPage";
import InitializationPage from "@/v2/pages/InitializationPage";

/**
 * Production entry flow (v2.0.1):
 *   /                    → routes based on auth+init state
 *   /login               → Login form (unauthenticated only)
 *   /initialization      → Loading experience (authenticated, uninitialized)
 *   /dashboard/*         → ArbiCore X home (authenticated + initialized)
 *   /v2/*                → legacy alias — redirects to /dashboard
 *   *                    → routed based on auth state
 *
 * The AppShell (formerly rooted at /v2) is remounted at /dashboard as the
 * primary entry point of the platform.  /v2 remains as a backward-compat
 * redirect only; it is no longer exposed in the primary navigation.
 */

function RootRedirect() {
  const { isAuthenticated, isInitialized } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isInitialized) return <Navigate to="/initialization" replace />;
  return <Navigate to="/dashboard" replace />;
}

function ProtectedDashboard() {
  const { isAuthenticated, isInitialized } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (!isInitialized) return <Navigate to="/initialization" replace />;
  return <DashboardShell />;
}

function LegacyV2Redirect() {
  // Preserve deep-link semantics from the old /v2/* paths.
  const path = window.location.pathname.replace(/^\/v2/, "/dashboard");
  const suffix = path === "/dashboard" ? "" : path.slice("/dashboard".length);
  return <Navigate to={`/dashboard${suffix}${window.location.search}`} replace />;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/initialization" element={<InitializationPage />} />
          <Route path="/dashboard/*" element={<ProtectedDashboard />} />
          <Route path="/v2" element={<LegacyV2Redirect />} />
          <Route path="/v2/*" element={<LegacyV2Redirect />} />
          <Route path="/" element={<RootRedirect />} />
          <Route path="*" element={<RootRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
