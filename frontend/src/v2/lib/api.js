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

// Reuse the legacy axios instance so the /auth/refresh interceptor keeps
// working across the app boundary.
const client = axios.create({ withCredentials: true });

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
  opportunitiesList: (filters = {}) =>
    get("/arbicore/opportunities", filters),
  opportunityDetail: (id) => get(`/arbicore/opportunities/${id}`),
  approveOpportunity: (id) => client.post(`${API}/arbicore/opportunities/${id}/approve`).then((r) => r.data),
  rejectOpportunity: (id) => client.post(`${API}/arbicore/opportunities/${id}/reject`).then((r) => r.data),
  roiProbability: (routeId) =>
    get("/arbicore/roi-probability", { route_id: routeId }),
};
