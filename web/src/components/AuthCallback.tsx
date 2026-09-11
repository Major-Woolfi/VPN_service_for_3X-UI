'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { pollTelegramAuth, TELEGRAM_POLL_TIMEOUT_MS } from '@/lib/api';

function hasAuthParams(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return !!(params.get('auth') || params.get('state'));
}

export default function AuthCallback() {
  const { t } = useLanguage();
  const [status, setStatus] = useState<'processing' | 'done' | 'error'>('done');
  const processedRef = useRef(false);

  const resolveTarget = useCallback((state: string | null) => {
    let target = '/profile';
    if (typeof window === 'undefined') return target;

    const params = new URLSearchParams(window.location.search);
    const next = params.get('next');
    if (next) {
      target = next;
    } else if (state) {
      try {
        const saved = sessionStorage.getItem(`vpn_auth_next_${state}`);
        if (saved) {
          target = saved;
          sessionStorage.removeItem(`vpn_auth_next_${state}`);
        }
      } catch {
        // ignore
      }
    }
    return target;
  }, []);

  const completeAuth = useCallback((state: string | null) => {
    setStatus('done');
    const target = resolveTarget(state);
    window.location.replace(target);
  }, [resolveTarget]);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    if (typeof window === 'undefined') return;

    const params = new URLSearchParams(window.location.search);
    const state = params.get('state');

    if (!state) {
      setStatus('done');
      return;
    }

    setStatus('processing');

    let cancelled = false;
    const poll = async () => {
      try {
        const res = await pollTelegramAuth(state);
        if (cancelled) return;
        if (res.status === 'completed') {
          completeAuth(state);
        } else if (res.status === 'expired') {
          setStatus('error');
          window.location.replace('/login?error=auth_expired');
        }
      } catch {
        // ignore poll errors
      }
    };

    poll();
    const interval = setInterval(poll, 2000);
    const timeout = setTimeout(() => {
      clearInterval(interval);
      if (!cancelled) {
        setStatus('error');
        window.location.replace('/login?error=auth_timeout');
      }
    }, TELEGRAM_POLL_TIMEOUT_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
      clearTimeout(timeout);
    };
  }, [completeAuth, resolveTarget]);

  if (status === 'done') return null;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-primary)',
      color: 'var(--text-primary)',
      fontSize: '14px',
      zIndex: 9999,
    }}>
      {status === 'processing' ? t('texts.authenticating') : t('texts.auth_error')}
    </div>
  );
}
