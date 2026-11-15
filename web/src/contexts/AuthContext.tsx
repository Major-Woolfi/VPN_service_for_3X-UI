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
import {
  ApiError,
  SESSION_HOST_EVENT,
  clearStoredUser,
  getMe,
  logoutUser,
  readStoredUser,
  writeStoredUser,
} from "@/lib/api";
import { syncLangFromDb } from "@/lib/i18n";

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

const TOKEN_REFRESH_INTERVAL = 60_000;

export function AuthProvider({
  children,
  initialUser = null,
}: {
  children: ReactNode;
  initialUser?: SanitizedUser | null;
}) {
  const router = useRouter();
  const [user, setUser] = useState<SanitizedUser | null>(initialUser);
  const [loading, setLoading] = useState(initialUser === null);
  const [isBanned, setIsBanned] = useState(false);
  const [banReason, setBanReason] = useState("");
  const sessionHostRef = useRef(false);
  const inFlightRef = useRef<Promise<SanitizedUser | null> | null>(null);
  const mountedRef = useRef(true);

  const applyUser = useCallback((userData: SanitizedUser) => {
    sessionHostRef.current = false;
    setUser(userData);
    setIsBanned(false);
    setBanReason("");
    writeStoredUser(userData);
    if (userData.language) {
      syncLangFromDb(userData.language);
    }
    return userData;
  }, []);

  const dropSession = useCallback(
    (banned = false, reason = "") => {
      clearStoredUser();
      setUser(null);
      if (banned) {
        setIsBanned(true);
        setBanReason(reason);
      }
      if (sessionHostRef.current) return;
      sessionHostRef.current = true;
      router.replace(`/login?reason=${banned ? "banned" : "session_expired"}`);
    },
    [router],
  );

  const login = useCallback(async (): Promise<SanitizedUser | null> => {
    return null;
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    await logoutUser();
    clearStoredUser();
    setUser(null);
    router.replace("/login");
  }, [router]);

  const refreshUser = useCallback(async (): Promise<SanitizedUser | null> => {
    const userData = await getMe();
    applyUser(userData);
    return userData;
  }, [getMe, applyUser]);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, isBanned, banReason, login, logout, refreshUser }}>
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
