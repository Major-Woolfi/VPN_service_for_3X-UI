// API client для бота - все эндпоинты идут через same-origin прокси /api/bot/*.
// Прокси живёт на сервере Next (src/app/api/bot/[...path]), поэтому:
//  - нет CORS и preflight-запросов вообще;
//  - токен сессии живёт только в httpOnly cookie, недоступной из JS;
//  - 401 от бота превращается в 401 + auth_expired, клиент сам разлогинивает.

import type {
  UserSession,
  WebRegisterRequest,
  WebLoginRequest,
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
  PartnerApplyResponse,
  PartnerRenewRequest,
  PartnerRenewResponse,
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
  CreateCheckoutRequest,
  CheckoutResponse,
  TestSubscriptionResponse,
  CustomTariffParams,
  CustomTariffGenerateResponse,
  SubscriptionPaymentRequest,
} from "./types";
import { t } from "./i18n";

export const API_BASE_URL = "/api/bot";
export const DEFAULT_API_BASE = API_BASE_URL;
export const SERVER_API_BASE = (
  process.env.BOT_API_URL || "http://localhost:2005/api/v1"
).replace(/\/$/, "");
export const REQUEST_TIMEOUT_MS = 15_000;
export const HEALTH_POLL_INTERVAL_MS = 10_000;
export const PANEL_STATUS_POLL_INTERVAL_MS = 5_000;
export const TELEGRAM_POLL_INTERVAL_MS = 1_500;
export const TELEGRAM_POLL_TIMEOUT_MS = 120_000;

export const SESSION_LOST_EVENT = "vpn:session-lost";

const RATE_LIMIT_STORAGE_KEY = "vpn_rate_limits";

function readRateLimits(): Record<string, number> {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(RATE_LIMIT_STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, number>;
  } catch {
    return {};
  }
}

function writeRateLimits(limits: Record<string, number>): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(RATE_LIMIT_STORAGE_KEY, JSON.stringify(limits));
  } catch {
    // ignore
  }
}

function rateLimit(key: string, minIntervalMs: number): boolean {
  const now = Date.now();
  const limits = readRateLimits();
  const last = limits[key] || 0;
  if (now - last < minIntervalMs) return false;
  limits[key] = now;
  writeRateLimits(limits);
  return true;
}

// ==========================================
// Кулдаун после сетевых ошибок и 429
// ==========================================

const COOLDOWN_STORAGE_PREFIX = "vpn_cooldown:";

function readEndpointCooldown(path: string): number {
  if (typeof localStorage === "undefined") return 0;
  try {
    const value = Number(localStorage.getItem(COOLDOWN_STORAGE_PREFIX + path));
    if (!value) return 0;
    if (value <= Date.now()) {
      localStorage.removeItem(COOLDOWN_STORAGE_PREFIX + path);
      return 0;
    }
    return value;
  } catch {
    return 0;
  }
}

function setEndpointCooldown(path: string, ms: number): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(
      COOLDOWN_STORAGE_PREFIX + path,
      String(Date.now() + ms),
    );
  } catch {
    // ignore
  }
}

function clearEndpointCooldown(path: string): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.removeItem(COOLDOWN_STORAGE_PREFIX + path);
  } catch {
    // ignore
  }
}

// ==========================================
// Автовыход при потере сессии
// ==========================================

function notifySessionLost(): void {
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent(SESSION_LOST_EVENT));
  } catch {
    // ignore
  }
}

// ==========================================
// Вспомогательные функции
// ==========================================

function endpointPath(path: string): string {
  return path.split("?")[0];
}

function extractErrorMessage(
  payload: Record<string, unknown>,
  status: number,
): string {
  const detail = payload.detail as unknown;
  const messages: string[] = Array.isArray(detail)
    ? detail
        .map((item) => {
          const entry = item as Record<string, unknown>;
          if (typeof entry.msg === "string") return entry.msg;
          if (typeof entry === "string") return entry;
          return "";
        })
        .filter(Boolean)
    : typeof detail === "string"
      ? [detail]
      : [];
  const raw =
    (typeof payload.error === "string" && payload.error) ||
    messages.join(", ") ||
    `HTTP ${status}`;
  return raw;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly authExpired: boolean;

  constructor(
    message: string,
    status: number,
    code = "error",
    authExpired = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.authExpired = authExpired;
  }
}

export async function fetchJson<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = path.startsWith("/") ? path : `${API_BASE_URL}/${path}`;
  const target = url.startsWith("/api/") ? url : `${API_BASE_URL}${url}`;

  const blockedUntil = readEndpointCooldown(endpointPath(target));
  if (blockedUntil > 0) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited", false);
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };

  let res: Response;
  try {
    res = await fetch(target, {
      ...options,
      cache: "no-store",
      credentials: "same-origin",
      headers,
      signal: options.signal || AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const aborted =
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError");
    if (!options.signal) {
      setEndpointCooldown(endpointPath(target), 5_000);
    }
    throw new ApiError(
      aborted ? t("texts.api_timeout") : t("texts.api_unavailable"),
      aborted ? 504 : 503,
      aborted ? "timeout" : "network",
      false,
    );
  }

  const payload = (await res.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;

  if (!res.ok) {
    const authExpired = payload.auth_expired === true;
    const message = extractErrorMessage(payload, res.status);
    const code = typeof payload.error === "string" ? payload.error : "error";

    // Автовыход - ТОЛЬКО когда прокси подтвердил потерю сессии
    // (auth_expired выставляется им только при наличии cookie).
    // Голый 401 у гостя - это обычный ответ на запрос без токена,
    // и реагировать на него нельзя, иначе гостя выкидывает на /login.
    if (authExpired) {
      clearStoredUser();
      notifySessionLost();
    }
    if (res.status === 429) {
      setEndpointCooldown(endpointPath(target), 15_000);
    }
    if (res.status >= 500) {
      setEndpointCooldown(endpointPath(target), 3_000);
    }

    throw new ApiError(
      message,
      res.status,
      code,
      // authExpired приходит только от прокси и означает реальную
      // потерю сессии. Эвристика по тексту сообщения больше не нужна:
      // она срабатывала на любом 401, включая запросы гостя.
      authExpired,
    );
  }

  clearEndpointCooldown(endpointPath(target));

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    delete payload.auth_expired;
  }

  return payload as T;
}

// ==========================================
// ПУБЛИЧНЫЕ ЭНДПОИНТЫ (без авторизации)
// ==========================================

export async function getPartnerPublicInfo(): Promise<PartnerPublicInfoResponse> {
  return fetchJson<PartnerPublicInfoResponse>(
    `${API_BASE_URL}/partner/public-info`,
  );
}

export async function getHealth() {
  if (!rateLimit("health", 2000)) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited");
  }
  return fetchJson<{ status: string; version: string }>(
    `${API_BASE_URL}/health`,
  );
}

export async function getFeatures() {
  return fetchJson<import("./types").FeaturesResponse>(
    `${API_BASE_URL}/config/features`,
  );
}

export async function startTelegramAuth(): Promise<{
  url: string;
  state: string;
}> {
  return fetchJson(`${API_BASE_URL}/auth/telegram/start`, { method: "POST" });
}

export async function pollTelegramAuth(
  state: string,
): Promise<{ status: string }> {
  return fetchJson<{ status: string }>(
    `${API_BASE_URL}/auth/telegram/status/${encodeURIComponent(state)}`,
  );
}

export async function startTelegramLink(): Promise<{
  url: string;
  state: string;
}> {
  return fetchJson(`${API_BASE_URL}/auth/telegram/link-start`, {
    method: "POST",
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
    const data = await fetchJson<LocationsResponse>(
      `${API_BASE_URL}/locations`,
    );
    return data.locations || [];
  } catch {
    return [];
  }
}

export async function verifySubscription(subId: string) {
  return fetchJson<{
    valid: boolean;
    max_expiry: number;
    clients_count: number;
  }>(`${API_BASE_URL}/subscription/verify/${encodeURIComponent(subId)}`);
}

export async function getStatsOverview() {
  return fetchJson<StatsOverviewResponse>(`${API_BASE_URL}/stats/overview`);
}

export async function getPanelStatus(): Promise<PanelStatusResponse> {
  if (!rateLimit("panel-status", 2000)) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited");
  }
  return fetchJson<PanelStatusResponse>(`${API_BASE_URL}/stats/panel-status`);
}

export async function registerUser(
  req: WebRegisterRequest,
): Promise<UserSession> {
  return fetchJson<UserSession>(`${API_BASE_URL}/auth/register`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function loginUser(req: WebLoginRequest): Promise<UserSession> {
  return fetchJson<UserSession>(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ==========================================
// AUTHORIZED ЭНДПОИНТЫ (сессия в httpOnly cookie)
// ==========================================

export async function getMe(signal?: AbortSignal): Promise<SanitizedUser> {
  return fetchJson<SanitizedUser>(`${API_BASE_URL}/profile`, { signal });
}

export async function getPartnerPendingStatus(): Promise<{
  has_pending_application: boolean;
}> {
  return fetchJson(`${API_BASE_URL}/partner/pending-status`);
}

export async function logoutUser(): Promise<void> {
  try {
    await fetchJson(`${API_BASE_URL}/auth/logout`, { method: "POST" });
  } catch {
    // Сессия всё равно должна быть забыта локально.
  }
  clearStoredUser();
}

export async function changePassword(req: WebPasswordChangeRequest) {
  return fetchJson(`${API_BASE_URL}/auth/change-password`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function linkTelegram(req: WebTelegramLinkRequest) {
  return fetchJson(`${API_BASE_URL}/auth/telegram/link`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function changeLanguage(language: string) {
  return fetchJson(`${API_BASE_URL}/profile/language`, {
    method: "PATCH",
    body: JSON.stringify({ language }),
  });
}

export async function createSubscription(
  req: CreateSubscriptionRequest,
): Promise<SubscriptionPaymentRequest> {
  return fetchJson<SubscriptionPaymentRequest>(
    `${API_BASE_URL}/subscription/create`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

export async function renewSubscription(
  req: CreateSubscriptionRequest,
): Promise<SubscriptionPaymentRequest> {
  return fetchJson<SubscriptionPaymentRequest>(
    `${API_BASE_URL}/subscription/renew`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

export async function trialSubscription() {
  return fetchJson(`${API_BASE_URL}/subscription/trial`, { method: "POST" });
}

export async function getSubscriptionLink(
  signal?: AbortSignal,
): Promise<SubscriptionLinkResponse> {
  return fetchJson<SubscriptionLinkResponse>(
    `${API_BASE_URL}/subscription/link`,
    {
      signal,
    },
  );
}

export async function addTraffic(gb: number) {
  return fetchJson(`${API_BASE_URL}/subscription/add-traffic`, {
    method: "POST",
    body: JSON.stringify({ gb }),
  });
}

export async function createCheckout(
  req: CreateCheckoutRequest,
): Promise<CheckoutResponse> {
  return fetchJson<CheckoutResponse>(
    `${API_BASE_URL}/payments/create-checkout`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
}

export async function createTestSubscription(
  req: CreateCheckoutRequest,
): Promise<TestSubscriptionResponse> {
  return fetchJson<TestSubscriptionResponse>(
    `${API_BASE_URL}/subscription/test`,
    {
      method: "POST",
      body: JSON.stringify(req),
    },
  );
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

export async function partnerApply(
  req: PartnerApplyRequest,
): Promise<PartnerApplyResponse> {
  return fetchJson<PartnerApplyResponse>(`${API_BASE_URL}/partner/apply`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function partnerRenew(
  req: PartnerRenewRequest,
): Promise<PartnerRenewResponse> {
  return fetchJson<PartnerRenewResponse>(`${API_BASE_URL}/partner/renew`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function generateCustomTariff(req: {
  traffic_gb: number;
  ip_limit: number;
  duration_days: number;
  servers?: string[];
}): Promise<CustomTariffGenerateResponse> {
  return fetchJson<CustomTariffGenerateResponse>(
    `${API_BASE_URL}/tariffs/custom/generate`,
    { method: "POST", body: JSON.stringify(req) },
  );
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
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ==========================================
// ADMIN ЭНДПОИНТЫ (через server-side proxy, ключ на сервере)
// ==========================================

export async function getAdminHealth(): Promise<AdminHealthResponse> {
  if (!rateLimit("admin-health", 2000)) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited");
  }
  return fetchJson<AdminHealthResponse>(`/api/admin/health`);
}

export async function getAdminPanelStatus(): Promise<PanelStatusResponse> {
  if (!rateLimit("panel-status", 2000)) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited");
  }
  return fetchJson<PanelStatusResponse>(`/api/admin/panel-status`);
}

export async function getUsers(
  page = 1,
  limit = 50,
): Promise<UserListResponse> {
  return fetchJson<UserListResponse>(
    `/api/admin/users?page=${page}&limit=${limit}`,
  );
}

export interface PublicLinks {
  site_url?: string;
  support_url?: string;
  qna_url?: string;
  privacy_policy_url?: string;
  public_offer_url?: string;
  tiktok_url?: string;
  youtube_url?: string;
  telegram_url?: string;
  setup_guide_url?: string;
  client_app_url?: string;
  terms_of_service_url?: string;
  telegram_bot_username?: string;
  telegram_channel_username?: string;
  telegram_chat_url?: string;
  email_url?: string;
}

export function getPublicLinksFromFeatures(
  features: import("./types").FeaturesResponse | null,
): PublicLinks {
  const links: Record<string, string> = features?.public_links ?? {};
  const get = (key: string): string | undefined => {
    const v = links[key];
    return typeof v === "string" && v.trim() ? v : undefined;
  };
  return {
    site_url: get("site_url") || process.env.NEXT_PUBLIC_SITE_URL,
    support_url: get("support_url"),
    qna_url: get("qna_url") || "/qa",
    privacy_policy_url: get("privacy_policy_url") || "/privacy",
    public_offer_url: get("public_offer_url") || "/offer",
    tiktok_url: get("tiktok_url"),
    youtube_url: get("youtube_url"),
    telegram_url: get("telegram_url"),
    setup_guide_url: get("setup_guide_url"),
    client_app_url: get("client_app_url"),
    terms_of_service_url: get("terms_of_service_url") || "/tos",
    telegram_bot_username:
      process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || undefined,
    telegram_channel_username:
      process.env.NEXT_PUBLIC_TELEGRAM_CHANNEL_USERNAME || undefined,
    telegram_chat_url: process.env.NEXT_PUBLIC_TELEGRAM_CHAT || undefined,
    email_url: process.env.NEXT_PUBLIC_EMAIL_URL || undefined,
  };
}

export async function debugCleanup(req: DebugCleanupRequest) {
  return fetchJson(`/api/admin/debug`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function debugSearch(query: string): Promise<DebugSearchResponse> {
  if (!rateLimit("debug-search", 2000)) {
    throw new ApiError(t("texts.rate_limited"), 429, "rate_limited");
  }
  return fetchJson<DebugSearchResponse>(
    `/api/admin/debug/search?q=${encodeURIComponent(query)}`,
  );
}

// ==========================================
// ABUSE ЭНДПОИНТЫ
// ==========================================

export async function getAbuseUsers(): Promise<AbuseUsersResponse> {
  return fetchJson<AbuseUsersResponse>(`/api/admin/abuse-users`);
}

export async function clearAbuse(req: ClearAbuseRequest) {
  return fetchJson(`/api/admin/users/${req.user_id}/clear-abuse`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ==========================================
// Кэш пользователя (только для мгновенной отрисовки, не источник истины)
// ==========================================

const USER_KEY = "vpn_user";

export function readStoredUser<T>(): T | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function writeStoredUser(value: unknown): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(value));
  } catch {
    // ignore
  }
}

export function clearStoredUser(): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(RATE_LIMIT_STORAGE_KEY);
  } catch {
    // ignore
  }
}
