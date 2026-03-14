import React, { createContext, useCallback, useEffect, useState } from 'react';
import { getMe, setStoredToken, clearStoredToken, getStoredToken, type User } from '../api/client';

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = useState<User | null>(null);
  const [token, setTokenState] = useState<string | null>(() => getStoredToken());
  const [loading, setLoading] = useState(true);

  const setUser = useCallback((u: User | null) => {
    setUserState(u);
  }, []);

  const setToken = useCallback((t: string | null) => {
    setTokenState(t);
    if (t) setStoredToken(t);
    else clearStoredToken();
  }, []);

  const logout = useCallback(() => {
    setUserState(null);
    setTokenState(null);
    clearStoredToken();
  }, []);

  useEffect(() => {
    const t = getStoredToken();
    if (!t) {
      setLoading(false);
      return;
    }
    getMe()
      .then((u) => {
        setUserState(u);
        setTokenState(t);
      })
      .catch(() => {
        clearStoredToken();
        setTokenState(null);
        setUserState(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const value: AuthContextValue = {
    user,
    token,
    loading,
    setUser,
    setToken,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
