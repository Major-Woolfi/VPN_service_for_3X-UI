// Типы для API бота

// === Auth ===
export interface WebRegisterRequest {
  username: string;
  password: string;
  tg_id?: number;
}

export interface WebLoginRequest {
  username: string;
  password: string;
}

export interface TelegramLoginRequest {
  tg_id: number;
  state: string;
}

export interface WebPasswordChangeRequest {
  old_password: string;
  new_password: string;
}

export interface WebTelegramLinkRequest {
  tg_id: number;
  password?: string;
}

export interface UserSession {
  user_id: number;
  web_id: string | null;
  token: string;
}

// === User / Profile ===
export interface SanitizedUser {
  user_id: number;
  telegram_id: number;
  username: string | null;
  login: string | null;
  language: string;
  trust_score: number;
  discount_percent: number;
  subscription: SubscriptionData;
  referral: ReferralData;
  partner: PartnerData;
  is_partner: boolean;
  pending_partner_application: boolean;
  trial_used: boolean;
  join_date: string;
  web_id: number | null;
  web_auth_method: string | null;
  is_admin: boolean;
  is_mate: boolean;
  mate_balance: number;
  mate_commission_total: number;
  mate_status: string;
  mate_followers: number;
  mate_avg_reach: number;
  mate_period_months: number;
  mate_ref_link_code: string;
  mate_subscription_id: string;
  mate_expiry: string;
  admin_subscription: {
    url: string;
    json_url: string;
  } | null;
  has_pending_payment: boolean;
  partner_subscription: {
    sub_id: string;
    expiry: string;
    url: string;
    json_url: string;
  } | null;
  has_password: boolean;
  banned: boolean;
  ban_reason: string;
}

export interface SubscriptionData {
  status: string;
  plan_text?: string;
  traffic_gb?: number;
  extra_sub_gb?: number;
  ip_limit?: number;
  vpn_url?: string;
  plan_servers?: ServerInfo[];
  used_gb?: number;
  max_expiry?: number;
  expiry_sub_datatime?: string;
}

export interface ServerInfo {
  server: string;
  ip: string;
}

export interface ReferralData {
  ref_code: string;
  ref_link: string;
  referrals_count: number;
  referrals_paid: number;
}

export interface PartnerData {
  mate_balance: number;
  mate_commission_total: number;
  mate_status: string;
  mate_followers: number;
  mate_avg_reach: number;
  mate_period_months: number;
  mate_ref_link_code: string;
  mate_subscription_id: string;
  mate_expiry: string;
}

// === Subscription ===
export interface CreateSubscriptionRequest {
  plan_id: string;
  plan_name?: string;
  ip_limit?: number;
  traffic_gb?: number;
  servers?: string[];
  duration_days?: number;
  price_rub?: number;
}

export interface ExtendSubscriptionRequest {
  user_id: number;
  days: number;
}

export interface SubscriptionLinkResponse {
  subscription_id: string;
  vpn_url: string;
  json_vpn_url: string;
  plan_text: string;
  traffic_gb: number;
  ip_limit: number;
  plan_servers: ServerInfo[];
}

// === Tariff ===
export interface Tariff {
  id: string;
  name: string;
  price_rub: number;
  traffic_gb: number;
  ip_limit: number;
  duration_days: number;
  servers: string[];
  active: boolean;
  locations: string[];
  is_trial?: boolean;
}

export interface TariffsResponse {
  tariffs: Tariff[];
}

// === Referral Stats ===
export interface ReferralStatsResponse {
  ref_code: string;
  ref_link: string;
  total_refs: number;
  paid_refs: number;
  unpaid_refs: number;
  conversion_rate: number;
  bonus_days_per_paid: number;
}

// === Partner Stats ===
export interface PartnerStatsResponse {
  total_refs: number;
  paid_refs: number;
  unpaid_refs: number;
  balance: number;
  commission_total: number;
  conversion_rate: number;
  avg_commission_per_paid: number;
}

export interface PartnerProfileResponse {
  balance: number;
  commission_total: number;
  referrals_count: number;
  referrals_paid: number;
  status: string;
  period_months: number;
  subscription_id: string;
  expiry: string;
  ref_link_code: string;
}

export interface PartnerApplyRequest {
  followers: number;
  social_links: string;
  nickname: string;
  period_months: number;
  bonus_type: string;
  bonus_value: number;
  pd_consent: number;
}

// === Custom Tariff ===
export interface CustomTariffParams {
  base_price: number;
  gb_coef: number;
  ip_day_coef: number;
  min_gb: number;
  max_gb: number;
  min_ip: number;
  max_ip: number;
  min_days: number;
  max_days: number;
  locations: Location[];
}

export interface CustomTariffCalculateRequest {
  traffic_gb: number;
  ip_limit: number;
  duration_days: number;
  servers?: string[];
}

export interface CustomTariffCalculateResponse {
  total_price: number;
  base_price: number;
  traffic_cost: number;
  ip_cost: number;
  locations_cost: number;
}

// === Locations ===
export interface Location {
  code: string;
  name: string;
  flag: string;
  label?: string;
  price_per_day_rub?: number;
}

export interface LocationsResponse {
  locations: Location[];
}

// === Admin ===
export interface AdminHealthResponse {
  status: string;
  users: {
    total: number;
    banned: number;
    active_subscriptions: number;
    partners: number;
  };
  payments: {
    pending: number;
    processing: number;
    total_stored: number;
  };
  partner_operations: {
    pending: number;
  };
  tech_work_mode: boolean;
}

export interface AdminUserFullInfo {
  user: SanitizedUser;
  subscriptions: unknown[];
  pending_payments: unknown[];
  partner_info: unknown;
  panel_info: unknown;
}

export interface BulkActionRequest {
  action: string;
  user_ids: number[];
  reason?: string;
}

export interface BulkActionResult {
  processed: number;
  errors: number;
  results: unknown[];
}

export interface DebugCleanupRequest {
  dry_run: boolean;
  cleanup_expired?: boolean;
  cleanup_traffic_exhausted?: boolean;
  cleanup_missing?: boolean;
}

export interface DebugSearchResponse {
  query: string;
  count: number;
  users: SanitizedUser[];
}

// === Payments ===
export interface PendingPayment {
  id: string;
  user_id: number;
  plan_text: string;
  method: string;
  amount: number;
  status: string;
  created_at: string;
}

export interface PaymentsHistoryResponse {
  payments: PendingPayment[];
  total: number;
  page: number;
  limit: number;
}

// === Broadcast ===
export interface BroadcastRequest {
  type: string;
  message: string;
}

// === Panel Clients ===
export interface PanelClient {
  sub_id: string;
  email: string;
  enable: boolean;
  expiryTime: number;
  totalGB: number;
  up: number;
  down: number;
  [key: string]: unknown;
}

// === User List ===
export interface UserListItem {
  user_id: number;
  telegram_id: number;
  username: string;
  join_date: string;
  has_subscription: number;
  is_mate: number;
  language: string;
  trust_score: number;
  abuse_status?: string;
  daily_traffic_usage?: number;
}

export interface UserListResponse {
  users: UserListItem[];
  total: number;
  page: number;
  limit: number;
}

// === Stats Overview ===
export interface StatsOverviewResponse {
  total_users: number;
  active_subscriptions: number;
  banned_users: number;
}

// === Panel Status ===
export interface PanelStatusResponse {
  panel: {
    panel_version: string;
    xray_version: string;
    panel_base?: string;
  };
  server_status: Record<string, unknown>;
  nodes: Record<string, unknown>[];
}

// === Partner Public Info ===
export interface PartnerPublicInfoResponse {
  commission_percent: number;
  min_followers: number;
  min_avg_reach: number;
  required_socials: string;
  terms_url: string;
  min_period_months: number;
  max_period_months: number;
  bonus_days_min: number;
  bonus_days_max: number;
  trust_points_min: number;
  trust_points_max: number;
}

// === Features / Config ===
export interface FeaturesResponse {
  payment_methods: string[];
  payment_card?: string;
  yoomoney?: string;
  panel_types: {
    main: boolean;
    json: boolean;
  };
  features: {
    custom_tariff: boolean;
    partner: boolean;
    telegram_login: boolean;
  };
  public_links: Record<string, string>;
}

// === Traffic Abuse ===
export interface AbuseUser {
  user_id: number;
  telegram_id: number;
  username: string;
  language: string;
  abuse_status: string;
  daily_traffic_gb: number;
  total_traffic_gb: number;
  daily_traffic_date: string;
  has_subscription: number;
  trust_score: number;
}

export interface AbuseUsersResponse {
  users: AbuseUser[];
}

export interface ClearAbuseRequest {
  user_id: number;
  reason?: string;
}
