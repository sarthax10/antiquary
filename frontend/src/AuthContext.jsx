import { createContext, useCallback, useContext, useEffect, useState } from "react";
import * as authApi from "./api/auth";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Distinguishes "not signed in" from "couldn't reach the API at all" — previously a
  // failed /me request left the app on a blank screen forever.
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    authApi
      .getCurrentUser()
      .then((u) => setUser(u))
      .catch((err) => {
        setUser(null);
        setError(err);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const login = async (email, password) => {
    const u = await authApi.login(email, password);
    setUser(u);
    return u;
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      // Even if the session had already expired server-side (401), the user asked to
      // leave — never strand them on a page that thinks they're signed in.
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, retry: load, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
