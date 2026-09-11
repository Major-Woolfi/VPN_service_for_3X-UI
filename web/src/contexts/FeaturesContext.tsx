'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { getFeatures } from '@/lib/api';
import { t } from '@/lib/i18n';
import type { FeaturesResponse } from '@/lib/types';

interface FeaturesContextType {
  features: FeaturesResponse | null;
  loading: boolean;
  error: string | null;
}

const FeaturesContext = createContext<FeaturesContextType | undefined>(undefined);

export function FeaturesProvider({ children }: { children: ReactNode }) {
  const [features, setFeatures] = useState<FeaturesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await getFeatures();
        setFeatures(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('texts.failed_to_load_features'));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <FeaturesContext.Provider value={{ features, loading, error }}>
      {children}
    </FeaturesContext.Provider>
  );
}

export function useFeatures() {
  const context = useContext(FeaturesContext);
  if (!context) {
    throw new Error('useFeatures must be used within FeaturesProvider');
  }
  return context;
}

