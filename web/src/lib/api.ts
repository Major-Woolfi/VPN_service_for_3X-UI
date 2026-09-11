// API client для бота - все эндпоинты /api/v1/*
// Сессия хранится в httpOnly cookie (vpn_token), credentials: 'include' обязателен.

import type {
  UserSession,
  WebRegisterRequest,
  WebLoginRequest,
  TelegramLoginRequest,
  WebPasswordChangeRequest,
  WebTelegramLinkRequest,
  SanitizedUser,
  SubscriptionLinkResponse,
  Tariff,
  TariffsResponse,
  ReferralStatsResponse,
  PartnerStatsResponse,
  PartnerProfileResponse,
  PartnerPublicInfoResponse,
  PartnerApplyRequest,
  Location,
  LocationsResponse,
  AdminHealthResponse,
  DebugCleanupRequest,
  DebugSearchResponse,
  UserListResponse,
  AbuseUsersResponse,
  ClearAbuseRequest,
  StatsOverviewResponse,
  PanelStatusResponse,
  CreateSubscriptionRequest,
  CustomTariffParams,
} from './types';
import { t } from './i18n';

export const API_BASE_URL = (process.env.NEXT_PUBLIC_BOT_API_URL || 'http://localhost:2005/api/v1').replace(/\/$/, '');
export const DEFAULT_API_BASE = 'http://localhost:2005/api/v1';
export const REQUEST_TIMEOUT_MS = 15_000;
export const HEALTH_POLL_INTERVAL_MS = 30_000;
export const PANEL_STATUS_POLL_INTERVAL_MS = 10_000;
export const TOKEN_REFRESH_INTERVAL_MS = 5 * 60_000;
export const TELEGRAM_POLL_INTERVAL_MS = 2_000;
export const TELEGRAM_POLL_TIMEOUT_MS = 120_000;

const _rateLimits: Record<string, number> = {};
function rateLimit(key: string, minIntervalMs: number): boolean {
  const now = Date.now();
  const last = _rateLimits[key] || 0;
  if (now - last < minIntervalMs) return false;
  _rateLimits[key] = now;
  return true;
}

const TOKEN_STORAGE_KEY = 'vpn_token';

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // ignore
  }
}

export function clearStoredToken(): void {
  try {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// ==========================================
// Вспомогательные функции
// ==========================================

export async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  let controller: AbortSignal;
  if (typeof AbortSignal.timeout === 'function') {
    controller = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  } else {
    const abortController = new AbortController();
    setTimeout(() => abortController.abort(), REQUEST_TIMEOUT_MS);
    controller = abortController.signal;
  }
  const signal = options.signal || controller;
  const isExternal = /^https?:\/\//i.test(url);
  const token = getStoredToken();
  const baseHeaders: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) {
    baseHeaders['Authorization'] = `Bearer ${token}`;
  }
  const headers: Record<string, string> = {
    ...baseHeaders,
    ...(options.headers as Record<string, string> | undefined),
  };
  const res = await fetch(url, {
    signal,
    ...options,
    credentials: isExternal ? 'include' : 'same-origin',
    headers,
  });
  if (!res.ok) {
    const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const detail = payload.detail as unknown;
    const messages: string[] = Array.isArray(detail)
      ? detail
          .map((item) => {
            const entry = item as Record<string, unknown>;
            if (typeof entry.msg === 'string') return entry.msg;
            if (typeof entry === 'string') return entry;
            return '';
          })
          .filter(Boolean)
      : typeof detail === 'string'
        ? [detail]
        : [];
    const message =
      (typeof payload.error === 'string' && payload.error) ||
      messages.join(', ') ||
      `HTTP ${res.status}`;
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

// ==========================================
// ПУБЛИЧНЫЕ ЭНДПОИНТЫ (без авторизации)
// ==========================================

export async function getPartnerPublicInfo(): Promise<PartnerPublicInfoResponse> {
  return fetchJson<PartnerPublicInfoResponse>(`${API_BASE_URL}/partner/public-info`);
}

export async function getHealth() {
  if (!rateLimit('health', 1000)) return Promise.reject(new Error(t('texts.rate_limited')));
  return fetchJson(`${API_BASE_URL}/health`) as Promise<{ status: string; version: string }>;
}

export async function getFeatures(): Promise<import('./types').FeaturesResponse> {
  return fetchJson(`${API_BASE_URL}/config/features`);
}

export async function startTelegramAuth(): Promise<{ url: string; state: string }> {
  return fetchJson(`${API_BASE_URL}/auth/telegram/start`, {
    method: 'POST',
  });
}

export async function pollTelegramAuth(
  state: string
): Promise<{ status: string; token?: string }> {
  const res = await fetchJson<{ status: string; token?: string }>(
    `${API_BASE_URL}/auth/telegram/status/${encodeURIComponent(state)}`
  );
  if (res.status === 'completed' && res.token) {
    setStoredToken(res.token);
  }
  return res;
}

export async function startTelegramLink(): Promise<{ url: string; state: string }> {
  return fetchJson(`${API_BASE_URL}/auth/telegram/link-start`, {
    method: 'POST',
  });
}

export async function getTariffs(): Promise<Tariff[]> {
  try {
    const data = await fetchJson<TariffsResponse>(`${API_BASE_URL}/tariffs`);
    return data.tariffs || [];
  } catch {
    return [];
  }
}

export async function getLocations(): Promise<Location[]> {
  try {
    const data = await fetchJson<LocationsResponse>(`${API_BASE_URL}/locations`);
    return data.locations || [];
  } catch {
    return [];
  }
}

export async function verifySubscription(sub_id: string) {
  return fetchJson(`${API_BASE_URL}/subscription/verify/${encodeURIComponent(sub_id)}`) as Promise<{
    valid: boolean;
    max_expiry: number;
    clients_count: number;
  }>;
}

export async function getStatsOverview() {
  return fetchJson<StatsOverviewResponse>(`${API_BASE_URL}/stats/overview`);
}

export async function getPanelStatus(): Promise<PanelStatusResponse> {
  if (!rateLimit('panel-status', 1000)) return Promise.reject(new Error(t('texts.rate_limited')));
  return fetchJson<PanelStatusResponse>(`${API_BASE_URL}/stats/panel-status`);
}

export async function registerUser(req: WebRegisterRequest): Promise<UserSession> {
  const session = await fetchJson<UserSession>(`${API_BASE_URL}/auth/register`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
  if (session?.token) {
    setStoredToken(session.token);
  }
  return session;
}

export async function loginUser(req: WebLoginRequest): Promise<UserSession> {
  const session = await fetchJson<UserSession>(`${API_BASE_URL}/auth/login`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
  if (session?.token) {
    setStoredToken(session.token);
  }
  return session;
}

// ==========================================
// AUTHORIZED ЭНДПОИНТЫ (нужен token)
// ==========================================

export async function getMe(): Promise<SanitizedUser> {
  if (!rateLimit('getMe', 1000)) return Promise.reject(new Error(t('texts.rate_limited')));
  const response = await fetchJson<SanitizedUser>(`${API_BASE_URL}/profile`);
  return response;
}

export async function getPartnerPendingStatus(): Promise<{ has_pending_application: boolean }> {
  return fetchJson(`${API_BASE_URL}/partner/pending-status`);
}

export async function logoutUser() {
  clearStoredToken();
  return fetchJson(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
  });
}

export async function changePassword(req: WebPasswordChangeRequest) {
  return fetchJson(`${API_BASE_URL}/auth/change-password`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function linkTelegram(req: WebTelegramLinkRequest & { password?: string }) {
  return fetchJson(`${API_BASE_URL}/auth/telegram/link`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function unlinkTelegram(req: { password?: string }) {
  return fetchJson(`${API_BASE_URL}/auth/telegram/unlink`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function telegramLogin(req: TelegramLoginRequest) {
  return fetchJson<UserSession>(`${API_BASE_URL}/auth/telegram/login`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function changeLanguage(language: string) {
  return fetchJson(`${API_BASE_URL}/profile/language`, {
    method: 'PATCH',
    body: JSON.stringify({ language }),
  });
}

export async function createSubscription(req: CreateSubscriptionRequest) {
  return fetchJson(`${API_BASE_URL}/subscription/create`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function renewSubscription(req: CreateSubscriptionRequest) {
  return fetchJson(`${API_BASE_URL}/subscription/renew`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function trialSubscription() {
  return fetchJson(`${API_BASE_URL}/subscription/trial`, {
    method: 'POST',
  });
}

export async function getSubscriptionLink(signal?: AbortSignal): Promise<SubscriptionLinkResponse> {
  return fetchJson<SubscriptionLinkResponse>(`${API_BASE_URL}/subscription/link`, { signal });
}

export async function addTraffic(gb: number) {
  return fetchJson(`${API_BASE_URL}/subscription/add-traffic`, {
    method: 'POST',
    body: JSON.stringify({ gb }),
  });
}

export async function createCheckout(
  req: { plan_id: string; method: string; custom_plan?: { name: string; price_rub: number; ip_limit: number; traffic_gb: number; duration_days: number; servers?: string[] } },
): Promise<{ checkout_url: string; payment_id: string }> {
  return fetchJson(`${API_BASE_URL}/payments/create-checkout`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getReferralStats(): Promise<ReferralStatsResponse> {
  return fetchJson<ReferralStatsResponse>(`${API_BASE_URL}/referrals/stats`);
}

export async function getPartnerProfile(): Promise<PartnerProfileResponse> {
  return fetchJson<PartnerProfileResponse>(`${API_BASE_URL}/partner/profile`);
}

export async function getPartnerStats(): Promise<PartnerStatsResponse> {
  return fetchJson<PartnerStatsResponse>(`${API_BASE_URL}/partner/stats`);
}

export async function partnerApply(req: PartnerApplyRequest) {
  return fetchJson(`${API_BASE_URL}/partner/apply`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function generateCustomTariff(
  req: { traffic_gb: number; ip_limit: number; duration_days: number; servers?: string[] }
): Promise<{ plan: { id: string; name: string; price_rub: number; ip_limit: number; traffic_gb: number; duration_days: number }; total_price: number }> {
  return fetchJson(`${API_BASE_URL}/tariffs/custom/generate`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function getCustomTariffParams(): Promise<CustomTariffParams> {
  return fetchJson<CustomTariffParams>(`${API_BASE_URL}/tariffs/custom/params`);
}

export async function partnerWithdraw(req: {
  amount: number;
  fio: string;
  phone: string;
  bank: string;
}) {
  return fetchJson(`${API_BASE_URL}/partner/withdraw`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ==========================================
// ADMIN ЭНДПОИНТЫ (через server-side proxy, ключ на сервере)
// ==========================================

export async function getAdminHealth(): Promise<AdminHealthResponse> {
  if (!rateLimit('admin-health', 1000)) return Promise.reject(new Error(t('texts.rate_limited')));
  return fetchJson<AdminHealthResponse>(`/api/admin/health`);
}

export async function getAdminPanelStatus(): Promise<PanelStatusResponse> {
  return fetchJson<PanelStatusResponse>(`/api/admin/panel-status`);
}

export async function getUsers(page = 1, limit = 50): Promise<UserListResponse> {
  return fetchJson<UserListResponse>(`/api/admin/users?page=${page}&limit=${limit}`);
}

export interface PublicLinks {
  site_url?: string;
  support_url?: string;
  qna_url: string;
  privacy_policy_url: string;
  public_offer_url: string;
  tiktok_url?: string;
  youtube_url?: string;
  telegram_channel_username?: string;
  telegram_bot_username?: string;
  setup_guide_url?: string;
  client_app_url?: string;
  terms_of_service_url: string;
  telegram_chat_url?: string;
  email_url?: string;
  payment_card?: string;
  yoomoney?: string;
}

export function getPublicLinks(): PublicLinks {
  return {
    site_url: process.env.NEXT_PUBLIC_SITE_URL,
    support_url: process.env.NEXT_PUBLIC_TELEGRAM_SUPPORT,
    qna_url: '/qa',
    privacy_policy_url: '/privacy',
    public_offer_url: '/offer',
    tiktok_url: process.env.NEXT_PUBLIC_TIKTOK_URL,
    youtube_url: process.env.NEXT_PUBLIC_YOUTUBE_URL,
    telegram_channel_username: process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_USERNAME,
    telegram_bot_username: process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME,
    setup_guide_url: process.env.NEXT_PUBLIC_SETUP_GUIDE_URL,
    client_app_url: process.env.NEXT_PUBLIC_CLIENT_APP_URL,
    terms_of_service_url: '/tos',
    telegram_chat_url: process.env.NEXT_PUBLIC_TELEGRAM_CHAT,
    email_url: process.env.NEXT_PUBLIC_EMAIL_URL,
    payment_card: process.env.NEXT_PUBLIC_PAYMENT_CARD_NUMBER,
    yoomoney: process.env.NEXT_PUBLIC_YOOMONEY_WALLET,
  };
}

export async function debugCleanup(req: DebugCleanupRequest) {
  return fetchJson(`/api/admin/debug`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function debugSearch(query: string): Promise<DebugSearchResponse> {
  if (!rateLimit('debug-search', 1000)) return Promise.reject(new Error(t('texts.rate_limited')));
  const url = `/api/admin/debug/search?q=${encodeURIComponent(query)}`;
  return fetchJson<DebugSearchResponse>(url);
}

// ==========================================
// ABUSE ЭНДПОИНТЫ
// ==========================================

export async function getAbuseUsers(): Promise<AbuseUsersResponse> {
  return fetchJson<AbuseUsersResponse>(`/api/admin/abuse-users`);
}

export async function clearAbuse(req: ClearAbuseRequest) {
  return fetchJson(`/api/admin/users/${req.user_id}/clear-abuse`, {
    method: 'POST',
    body: JSON.stringify(req),
  });
}
