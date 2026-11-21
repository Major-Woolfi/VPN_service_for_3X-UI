"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
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
  reload: () => void;
}

const FeaturesContext = createContext<FeaturesContextType | undefined>(undefined);

export function FeaturesProvider({
  children,
  initialFeatures = null,
}: {
  children: ReactNode;
  initialFeatures?: FeaturesResponse | null;
}) {
  const [features, setFeatures] = useState<FeaturesResponse | null>(initialFeatures);
  const [loading, setLoading] = useState(initialFeatures === null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!initialFeatures) return;
    setFeatures(initialFeatures);
    setLoading(false);
    setError(null);
  }, [initialFeatures]);

  useEffect(() => {
    if (initialFeatures && reloadKey === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getFeatures();
        if (!cancelled) {
          setFeatures(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            typeof err === "object" && err !== null && "message" in err
              ? (err as { message: string }).message
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
  }, [initialFeatures, reloadKey]);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setReloadKey((value) => value + 1);
  }, []);

  const value = useMemo(
    () => ({ features, loading, error, reload }),
    [features, loading, error, reload],
  );

  return <FeaturesContext.Provider value={value}>{children}</FeaturesContext.Provider>;
}

export function useFeatures() {
  const context = useContext(FeaturesContext);
  if (!context) {
    throw new Error("useFeatures must be used within FeaturesProvider");
  }
  return context;
}
