import axios from "axios";
import { createContext, useContext, useEffect, useState } from "react";

axios.defaults.withCredentials = true;
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function formatApiErrorDetail(detail) {
  if (detail == null) return "Something went wrong. Please try again.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

let refreshPromise = null;
axios.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { config, response } = error;
    if (response?.status === 401 && config && !config._retried && !String(config.url).includes("/auth/")) {
      config._retried = true;
      try {
        refreshPromise = refreshPromise || axios.post(`${API}/auth/refresh`);
        await refreshPromise;
        refreshPromise = null;
        return axios(config);
      } catch (e) {
        refreshPromise = null;
        window.dispatchEvent(new Event("arbicore:unauthed"));
      }
    }
    return Promise.reject(error);
  }
);

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null=checking, false=anon, object=authed
  const [setupComplete, setSetupComplete] = useState(null);

  useEffect(() => {
    axios.get(`${API}/auth/status`).then(({ data }) => setSetupComplete(data.setup_complete)).catch(() => setSetupComplete(true));
    axios.get(`${API}/auth/me`).then(({ data }) => setUser(data)).catch(() => setUser(false));
    const onUnauthed = () => setUser(false);
    window.addEventListener("arbicore:unauthed", onUnauthed);
    return () => window.removeEventListener("arbicore:unauthed", onUnauthed);
  }, []);

  const login = async (username, password) => {
    const { data } = await axios.post(`${API}/auth/login`, { username, password });
    setUser(data);
    return data;
  };

  const setup = async (username, password) => {
    const { data } = await axios.post(`${API}/auth/setup`, { username, password });
    setUser(data);
    setSetupComplete(true);
    return data;
  };

  const logout = async () => {
    try { await axios.post(`${API}/auth/logout`); } catch (e) { /* cookies cleared anyway */ }
    setUser(false);
  };

  const logoutAll = async () => {
    try { await axios.post(`${API}/auth/logout-all`); } catch (e) { /* session already dead */ }
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, setUser, setupComplete, login, setup, logout, logoutAll }}>
      {children}
    </AuthContext.Provider>
  );
};
