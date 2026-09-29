"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { getFeatures } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { FeaturesResponse } from "@/lib/types";

interface FeaturesContextType {
  features: FeaturesResponse | null;
  loading: boolean;
  error: string | null;
}

const FeaturesContext = createContext<FeaturesContextType | undefined>(
  undefined,
);

export function FeaturesProvider({
  children,
  initialFeatures = null,
}: {
  children: ReactNode;
  initialFeatures?: FeaturesResponse | null;
}) {
  const [features, setFeatures] = useState<FeaturesResponse | null>(
    initialFeatures,
  );
  const [loading, setLoading] = useState(initialFeatures === null);
  const [error, setError] = useState<string | null>(null);

  // Синхронизация нового server-provided features - в render-фазе
  // (паттерн React "Adjusting state when a prop changes"), а не setState
  // в эффекте: это не вызывает каскадных ререндеров.
  const initialSignature = initialFeatures
    ? JSON.stringify(initialFeatures)
    : "";
  const [syncedSignature, setSyncedSignature] = useState(initialSignature);
  if (initialSignature && initialSignature !== syncedSignature) {
    setSyncedSignature(initialSignature);
    setFeatures(initialFeatures);
    setLoading(false);
  }

  // Сервер уже получил features в layout - повторный клиентский запрос
  // /config/features был дублирующим обращением к боту на каждой странице.
  // Клиентский запрос остаётся только как fallback, если серверный не удался.
  useEffect(() => {
    if (initialFeatures) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getFeatures();
        if (!cancelled) setFeatures(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : t("texts.failed_to_load_features"),
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initialFeatures]);

  return (
    <FeaturesContext.Provider value={{ features, loading, error }}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures() {
  const context = useContext(FeaturesContext);
  if (!context) {
    throw new Error("useFeatures must be used within FeaturesProvider");
  }
  return context;
}
