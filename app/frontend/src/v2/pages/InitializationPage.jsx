import { API_BASE } from "@/lib/apiBase";
/**
 * ArbiCore X — InitializationPage (production entry experience)
 *
 * Renders sequential backend synchronisation steps between login and
 * dashboard.  Each step hits a real backend endpoint and reports its own
 * outcome.  When all steps complete (or after graceful degradation), the
 * user is transitioned into /dashboard.
 */
import { useEffect, useMemo, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "@/context/AuthContext";
import "@/v2/theme/tokens.css";
import "@/v2/pages/InitializationPage.css";

const API = API_BASE;

const STEPS = [
  { key: "market",       label: "Connecting to Market…",              endpoint: "/" },
  { key: "intelligence", label: "Loading Intelligence…",               endpoint: "/system/status" },
  { key: "mid",          label: "Synchronizing Market Intelligence Database…", endpoint: "/arbicore/mid/status" },
  { key: "engine",       label: "Preparing Opportunity Engine…",       endpoint: "/arbicore/opportunities/summary" },
];

async function pingEndpoint(path) {
  try {
    const res = await axios.get(`${API}${path}`, { timeout: 10000, validateStatus: () => true });
    return { ok: res.status >= 200 && res.status < 500, status: res.status };
  } catch (err) {
    return { ok: false, status: 0, err: err?.message || "network error" };
  }
}

export default function InitializationPage() {
  const navigate = useNavigate();
  const { isAuthenticated, isInitialized, markInitialized } = useAuth();
  const [stepStates, setStepStates] = useState(() => STEPS.map(() => ({ state: "pending", detail: null })));
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState(null);

  const totalSteps = STEPS.length;
  const activeIndex = useMemo(() => {
    const idx = stepStates.findIndex((s) => s.state === "pending" || s.state === "running");
    return idx === -1 ? totalSteps : idx;
  }, [stepStates, totalSteps]);

  useEffect(() => {
    if (!isAuthenticated) return;

    let cancelled = false;

    async function run() {
      for (let i = 0; i < STEPS.length; i += 1) {
        if (cancelled) return;
        const step = STEPS[i];
        setStepStates((prev) => {
          const next = [...prev];
          next[i] = { state: "running", detail: null };
          return next;
        });

        // small delay so the animation reads as a real workflow, not a flash
        await new Promise((r) => setTimeout(r, 500));
        if (cancelled) return;

        const result = await pingEndpoint(step.endpoint);
        setStepStates((prev) => {
          const next = [...prev];
          next[i] = {
            state: result.ok ? "ok" : "warn",
            detail: result.ok ? `HTTP ${result.status}` : (result.err || `HTTP ${result.status}`),
          };
          return next;
        });

        // Small settle pause so operators see the tick land
        await new Promise((r) => setTimeout(r, 250));
      }

      if (!cancelled) {
        setComplete(true);
        markInitialized();
        // Transition after brief pause so the last checkmark registers
        setTimeout(() => {
          if (!cancelled) navigate("/dashboard", { replace: true });
        }, 700);
      }
    }

    run().catch((err) => {
      if (!cancelled) setError(err?.message || "initialization failed");
    });

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, markInitialized, navigate]);

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isInitialized) return <Navigate to="/dashboard" replace />;

  return (
    <div className="ui-v2-root arbicore-init" data-testid="initialization-page">
      <div className="arbicore-init__panel">
        <div className="arbicore-init__brand">
          <div className="arbicore-init__wordmark">ArbiCore X</div>
          <div className="arbicore-init__tag">Initializing platform intelligence</div>
        </div>

        <ul className="arbicore-init__steps" data-testid="initialization-steps">
          {STEPS.map((step, i) => {
            const s = stepStates[i];
            return (
              <li key={step.key} className={`arbicore-init__step arbicore-init__step--${s.state}`} data-testid={`initialization-step-${step.key}`}>
                <span className="arbicore-init__step-icon" aria-hidden="true">
                  {s.state === "pending" && <span className="arbicore-init__dot" />}
                  {s.state === "running" && <span className="arbicore-init__spinner" />}
                  {s.state === "ok"      && <span className="arbicore-init__check">✓</span>}
                  {s.state === "warn"    && <span className="arbicore-init__warn">!</span>}
                </span>
                <span className="arbicore-init__step-label">{step.label}</span>
                {s.detail && (
                  <span className="arbicore-init__step-detail" data-testid={`initialization-step-${step.key}-detail`}>
                    {s.detail}
                  </span>
                )}
              </li>
            );
          })}
        </ul>

        <div className="arbicore-init__progress">
          <div className="arbicore-init__progress-track">
            <div
              className="arbicore-init__progress-fill"
              style={{ width: `${Math.round(((complete ? totalSteps : activeIndex) / totalSteps) * 100)}%` }}
            />
          </div>
          <div className="arbicore-init__progress-label">
            {complete ? "Ready" : `${activeIndex}/${totalSteps}`}
          </div>
        </div>

        {error && (
          <div className="arbicore-init__error" role="alert">{error}</div>
        )}

        <div className="arbicore-init__footer">
          <span>v2.0.1</span>
          <span className="arbicore-init__footer-sep">·</span>
          <span>SHADOW mode</span>
        </div>
      </div>
    </div>
  );
}
