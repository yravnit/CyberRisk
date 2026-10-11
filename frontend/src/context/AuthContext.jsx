import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getMe, loginUser, registerUser } from '../api/client';

const TOKEN_KEY = 'cyberrisk_token';
const AuthContext = createContext(null);

const readToken = () => localStorage.getItem(TOKEN_KEY);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(readToken);
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const persist = (nextToken, nextUser) => {
    setToken(nextToken);
    setUser(nextUser || null);
    if (nextToken) localStorage.setItem(TOKEN_KEY, nextToken);
    else localStorage.removeItem(TOKEN_KEY);
  };

  // Validate a stored token on load so a stale token doesn't send the user
  // into the dashboard only to be bounced by a 401 on the first panel.
  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    getMe()
      .then((u) => { if (!cancelled) setUser(u); })
      .catch(() => { if (!cancelled) persist(null, null); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const login = useCallback(async (username, password) => {
    const res = await loginUser(username, password);
    persist(res.token, res.user);
    return res.user;
  }, []);

  const register = useCallback(async (username, password) => {
    const res = await registerUser(username, password);
    persist(res.token, res.user);
    return res.user;
  }, []);

  const logout = useCallback(() => persist(null, null), []);

  return (
    <AuthContext.Provider value={{ token, user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
