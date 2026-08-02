import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, Link } from "react-router-dom";
import axios from "axios";
import { AuthProvider } from "@/context/AuthContext";
import { AppShell as UiV2AppShell } from "@/v2/components/AppShell";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LegacyLanding = () => {
  useEffect(() => {
    axios.get(`${API}/`).catch(() => {});
  }, []);
  return (
    <div style={{ padding: 40, fontFamily: "system-ui, sans-serif", color: "#c9d4e0", background: "#0b0f14", minHeight: "100vh" }}>
      <h1 style={{ fontSize: 20, marginBottom: 8 }}>ArbiCore X — Preview Pod</h1>
      <p style={{ color: "#8a97a8", marginBottom: 16 }}>Legacy UI is a stub in this preview environment. Open the Slice 0 shell:</p>
      <Link to="/v2" style={{ color: "#ffb224", textDecoration: "none", fontFamily: "monospace" }}>→ /v2 (UI v2 Slice 0 shell)</Link>
    </div>
  );
};

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/v2/*" element={<UiV2AppShell />} />
          <Route path="/" element={<LegacyLanding />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
