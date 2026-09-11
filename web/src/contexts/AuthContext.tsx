'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import type { SanitizedUser } from '@/lib/types';
import { getMe, logoutUser, clearStoredToken } from '@/lib/api';
import { syncLangFromDb, t } from '@/lib/i18n';

interface AuthContextType {
  user: SanitizedUser | null;
  setUser: React.Dispatch<React.SetStateAction<SanitizedUser | null>>;
  loading: boolean;
  isBanned: boolean;
  banReason: string;
  login: () => Promise<SanitizedUser | null>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<SanitizedUser | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const USER_KEY = 'vpn_user';
const TOKEN_REFRESH_INTERVAL = 5 * 60_000;

function clearStoredUser() {
  try {
    localStorage.removeItem(USER_KEY);
  } catch {
    // ignore
  }
}

async function clearAuthSession() {
  try {
    const { logoutUser } = await import('@/lib/api');
    await logoutUser().catch(() => {});
  } catch {
    // ignore
  }
  clearStoredUser();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<SanitizedUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [isBanned, setIsBanned] = useState(false);
  const [banReason, setBanReason] = useState('');

  const loadUser = useCallback(async (): Promise<SanitizedUser | null> => {
    try {
      const userData = await getMe();
      setUser(userData);
      try {
        localStorage.setItem(USER_KEY, JSON.stringify(userData));
      } catch {
        // ignore
      }
      if (userData.language) {
        syncLangFromDb(userData.language);
      }
      setIsBanned(false);
      setBanReason('');
      return userData;
    } catch (error) {
      const message = error instanceof Error ? error.message : '';
      const isBannedError = message.toLowerCase().includes('account banned');
      const isAuthError =
        message.toLowerCase().includes('unauthorized') ||
        message.toLowerCase().includes('invalid session') ||
        message.toLowerCase().includes('invalid_session') ||
        message.includes('401') ||
        message.includes('403');
      if (isBannedError || (isAuthError && message.includes('403'))) {
        setIsBanned(true);
        setBanReason(message);
        clearStoredUser();
        clearStoredToken();
        setUser(null);
        router.replace('/banned');
      } else if (isAuthError) {
        clearStoredUser();
        clearStoredToken();
        setUser(null);
      }
      return null;
    }
  }, [router]);

  useEffect(() => {
    const init = async () => {
      let cached: SanitizedUser | null = null;
      try {
        const stored = localStorage.getItem(USER_KEY);
        if (stored) {
          cached = JSON.parse(stored) as SanitizedUser;
          setUser(cached);
        }
      } catch {
        // ignore
      }
      await loadUser();
      setLoading(false);
    };
    init();
  }, [loadUser]);

  const login = useCallback(async (): Promise<SanitizedUser | null> => {
    return loadUser();
  }, [loadUser]);

  const logout = useCallback(async () => {
    await clearAuthSession();
    setUser(null);
    try {
      router.replace('/');
    } catch {
      // ignore
    }
  }, [router]);

  useEffect(() => {
    let cancelled = false;

    const interval = setInterval(async () => {
      if (cancelled) return;
      try {
        const userData = await getMe();
        if (userData && !cancelled) {
          setUser(userData);
          try {
            localStorage.setItem(USER_KEY, JSON.stringify(userData));
          } catch {
            // ignore
          }
          if (userData.language) {
            syncLangFromDb(userData.language);
          }
        }
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : '';
        if (
          message.toLowerCase().includes('unauthorized') ||
          message.toLowerCase().includes('invalid session')
        ) {
          clearStoredUser();
          setUser(null);
        }
      }
    }, TOKEN_REFRESH_INTERVAL);

    const onVisibility = async () => {
      if (document.visibilityState !== 'visible') return;
      try {
        const userData = await getMe();
        if (userData && !cancelled) {
          setUser(userData);
          try {
            localStorage.setItem(USER_KEY, JSON.stringify(userData));
          } catch {
            // ignore
          }
          if (userData.language) {
            syncLangFromDb(userData.language);
          }
        }
      } catch {
        // ignore
      }
    };

    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  const refreshUser = useCallback(async (): Promise<SanitizedUser | null> => {
    const userData = await loadUser();
    if (!userData) {
      throw new Error(t('texts.failed_to_load_user'));
    }
    return userData;
  }, [loadUser]);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, isBanned, banReason, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
