export interface WebRegisterRequest {
  web_login: string;
  password: string;
  tg_id?: number;
  ref_code?: string;
}

export interface WebLoginRequest {
  web_login: string;
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

export interface UserSession {
  user_id: number;
  web_id: number;
  ttoken: string;
}

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
  partner: Partial<PartnerData>;
  is_partner: boolean;
  pending_partner_application: boolean;
  trial_used: boolean;
  join_date: string;
  web_id: number | null;
  is_admin: boolean;
  has_pending_payment: boolean;
  web_auth_method?: string | null;
  is_mate?: boolean;
  is_coowner?: boolean;
  coowner_code?: string;
  mate_balance?: number;
  mate_commission_total?: number;
  mate_status?: string;
  mate_followers?: number;
  mate_avg_reach?: number;
  mate_period_months?: number;
  mate_ref_link_code?: string;
  mate_subscription_id?: string;
  mate_expiry?: string;
  admin_subscription: {
    url: string;
    json_url: string;
  } | null;
  admin_test_subscription: {
    sub_id: string;
    expiry: string;
    url: string;
    json_url: string;
  } | null;
  partner_subscription: {
    sub_id: string;
    expiry: string;
    url: string;
    json_url: string;
    used_gb?: number;
    traffic_gb?: number;
  } | null;
  has_password: boolean;
  bbanned?: boolean;
  ban_reason?: string;
}

export interface SubscriptionData {
  status: string;
  plan_id?: string;
  plan_text?: string;
  traffic_gb?: number;
  extra_sub_gb?: number;
  ip_limit?: number;
  vpn_url?: string;
  plan_servers?: string[];
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

export interface CreateSubscriptionRequest {
  user_id?: number;
  plan_id: string;
  plan_name?: string;
  price_rub?: number;
  ip_limit?: number;
  traffic_gb?: number;
  servers?: string[];
  duration_days?: number;
}

export interface ExtendSubscriptionRequest {
  user_id: number;
  days: number;
}

export interface SubscriptionlinkResponse {
  subscription_id: string;
  vpn_url: string;
  json_vpn_url: string;
  plan_text: string;
  traffic_gb: number;
  ip_limit: number;
  plan_servers: string[];
}

export interface SubscriptionPaymentRequest {
  message: string;
  payment_id: string;
  plan_id: string;
  plan_name: string;
  amount: number;
  original_amount_rub: number;
  discount_percent: number;
  wait_admin: true;
}

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
  tariff_mode?: "old" | "new";
}

export interface ReferralStatsResponse {
  ref_code: string;
  ref_link: string;
  total_refs: number;
  paid_refs: number;
  unpaid_refs: number;
  conversion_rate: number;
  bonus_days_per_paid: number;
}

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
  ref_link: string;
}

export interface PartnerApplyRequest {
  followers: number;
  social_links: string;
  nickname: string;
  period_months: number;
  bonus_type: string;
  bonus_value: number;
}

export interface CoOwnerProfileResponse {
  uid: number;
  nickname: string;
  telegram_id: number;
  ref_code: string;
  telegram_link: string;
  web_link: string;
  subscription_id: string;
  vpn_url: string;
  expiry: string;
  commission_percent: number;
}

export interface CoOwnerLinkResponse {
  ref_code: string;
  telegram_link: string;
  web_link: string;
}

export interface CoOwnerUser {
  user_id: number;
  telegram_id: number;
  join_date: string;
  username: string;
  has_subscription: boolean;
  subscription_id: string;
  vpn_url: string;
  expiry_sub_datatime: string;
  ref_by: number;
}

export interface CoOwnerUsersResponse {
  users: CoOwnerUser[];
  total: number;
}

export interface CoOwnerPayment {
  payment_id: string;
  uid: number;
  amount: number;
  status: string;
  method: string;
  timestamp: string;
  commission: number;
}

export interface CoOwnerPaymentsResponse {
  payments: CoOwnerPayment[];
  total: number;
  commission: number;
}

export interface CoOwnerStatsResponse {
  total_invited: number;
  active_subscriptions: number;
  paid_users: number;
  revenue: number;
  commission: number;
  commission_percent: number;
  max_depth: number;
  traffic_gb: number;
  newest_join_date: string;
}

export interface PartnerApplyResponse {
  message: string;
  app_id: number;
  operation_id: number | null;
}

export interface PartnerRenewRequest {
  months: number;
}

export interface PartnerRenewResponse {
  message: string;
  operation_id: number;
  months: number;
  amount: number;
}

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
  traffic_chost: number;
  ip_chost: number;
  locations_chost: number;
}

export interface CustomTariffPlan {
  id: string;
  name: string;
  price_rub: number;
  ip_limit: number;
  traffic_gb: number;
  duration_days: number;
  servers: string[];
  active: boolean;
}

export interface CustomTariffGenerateResponse {
  plan: CustomTariffPlan;
  total_price: number;
  formatted_name: string;
  price_rub: number;
}

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

export interface AdminHealthResponse {
  status: string;
  users: {
    total: number;
    bbanned: number;
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

export type PaymentMethod = "card" | "yoomoney" | "manual";

export interface CreateCheckoutRequest {
  plan_id: string;
  method?: PaymentMethod;
  custom_plan?: {
    name?: string;
    price_rub?: number;
    traffic_gb: number;
    ip_limit: number;
    duration_days: number;
    servers?: string[];
  };
}

export interface CheckoutPaymentDetails {
  card_number?: string;
}

export interface TestSubscriptionResponse {
  message: string;
  plan_name: string;
  payment_id: string;
  wait_admin: boolean;
  url?: string;
  json_url?: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  payment_id: string;
  payment_method: PaymentMethod;
  amount_rub: number;
  original_amount_rub: number;
  discount_percent: number;
  payment_details?: CheckoutPaymentDetails | null;
}

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

export interface BroadcastRequest {
  type: string;
  message: string;
}

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

export interface UserListItem {
  user_id: number;
  telegram_id: number;
  username: string;
  join_date: string;
  subscription_id: string;
  vpn_url: string;
  plan_text: string;
  expiry_sub_datatime: string;
  ref_by: number;
  co_owner_ref_by: number;
  is_coowner: number;
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

export interface StatsOverviewResponse {
  total_users: number;
  active_subscriptions: number;
  banned_users: number;
}

export interface PanelStatusResponse {
  panel: {
    panel_version: string;
    xray_version: string;
    panel_base?: string;
  };
  server_status: Record<string, unknown>;
  nodes: Record<string, unknown>[];
}

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

export interface FeaturesResponse {
  payment_methods: PaymentMethod[];
  panel_types: {
    main: boolean;
    json: boolean;
  };
  features: {
    tariff_mode?: "old" | "new";
    custom_tariff: boolean;
    partner: boolean;
    partner_new_auto_mode: boolean;
    trust_score: boolean;
    telegram_login: boolean;
    main_panel: boolean;
    json_panel: boolean;
    card_payment: boolean;
    yoomoney_payment: boolean;
  };
  public_links: Record<string, string>;
}

export interface PartnerChannel {
  channel_id: number;
  title: string;
  username: string;
  is_owner_verified: number;
  has_posting_rights: number;
  is_active: number;
  added_at: string;
  last_checked_at: string;
  last_status: string;
  last_error: string;
}

export interface PartnerChannelList {
  channels: PartnerChannel[];
  count: number;
}

export interface PartnerChannelAddRequest {
  channel_id: number;
}

export interface PartnerChannelVerifyResult {
  count: number;
  total: number;
}

export interface AutopostRequest {
  text: string;
}

export interface AutopostResult {
  sent: number;
  failed: number;
  total: number;
}

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
