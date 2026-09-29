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
  SESSION_LOST_EVENT,
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
  const sessionLostRef = useRef(false);
  const inFlightRef = useRef<Promise<SanitizedUser | null> | null>(null);
  const mountedRef = useRef(true);

  const applyUser = useCallback((userData: SanitizedUser) => {
    sessionLostRef.current = false;
    setUser(userData);
    setIsBanned(false);
    setBanReason("");
    writeStoredUser(userData);
    if (userData.language) {
      syncLangFromDb(userData.language);
    }
    return userData;
  }, []);

  // Автовыход: proxy вернул 401 (сессия истекла или была отозвана).
  const dropSession = useCallback(
    (banned = false, reason = "") => {
      clearStoredUser();
      setUser(null);
      if (banned) {
        setIsBanned(true);
        setBanReason(reason);
      }
      if (sessionLostRef.current) return;
      sessionLostRef.current = true;
      router.replace(`/login?reason=${banned ? "banned" : "session_expired"}`);
    },
    [router],
  );

  const loadUser = useCallback((): Promise<SanitizedUser | null> => {
    if (inFlightRef.current) return inFlightRef.current;

    const request = (async (): Promise<SanitizedUser | null> => {
      try {
        const userData = await getMe();
        if (!mountedRef.current) return userData;
        applyUser(userData);
        return userData;
      } catch (error) {
        if (!mountedRef.current) return null;
        if (error instanceof ApiError && error.authExpired) {
          // Прокси ставит auth_expired только когда cookie была,
          // а апстрим ответил 401: сессия действительно потеряна.
          dropSession();
          return null;
        }
        if (error instanceof ApiError && error.status === 401) {
          // Голый 401 без auth_expired - cookie не было вовсе.
          // Это обычный ответ гостя, автовыход здесь не нужен.
          return null;
        }
        if (error instanceof ApiError && error.status === 403) {
          dropSession(true, error.message);
          return null;
        }
        // Сеть недоступна - не выкидываем пользователя, оставляем кэш.
        return readStoredUser<SanitizedUser>();
      } finally {
        inFlightRef.current = null;
      }
    })();

    inFlightRef.current = request;
    return request;
  }, [applyUser, dropSession]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // После server-side логина router.refresh() приносит новый initialUser.
  // Без синхронизации состояние оставалось null и /profile вечно показывал
  // «Загрузка» до ручного F5.
  // Синхронизация выполняется в render-фазе (документированный паттерн React
  // «Adjusting state when a prop changes»), а не через setState в эффекте:
  // это не даёт каскадных ререндеров и не нарушает правила линтера.
  const initialUserSignature = initialUser ? JSON.stringify(initialUser) : "";
  const [syncedSignature, setSyncedSignature] = useState(initialUserSignature);
  if (initialUserSignature && initialUserSignature !== syncedSignature) {
    setSyncedSignature(initialUserSignature);
    setIsBanned(false);
    setBanReason("");
    setUser(initialUser);
    setLoading(false);
  }

  // localStorage, язык и флаг потери сессии - внешние системы,
  // их синхронизируем в эффекте, а не в render-фазе.
  useEffect(() => {
    if (!initialUser) return;
    sessionLostRef.current = false;
    writeStoredUser(initialUser);
    if (initialUser.language) syncLangFromDb(initialUser.language);
  }, [initialUser]);

  useEffect(() => {
    const onSessionLost = () => dropSession();
    window.addEventListener(SESSION_LOST_EVENT, onSessionLost);
    return () => window.removeEventListener(SESSION_LOST_EVENT, onSessionLost);
  }, [dropSession]);

  useEffect(() => {
    if (initialUser) {
      // loading уже инициализирован как false, когда initialUser пришёл с сервера.
      return;
    }
    // Кэш из localStorage нужен только до ответа сервера, поэтому он
    // обновляется в асинхронном колбэке, а не синхронно в теле эффекта.
    const cached = readStoredUser<SanitizedUser>();
    if (cached) {
      queueMicrotask(() => {
        if (mountedRef.current) {
          setUser(cached);
          setLoading(false);
        }
      });
    }
    let cancelled = false;
    loadUser().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Сессия истекла на сервере - proxy сам сообщит через 401.
  // Дополнительно синхронизируемся раз в минуту, чтобы поймать
  // отозванную сессию даже без активных запросов.
  useEffect(() => {
    if (initialUser) return;
    const interval = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      void loadUser();
    }, TOKEN_REFRESH_INTERVAL);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void loadUser();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loadUser, initialUser]);

  const login = useCallback(async (): Promise<SanitizedUser | null> => {
    setLoading(true);
    const result = await loadUser();
    setLoading(false);
    return result;
  }, [loadUser]);

  const logout = useCallback(async () => {
    clearStoredUser();
    setUser(null);
    sessionLostRef.current = false;
    await logoutUser();
    router.replace("/");
  }, [router]);

  const refreshUser = useCallback(async (): Promise<SanitizedUser | null> => {
    return loadUser();
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
