"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import type { SanitizedUser } from "@/lib/types";
import { getMe, clearStoredToken } from "@/lib/api";
import { syncLangFromDb, t } from "@/lib/i18n";

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

const USER_KEY = "vpn_user";
const TOKEN_REFRESH_INTERVAL = 5 * 60_000;

function clearStoredUser() {
  try {
    localStorage.removeItem(USER_KEY);
  } catch {
    // ignore
  }
}

function clearSessionCookie() {
  try {
    const cookies = document.cookie.split(";");
    for (const cookie of cookies) {
      const eqIdx = cookie.indexOf("=");
      const name =
        eqIdx > -1 ? cookie.substring(0, eqIdx).trim() : cookie.trim();
      if (name) {
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Lax`;
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Strict`;
        document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/`;
      }
    }
  } catch {
    // ignore
  }
}

async function clearAuthSession() {
  try {
    const { logoutUser } = await import("@/lib/api");
    await logoutUser().catch(() => {});
  } catch {
    // ignore
  }
  clearStoredUser();
  clearStoredToken();
  clearSessionCookie();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<SanitizedUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [isBanned, setIsBanned] = useState(false);
  const [banReason, setBanReason] = useState("");
  const authLostRef = useRef(false);
  const isPageVisible = useRef(true);
  const refreshInProgress = useRef(false);

  const redirectToLogin = useCallback(() => {
    if (authLostRef.current) return;
    authLostRef.current = true;
    try {
      sessionStorage.setItem("auth_lost", "1");
    } catch {
      // ignore
    }
    router.replace("/login");
  }, [router]);

  const loadUser = useCallback(async (): Promise<SanitizedUser | null> => {
    try {
      const userData = await getMe();
      authLostRef.current = false;
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
      setBanReason("");
      return userData;
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      const isBannedError = message.toLowerCase().includes("account banned");
      const isAuthError =
        message.toLowerCase().includes("unauthorized") ||
        message.toLowerCase().includes("invalid session") ||
        message.toLowerCase().includes("invalid_session") ||
        message.includes("401") ||
        message.includes("403");
      if (isBannedError || (isAuthError && message.includes("403"))) {
        setIsBanned(true);
        setBanReason(message);
        clearStoredUser();
        clearStoredToken();
        clearSessionCookie();
        setUser(null);
        redirectToLogin();
      } else if (isAuthError) {
        clearStoredUser();
        clearStoredToken();
        clearSessionCookie();
        setUser(null);
        redirectToLogin();
      }
      return null;
    }
  }, [redirectToLogin]);

  useEffect(() => {
    const init = async () => {
      try {
        const lost = sessionStorage.getItem("auth_lost");
        if (lost === "1") {
          sessionStorage.removeItem("auth_lost");
          redirectToLogin();
          setLoading(false);
          return;
        }
      } catch {
        // ignore
      }
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
  }, [loadUser, redirectToLogin]);

  const login = useCallback(async (): Promise<SanitizedUser | null> => {
    return loadUser();
  }, [loadUser]);

  const logout = useCallback(async () => {
    await clearAuthSession();
    setUser(null);
    try {
      router.replace("/");
    } catch {
      // ignore
    }
  }, [router]);

  useEffect(() => {
    let cancelled = false;

    const interval = setInterval(async () => {
      if (cancelled || !isPageVisible.current || refreshInProgress.current)
        return;
      refreshInProgress.current = true;
      try {
        const userData = await getMe();
        if (userData && !cancelled) {
          authLostRef.current = false;
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
        const message = error instanceof Error ? error.message : "";
        if (
          message.toLowerCase().includes("unauthorized") ||
          message.toLowerCase().includes("invalid session") ||
          message.includes("401")
        ) {
          clearStoredUser();
          clearStoredToken();
          clearSessionCookie();
          setUser(null);
          redirectToLogin();
        }
      } finally {
        if (!cancelled) {
          refreshInProgress.current = false;
        }
      }
    }, TOKEN_REFRESH_INTERVAL);

    const onVisibility = () => {
      isPageVisible.current = document.visibilityState === "visible";
      if (!isPageVisible.current) return;
      (async () => {
        if (refreshInProgress.current) return;
        refreshInProgress.current = true;
        try {
          const userData = await getMe();
          if (userData && !cancelled) {
            authLostRef.current = false;
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
        } finally {
          if (!cancelled) {
            refreshInProgress.current = false;
          }
        }
      })();
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [redirectToLogin]);

  const refreshUser = useCallback(async (): Promise<SanitizedUser | null> => {
    const userData = await loadUser();
    if (!userData) {
      throw new Error(t("texts.failed_to_load_user"));
    }
    return userData;
  }, [loadUser]);

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        loading,
        isBanned,
        banReason,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
