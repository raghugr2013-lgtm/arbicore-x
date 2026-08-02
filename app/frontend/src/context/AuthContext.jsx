/**
 * Preview-only AuthContext stub for the pod environment.
 * The canonical /v2 code imports useAuth from @/context/AuthContext; this
 * stub keeps the shell renderable without the full auth wiring.
 */
import { createContext, useContext } from "react";

const AuthContext = createContext({
  user: { username: "preview" },
  logout: () => {},
});

export const useAuth = () => useContext(AuthContext);
export const AuthProvider = ({ children }) => (
  <AuthContext.Provider value={{ user: { username: "preview" }, logout: () => {} }}>
    {children}
  </AuthContext.Provider>
);
