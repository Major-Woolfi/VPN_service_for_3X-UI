"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import type { SanitizedUser } from "@/lib/types";
import { clearStoredUser, getMe, logoutUser, writeStoredUser } from "@/lib/api";
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

export function AuthProvider({
  children,
  initialUser = null,
}: {
  children: ReactNode;
  initialUser?: SanitizedUser | null;
}) {
  const router = useRouter();
  const [user, setUser] = useState<SanitizedUser | null>(initialUser);
  const loading = false;
  const [isBanned, setIsBanned] = useState(false);
  const [banReason, setBanReason] = useState("");

  const applyUser = useCallback((userData: SanitizedUser) => {
    setUser(userData);
    setIsBanned(false);
    setBanReason("");
    writeStoredUser(userData);
    if (userData.language) {
      syncLangFromDb(userData.language);
    }
    return userData;
  }, []);

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
  }, [applyUser]);

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
