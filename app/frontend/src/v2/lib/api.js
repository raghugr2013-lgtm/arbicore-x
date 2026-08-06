/**
 * ArbiCore X — UI v2 · Thin API client (Slice 0)
 *
 * Wraps axios for the /v2 sub-app so v2 code never touches the legacy axios
 * defaults directly. All calls go to REACT_APP_BACKEND_URL + /api/… so the
 * build-time env-var guarantee (docs/releases/v1.0.2.md) is preserved.
 *
 * Endpoints wired at Slice 0:
 *   - GET /api/system/status                (feature flag + heartbeat)
 *   - GET /api/arbicore/dashboard/pulse
 *   - GET /api/arbicore/dashboard/deck
 *   - GET /api/arbicore/opportunities/summary
 *   - GET /api/arbicore/roi-probability
 */
import axios from "axios";

const BASE = process.env.REACT_APP_BACKEND_URL;
const API = `${BASE}/api`;

// v2 endpoints authenticate via Authorization headers, not cookies.  Keep
// withCredentials off so cross-origin fetches (e.g. when the app is served
// via one ingress URL and the API responds via another) do not trigger the
// stricter credentialed-CORS check that wildcard "*" cannot satisfy.
const client = axios.create({ withCredentials: false });

async function get(path, params) {
  const res = await client.get(`${API}${path}`, { params });
  return res.data;
}

export const v2Api = {
  systemStatus: () => get("/system/status"),
  pulse: () => get("/arbicore/dashboard/pulse"),
  deck: (limit = 5) => get("/arbicore/dashboard/deck", { limit }),
  opportunitiesSummary: (windowHours = 24) =>
    get("/arbicore/opportunities/summary", { window_hours: windowHours }),
  // v2.11.9 — Shadow Certification (auth via legacy session cookie; the pulse
  // endpoint already surfaces a compact snapshot, but these detailed views
  // are used by the certification card action link).
  shadowCertCurrent: () => get("/arbicore/certification/shadow/current"),
  shadowCertRuns: (limit = 20) =>
    get("/arbicore/certification/shadow/runs", { limit }),
  shadowCertRun: (runId) =>
    get(`/arbicore/certification/shadow/runs/${runId}`),
  shadowCertReadiness: () =>
    get("/arbicore/certification/shadow/readiness"),
  opportunitiesList: (filters = {}) =>
    get("/arbicore/opportunities", filters),
  opportunityDetail: (id) => get(`/arbicore/opportunities/${id}`),
  opportunityTimeline: (id) => get(`/arbicore/opportunities/${id}/timeline`),
  approveOpportunity: (id) => client.post(`${API}/arbicore/opportunities/${id}/approve`).then((r) => r.data),
  rejectOpportunity: (id) => client.post(`${API}/arbicore/opportunities/${id}/reject`).then((r) => r.data),
  roiProbability: (routeId) =>
    get("/arbicore/roi-probability", { route_id: routeId }),
  // Slice 2 — Discovery + Intelligence
  discoveryCandidates: (filters = {}) =>
    get("/arbicore/discovery/candidates", filters),
  discoveryAction: (id, action) =>
    client.post(`${API}/arbicore/discovery/candidates/${id}/action`, null, { params: { action } }).then((r) => r.data),
  recommendations: () => get("/arbicore/intelligence/recommendations"),
  decisions: (filters = {}) => get("/arbicore/intelligence/decisions", filters),
  // Wave-1 activations — dormant learning-loop engines exposed for future
  // Intelligence sub-tabs. No UI consumer yet (deliberate, per Wave-1 rules).
  calibration: (params = {}) => get("/arbicore/intelligence/calibration", params),
  models: () => get("/arbicore/intelligence/models"),
  // Wave-2 exposures (file-verified canonical engines)
  certification: () => get("/arbicore/intelligence/certification"),
  entities: (params = {}) => get("/arbicore/intelligence/entities", params),
  // Slice 3 — Operations
  scanners: () => get("/arbicore/operations/scanners"),
  scannerAction: (family, action) =>
    client.post(`${API}/arbicore/operations/scanners/${family}/action`, null, { params: { action } }).then((r) => r.data),
  cycles: (filters = {}) => get("/arbicore/operations/cycles", filters),
  venues: () => get("/arbicore/operations/venues"),
  interlock: () => get("/arbicore/operations/interlock"),
  interlockAction: (action) =>
    client.post(`${API}/arbicore/operations/interlock/action`, null, { params: { action } }).then((r) => r.data),
  integrations: () => get("/arbicore/operations/integrations"),
  queues: () => get("/arbicore/operations/queues"),
  alerts: (filters = {}) => get("/arbicore/operations/alerts", filters),
  alertAck: (id) => client.post(`${API}/arbicore/operations/alerts/${id}/ack`).then((r) => r.data),
  // Slice 4 — Portfolio
  positions: (filters = {}) => get("/arbicore/portfolio/positions", filters),
  balances: (filters = {}) => get("/arbicore/portfolio/balances", filters),
  transfers: (filters = {}) => get("/arbicore/portfolio/transfers", filters),
  deployable: () => get("/arbicore/portfolio/deployable"),
  treasury: () => get("/arbicore/portfolio/treasury"),
  ledger: (filters = {}) => get("/arbicore/portfolio/ledger", filters),
  exposure: () => get("/arbicore/portfolio/exposure"),
  allocation: () => get("/arbicore/portfolio/allocation"),
  // Slice 5 — Settings
  accountGet: () => get("/arbicore/settings/account"),
  accountPatch: (patch) => client.patch(`${API}/arbicore/settings/account`, patch).then((r) => r.data),
  vaultsGet: () => get("/arbicore/settings/vaults"),
  vaultReconcile: (v) => client.post(`${API}/arbicore/settings/vaults/${v}/reconcile`).then((r) => r.data),
  executionGet: () => get("/arbicore/settings/execution"),
  executionPatch: (patch) => client.patch(`${API}/arbicore/settings/execution`, patch).then((r) => r.data),
  exchangesGet: () => get("/arbicore/settings/exchanges"),
  exchangeTest: (key) => client.post(`${API}/arbicore/settings/exchanges/${key}/test`).then((r) => r.data),
  notificationsGet: () => get("/arbicore/settings/notifications"),
  notificationsPatch: (patch) => client.patch(`${API}/arbicore/settings/notifications`, patch).then((r) => r.data),
  documentationGet: () => get("/arbicore/settings/documentation"),
  operationalGet: () => get("/arbicore/settings/operational"),
  operationalPatch: (patch) => client.patch(`${API}/arbicore/settings/operational`, patch).then((r) => r.data),
  // Phase 10.1 — Network configuration
  networkGet: () => get("/arbicore/settings/network"),
  networkValidate: (patch) => client.post(`${API}/arbicore/settings/network/validate`, patch).then((r) => r.data),
  networkDraft: (patch) => client.post(`${API}/arbicore/settings/network/draft`, patch).then((r) => r.data),
  networkApply: (body) => client.post(`${API}/arbicore/settings/network/apply`, body).then((r) => r.data),
  networkRollback: (body) => client.post(`${API}/arbicore/settings/network/rollback`, body).then((r) => r.data),
  networkHistory: (limit = 50) => get("/arbicore/settings/network/history", { limit }),
  // Phase 10.3 — Telegram
  telegramGet: () => get("/arbicore/settings/telegram"),
  telegramPut: (body) => client.put(`${API}/arbicore/settings/telegram`, body).then((r) => r.data),
  telegramTest: () => client.post(`${API}/arbicore/settings/telegram/test`).then((r) => r.data),
  telegramLog: (limit = 50) => get("/arbicore/settings/telegram/log", { limit }),
  // Phase 10.4 — Scanner configuration (multi-family)
  scannerGet: () => get("/arbicore/settings/scanner"),
  scannerGlobalValidate: (patch) => client.post(`${API}/arbicore/settings/scanner/global/validate`, patch).then((r) => r.data),
  scannerGlobalDraft: (patch) => client.post(`${API}/arbicore/settings/scanner/global/draft`, patch).then((r) => r.data),
  scannerGlobalApply: (body) => client.post(`${API}/arbicore/settings/scanner/global/apply`, body).then((r) => r.data),
  scannerGlobalRollback: (body) => client.post(`${API}/arbicore/settings/scanner/global/rollback`, body).then((r) => r.data),
  scannerFamilyGet: (fid) => get(`/arbicore/settings/scanner/family/${fid}`),
  scannerFamilyValidate: (fid, patch) => client.post(`${API}/arbicore/settings/scanner/family/${fid}/validate`, patch).then((r) => r.data),
  scannerFamilyDraft: (fid, patch) => client.post(`${API}/arbicore/settings/scanner/family/${fid}/draft`, patch).then((r) => r.data),
  scannerFamilyApply: (fid, body) => client.post(`${API}/arbicore/settings/scanner/family/${fid}/apply`, body).then((r) => r.data),
  scannerFamilyRollback: (fid, body) => client.post(`${API}/arbicore/settings/scanner/family/${fid}/rollback`, body).then((r) => r.data),
  scannerFamilyHistory: (fid, limit = 50) => get(`/arbicore/settings/scanner/family/${fid}/history`, { limit }),
  scannerPause: (reason = "") => client.post(`${API}/arbicore/settings/scanner/pause`, { reason }).then((r) => r.data),
  scannerResume: (reason = "") => client.post(`${API}/arbicore/settings/scanner/resume`, { reason }).then((r) => r.data),
  scannerReload: (reason = "") => client.post(`${API}/arbicore/settings/scanner/reload`, { reason }).then((r) => r.data),
  // Phase 10.5 — Secrets management
  secretsList: () => get("/arbicore/execution/secrets"),
  secretsStatus: () => get("/arbicore/execution/secrets/status"),
  secretsPut: (body) => client.post(`${API}/arbicore/execution/secrets`, body).then((r) => r.data),
  secretsDelete: (handleId) => client.delete(`${API}/arbicore/execution/secrets/${handleId}`).then((r) => r.data),
  secretsRotate: (handleId, plaintext) => client.post(`${API}/arbicore/execution/secrets/${handleId}/rotate`, { plaintext }).then((r) => r.data),
  secretsTest: (handleId) => client.post(`${API}/arbicore/execution/secrets/${handleId}/test`).then((r) => r.data),
  // Phase 10.6 — Flash Loan prereqs
  flashLoanPrereqs: () => get("/arbicore/wizard/flash-loan-prereqs"),
  // Phase 10.2 — audit
  configHistory: (kind, limit = 100) => get("/arbicore/settings/config/history", { kind, limit }),
};
