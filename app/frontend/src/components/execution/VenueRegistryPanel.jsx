import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROLE_STYLE = {
  primary: "#34d399", backup: "#38bdf8", watch: "#ffb224", disabled: "#6b7888",
};

export const VenueRegistryPanel = () => {
  const [venues, setVenues] = useState([]);
  const [roles, setRoles] = useState(["primary", "backup", "watch", "disabled"]);

  const load = useCallback(() => {
    axios.get(`${API}/execution/venues`).then((r) => {
      setVenues(r.data.venues || []);
      setRoles(r.data.roles || roles);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  const setRole = async (exchange, role) => {
    try {
      await axios.patch(`${API}/execution/venues/${exchange}`, { role });
      toast.success(`${exchange.toUpperCase()} → ${role.toUpperCase()}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Update failed");
    }
  };

  return (
    <div className="panel" data-testid="venue-registry-panel">
      <div className="panel-title">
        Venue Configuration Registry
        <span className="float-right text-[#3d4a59]">no hardcoded venues</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="panel-th">
              <th className="text-left">Venue</th>
              <th className="text-left">Role</th>
              <th className="text-right">Audit</th>
              <th className="text-left">Notes</th>
            </tr>
          </thead>
          <tbody>
            {venues.map((v) => (
              <tr key={v.exchange} className="border-b border-[#1f2a36]/50" data-testid={`venue-row-${v.exchange}`}>
                <td className="py-2 font-bold">{v.exchange.toUpperCase()}</td>
                <td className="py-2">
                  <select
                    data-testid={`venue-role-${v.exchange}`}
                    value={v.role}
                    onChange={(e) => setRole(v.exchange, e.target.value)}
                    className="term-input"
                    style={{ color: ROLE_STYLE[v.role] || "#c9d4e0" }}
                  >
                    {roles.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
                  </select>
                </td>
                <td className="py-2 text-right">{v.automation?.audit_score ?? "—"}</td>
                <td className="py-2 text-[9px] text-[#6b7888] max-w-[280px]">{v.automation?.notes || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="font-mono text-[9px] text-[#3d4a59] mt-2">
        PRIMARY = first execution target · BACKUP = fallback · WATCH = monitored only · DISABLED = excluded.
      </div>
    </div>
  );
};
