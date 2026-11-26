/**
 * Account authentication, OTP verification, tiered Admin RBAC & encrypted cloud sync client for 镜信 (MirrorBrief).
 */

import { resolveDataUrl } from './dataBase'
import { t } from './i18n'

export type UserRole = 'super_admin' | 'admin' | 'user'

export function isAdminRole(role?: string | null): boolean {
  return role === 'admin' || role === 'super_admin'
}

export interface AuthUser {
  id: number
  member_number?: number
  username: string
  display_name: string
  email: string
  phone: string
  email_digest_enabled?: boolean
  avatar?: string
  role: UserRole
  is_active: boolean
  created_at: string
  last_login_at: string | null
  login_count: number
  extra_qa_quota?: number
  invited_by_code?: string
}

export interface AuthSession {
  token: string
  user: AuthUser
  referral_bonus_granted?: number
}

export interface CloudSyncCounts {
  watchlist: number
  bookmarks: number
  read_later: number
  notes: number
  predictions: number
  muted: number
}

const AUTH_STORAGE_KEY = 'insight_auth_session_v1'
const DEVICE_ID_STORAGE_KEY = 'mirrorbrief_device_id_v1'

export function getOrCreateDeviceId(): string {
  if (typeof window === 'undefined') return 'ssr-device'
  try {
    let id = window.localStorage.getItem(DEVICE_ID_STORAGE_KEY)
    if (!id || id.length < 10) {
      const rand =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID().replace(/-/g, '')
          : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`
      const screenTag = `${window.screen?.width || 0}x${window.screen?.height || 0}`
      id = `mb_${screenTag}_${rand}`.slice(0, 64)
      window.localStorage.setItem(DEVICE_ID_STORAGE_KEY, id)
    }
    return id
  } catch {
    return `mb_ephemeral_${Date.now().toString(36)}`
  }
}

export function getApiBase(): string {
  const custom = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE
  if (custom && custom.trim()) return custom.trim().replace(/\/+$/, '')
  if (typeof window !== 'undefined') {
    const dir = window.location.pathname.replace(/\/[^/]*$/, '').replace(/\/+$/, '')
    return dir
  }
  return ''
}

export function loadAuthSession(): AuthSession | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AuthSession>
    if (typeof parsed.token === 'string' && parsed.token && parsed.user && typeof parsed.user.username === 'string') {
      return parsed as AuthSession
    }
    return null
  } catch {
    return null
  }
}

export function saveAuthSession(session: AuthSession): void {
  try {
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
  } catch {
    // Ignore storage quota errors
  }
}

export function clearAuthSession(): void {
  try {
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
  } catch {
    // Ignore
  }
}

export class ApiValidationError extends Error {
  fieldErrors: Record<string, string>
  constructor(message: string, fieldErrors: Record<string, string> = {}) {
    super(message)
    this.name = 'ApiValidationError'
    this.fieldErrors = fieldErrors
  }
}

function normalizeValidationFieldMsg(field: string, rawMsg: string): string {
  if (/[\u4e00-\u9fa5]/.test(rawMsg)) return rawMsg
  if (field === 'username') {
    return t(
      '用户名需 4~20 位，只能用字母、数字、下划线或中文',
      'Username must be 4–20 characters (letters, numbers, underscore, or CJK)',
    )
  }
  if (field === 'password' || field === 'new_password') {
    return t(
      '密码至少 8 位（最长 64 位），需同时包含字母和数字',
      'Password must be 8–64 chars including both letters and digits',
    )
  }
  if (field === 'email' || field === 'phone' || field === 'target' || field === 'contact') {
    return t('请输入有效的手机号或电子邮箱', 'Please enter a valid email or phone number')
  }
  return t('请检查输入格式是否正确', 'Please check the input format')
}

async function apiRequest<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Device-ID': getOrCreateDeviceId(),
    ...((init.headers as Record<string, string>) || {}),
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const resp = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers,
  })
  const text = await resp.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!resp.ok) {
    const rawDetail = data && typeof data === 'object' && 'detail' in data ? (data as { detail?: unknown }).detail : null
    if (Array.isArray(rawDetail)) {
      const fieldErrors: Record<string, string> = {}
      const msgs: string[] = []
      for (const item of rawDetail) {
        if (!item || typeof item !== 'object') continue
        const loc = Array.isArray((item as { loc?: unknown }).loc) ? ((item as { loc: unknown[] }).loc) : []
        const field = String(loc[loc.length - 1] || 'form')
        const rawMsg = typeof (item as { msg?: unknown }).msg === 'string' ? (item as { msg: string }).msg : ''
        const friendly = normalizeValidationFieldMsg(field, rawMsg)
        fieldErrors[field] = friendly
        if (!msgs.includes(friendly)) msgs.push(friendly)
      }
      throw new ApiValidationError(
        msgs[0] || t('请检查表单输入格式是否正确', 'Please check your form entries'),
        fieldErrors,
      )
    }
    if (resp.status === 401 && token) {
      clearAuthSession()
    }
    const msg =
      (typeof rawDetail === 'string' && rawDetail.trim() ? rawDetail : null) ||
      (resp.status === 422
        ? t('请检查输入内容格式是否正确', 'Invalid input format')
        : t(`请求失败 (HTTP ${resp.status})`, `Request failed (HTTP ${resp.status})`))
    throw new Error(msg)
  }
  return data as T
}

export async function apiSendCode(
  target: string,
  purpose: 'register' | 'bind' | 'reset_password',
): Promise<{ ok: boolean; sent: boolean; channel: string; message: string; dev_code?: string }> {
  return apiRequest('/api/auth/send-code', {
    method: 'POST',
    body: JSON.stringify({ target, purpose }),
  })
}

export async function apiRegister(
  username: string,
  password: string,
  displayName = '',
  opts: { email?: string; phone?: string; code?: string; invite_code?: string } = {},
): Promise<AuthSession> {
  return apiRequest<AuthSession>('/api/auth/register', {
    method: 'POST',
    headers: {
      'X-Device-ID': getOrCreateDeviceId(),
    },
    body: JSON.stringify({
      username,
      password,
      display_name: displayName,
      email: opts.email || '',
      phone: opts.phone || '',
      code: opts.code || '',
      invite_code: opts.invite_code || '',
    }),
  })
}

export async function apiLogin(username: string, password: string): Promise<AuthSession> {
  return apiRequest<AuthSession>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function apiBindContact(
  token: string,
  target: string,
  code: string,
): Promise<{ ok: boolean; user: AuthUser }> {
  return apiRequest(
    '/api/auth/bind-contact',
    {
      method: 'POST',
      body: JSON.stringify({ target, code }),
    },
    token,
  )
}

export async function apiResetPassword(
  target: string,
  code: string,
  newPassword: string,
): Promise<{ ok: boolean; token: string; user: AuthUser }> {
  return apiRequest('/api/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ target, code, new_password: newPassword }),
  })
}

export async function apiFetchMe(token: string): Promise<{
  user: AuthUser
  prediction_bonus_qa_quota?: number
  sync_summary: { has_cloud_state: boolean; updated_at: string | null; counts: CloudSyncCounts | null }
}> {
  return apiRequest('/api/auth/me', { method: 'GET' }, token)
}

export async function apiUpdatePreferences(
  token: string,
  prefs: { email_digest_enabled: boolean },
): Promise<{ ok: boolean; user: AuthUser }> {
  return apiRequest(
    '/api/auth/preferences',
    {
      method: 'PATCH',
      body: JSON.stringify(prefs),
    },
    token,
  )
}

export async function apiChangePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; token: string; user: AuthUser }> {
  return apiRequest(
    '/api/auth/password',
    {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    },
    token,
  )
}

export async function apiPullCloudState(token: string): Promise<{
  has_state: boolean
  state: Record<string, unknown> | null
  updated_at: string | null
  counts: CloudSyncCounts | null
}> {
  return apiRequest('/api/user/state', { method: 'GET' }, token)
}

export async function apiPushCloudState(
  token: string,
  state: Record<string, unknown>,
): Promise<{ ok: boolean; updated_at: string; counts: CloudSyncCounts }> {
  return apiRequest(
    '/api/user/state',
    {
      method: 'PUT',
      body: JSON.stringify({ state }),
    },
    token,
  )
}

export async function apiSubmitFeedback(
  payload: {
    content: string
    contact?: string
    category?: string
    page_url?: string
  },
  token?: string | null,
): Promise<{ ok: boolean; id?: number; status?: string; created_at?: string }> {
  return apiRequest(
    '/api/feedback',
    {
      method: 'POST',
      headers: {
        'X-Device-ID': getOrCreateDeviceId(),
      },
      body: JSON.stringify(payload),
    },
    token || undefined,
  )
}

export interface FeedbackRecordItem {
  id: number
  user_id?: number | null
  username?: string
  device_id?: string
  contact?: string
  category: string
  content: string
  page_url?: string
  ip?: string
  status: 'pending' | 'adopted' | 'replied' | 'ignored' | string
  admin_reply?: string
  replied_by?: string
  replied_at?: string
  created_at: string
}

export async function apiFetchMyFeedback(token?: string | null): Promise<{ items: FeedbackRecordItem[] }> {
  try {
    return await apiRequest<{ items: FeedbackRecordItem[] }>(
      '/api/feedback/mine',
      {
        method: 'GET',
        headers: {
          'X-Device-ID': getOrCreateDeviceId(),
        },
      },
      token || undefined,
    )
  } catch {
    return { items: [] }
  }
}

export async function apiFetchPublicOverrides(): Promise<import('./overrides').EditorialOverridesDoc | null> {
  try {
    return await apiRequest<import('./overrides').EditorialOverridesDoc>('/api/public/overrides', { method: 'GET' })
  } catch {
    try {
      const res = await fetch(resolveDataUrl('data/editorial_overrides.json', true), { cache: 'no-store' })
      if (!res.ok) return null
      return (await res.json()) as import('./overrides').EditorialOverridesDoc
    } catch {
      return null
    }
  }
}

export async function apiFetchPredictionCrowd(token?: string | null): Promise<{
  min_votes: number
  items: Record<
    string,
    {
      prediction_id: string
      vote_count: number
      min_votes: number
      unlocked: boolean
      crowd_avg_pct: number | null
      bull_votes: number | null
      bear_votes: number | null
      user_prob_pct: number | null
    }
  >
}> {
  return apiRequest('/api/predictions/crowd', { method: 'GET' }, token)
}

export async function apiSubmitPredictionVote(
  token: string,
  predictionId: string,
  probPct: number,
  opts: { reason_tag?: string; challenger_ref?: string } = {},
): Promise<{
  ok: boolean
  min_votes: number
  early_multiplier?: number
  reason_tag?: string
  items: Record<string, any>
  item?: any
}> {
  return apiRequest(
    `/api/predictions/${encodeURIComponent(predictionId)}/vote`,
    {
      method: 'PUT',
      body: JSON.stringify({
        prob_pct: probPct,
        reason_tag: opts.reason_tag || '',
        challenger_ref: opts.challenger_ref || '',
      }),
    },
    token,
  )
}

export interface DailyPredictionRow {
  id: string
  source_type: string
  category: string
  title: string
  question: string
  win_rule: string
  lose_rule: string
  ticker: string
  base_price: number | null
  target_price: number | null
  ai_prob_pct: number
  created_at: string
  lock_at: string
  due_at: string
  status: 'open' | 'locked' | 'settled' | string
  outcome: 'yes' | 'no' | 'void' | null
  settled_value: number | null
  settled_at: string | null
  proposer_user_id: number | null
  proposer_username: string
}

export interface PredictionProposalRow {
  id: number
  user_id: number
  username: string
  category: string
  title: string
  question: string
  win_rule: string
  lose_rule: string
  due_at: string
  status: 'pending' | 'approved' | 'rejected' | string
  published_prediction_id: string
  created_at: string
  reviewed_at: string
}

export interface UserPredictionProfile {
  user_id: number
  season_key: string
  insight_points: number
  settled_count: number
  hit_count: number
  hit_rate_pct: number | null
  avg_brier: number | null
  current_streak: number
  best_streak: number
  rank_tier: string
  bonus_qa_quota: number
  bonus_qa_expires_at: string
  unlocked_referral_bonus: number
}

export interface ArenaLeaderboardRow {
  rank: number
  user_id: number
  username: string
  display_name: string
  avatar: string
  insight_points: number
  settled_count: number
  hit_count: number
  hit_rate_pct: number | null
  avg_brier: number | null
  current_streak: number
  best_streak: number
  rank_tier: string
}

export interface PredictionArenaResponse {
  season_key: string
  daily_predictions: DailyPredictionRow[]
  public_predictions: Array<Record<string, unknown>>
  crowd_stats: Record<string, import('./types').CrowdPredictionStat>
  min_votes: number
  my_profile: UserPredictionProfile | null
  leaderboard: ArenaLeaderboardRow[]
  allowed_reason_tags: string[]
  server_time: string
}

export async function apiFetchPredictionArena(token?: string | null): Promise<PredictionArenaResponse> {
  return apiRequest('/api/predictions/arena', { method: 'GET' }, token)
}

export async function apiSubmitPredictionProposal(
  token: string,
  body: {
    category: string
    title: string
    question: string
    win_rule?: string
    lose_rule?: string
    due_at: string
  },
): Promise<{ ok: boolean; proposal: PredictionProposalRow }> {
  return apiRequest(
    '/api/predictions/proposals',
    { method: 'POST', body: JSON.stringify(body) },
    token,
  )
}

export async function apiFetchMyPredictionProposals(
  token: string,
): Promise<{ items: PredictionProposalRow[] }> {
  return apiRequest('/api/predictions/proposals/mine', { method: 'GET' }, token)
}

// ---------------- Admin APIs (Level-1 super_admin & Level-2 admin) ----------------

export interface AdminUserRow {
  id: number
  username: string
  display_name: string
  email: string
  phone: string
  avatar?: string
  password_plain: string | null
  role: UserRole
  is_active: number
  created_at: string
  last_login_at: string | null
  last_login_ip: string | null
  login_count: number
  has_saved_password?: boolean
  watchlist_count: number | null
  bookmarks_count: number | null
  read_later_count: number | null
  notes_count: number | null
  predictions_count: number | null
  muted_count: number | null
  payload_bytes: number | null
  state_updated_at: string | null
}

export interface AdminOverviewResponse {
  admin: AuthUser
  stats: {
    total_users: number
    super_admin_count?: number
    sub_admin_count?: number
    active_accounts: number
    active_24h: number
    active_7d: number
    synced_users: number
    sync_snapshots_total?: number
    pending_feedback_count?: number
    total_feedback_count?: number
    total_watchlist_items: number
    total_bookmarks: number
    total_read_later: number
    total_notes: number
    total_predictions: number
    encrypted_storage_bytes: number
    db_file_bytes: number
    push_ok_count: number
    push_error_count: number
    online_real_total?: number
    online_real_logged_in?: number
    online_real_guest?: number
    today_total_visits?: number
    today_unique_ips?: number
  }
  data_status: {
    smart_batch_id?: string
    smart_generated_at?: string
    raw_summary?: Record<string, unknown>
    v3?: Record<string, unknown>
  }
  server_time: string
}

export interface AdminPushConfig {
  enabled: boolean
  site_url: string
  feishu_webhook: string
  wecom_webhook: string
  dingtalk_webhook: string
  serverchan_sendkey: string
  telegram_bot_token: string
  telegram_chat_id: string
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_pass: string
  smtp_to: string
  sms_webhook_url?: string
}

export async function apiAdminOverview(token: string): Promise<AdminOverviewResponse> {
  return apiRequest('/api/admin/overview', { method: 'GET' }, token)
}

export async function apiAdminUsers(token: string): Promise<{ users: AdminUserRow[] }> {
  return apiRequest('/api/admin/users', { method: 'GET' }, token)
}

export async function apiAdminCreateUser(
  token: string,
  body: {
    username: string
    password: string
    display_name?: string
    email?: string
    phone?: string
    role: UserRole
  },
): Promise<{ ok: boolean; user: AuthUser }> {
  return apiRequest('/api/admin/users', { method: 'POST', body: JSON.stringify(body) }, token)
}

export async function apiAdminUserData(
  token: string,
  userId: number,
): Promise<{
  user: AuthUser
  has_state: boolean
  updated_at: string | null
  counts: CloudSyncCounts | null
  state: Record<string, unknown> | null
}> {
  return apiRequest(`/api/admin/users/${userId}/data`, { method: 'GET' }, token)
}

export async function apiAdminPatchUser(
  token: string,
  userId: number,
  body: {
    is_active?: boolean
    new_password?: string
    display_name?: string
    email?: string
    phone?: string
    role?: UserRole
  },
): Promise<{ ok: boolean; user: AuthUser }> {
  return apiRequest(
    `/api/admin/users/${userId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
    token,
  )
}

export async function apiAdminAuditLogs(token: string, limit = 100): Promise<{ logs: Record<string, unknown>[] }> {
  return apiRequest(`/api/admin/audit-logs?limit=${limit}`, { method: 'GET' }, token)
}

export async function apiAdminGetPushConfig(token: string): Promise<{ config: AdminPushConfig }> {
  return apiRequest('/api/admin/push-config', { method: 'GET' }, token)
}

export async function apiAdminSavePushConfig(
  token: string,
  config: AdminPushConfig,
): Promise<{ ok: boolean; updated_at: string }> {
  return apiRequest('/api/admin/push-config', { method: 'PUT', body: JSON.stringify(config) }, token)
}

export async function apiAdminPushTest(
  token: string,
): Promise<{ ok: boolean; results: { channel: string; status: string; error?: string }[] }> {
  return apiRequest('/api/admin/push-test', { method: 'POST' }, token)
}

export async function apiAdminPushLogs(token: string): Promise<{ logs: Record<string, unknown>[] }> {
  return apiRequest('/api/admin/push-logs', { method: 'GET' }, token)
}

export async function apiAdminSyncNow(
  token: string,
): Promise<{
  ok: boolean
  base: string
  updated: number
  failed: string[]
  skipped_same_batch?: string
  smart_batch_id?: string
  raw_batch_id?: string
  forced?: boolean
  wire_updated_at?: string
  wire_total?: number
  quotes_count?: number
}> {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
  const timer = controller ? setTimeout(() => controller.abort(), 20_000) : null
  try {
    return await apiRequest(
      '/api/admin/sync-now',
      controller ? { method: 'POST', signal: controller.signal } : { method: 'POST' },
      token,
    )
  } catch (err) {
    if (err instanceof Error && (err.name === 'AbortError' || /aborted/i.test(err.message))) {
      throw new Error('同步云端数据超时（20秒），后台仍在拉取，请稍后点击「刷新面板」查看')
    }
    throw err
  } finally {
    if (timer !== null) clearTimeout(timer)
  }
}

export type SiteAccessMode = 'private_gate' | 'invite_only' | 'public'
export type GrowthStage =
  | 'stage_1_cold_start'
  | 'stage_2_soft_invite'
  | 'stage_3_scarcity_invite'
  | 'stage_4_elite_circle'

export interface PublicSiteSettings {
  monitor_public: boolean
  access_mode?: SiteAccessMode
  invite_required?: boolean
  login_required?: boolean
  feedback_enabled?: boolean
  feedback_notice?: string
  feedback_contact_wechat?: string
  feedback_contact_email?: string
  feedback_contact_group?: string
  feedback_contact_qr_url?: string
  feedback_daily_limit?: number
  site_banner_enabled?: boolean
  site_banner_text?: string
  site_banner_tone?: 'info' | 'warning' | 'important' | string
  growth_stage?: GrowthStage
  welcome_hero_enabled?: boolean
  soft_auth_prompts_enabled?: boolean
  guest_qa_daily_limit?: number
  auth_qa_daily_limit?: number
  crowd_vote_min_unlock?: number
  user_referral_enabled?: boolean
  user_invite_quota?: number
  referral_bonus_qa_quota?: number
  invite_waitlist_enabled?: boolean
  prediction_daily_market_enabled?: boolean
  prediction_rewards_enabled?: boolean
  prediction_proposals_enabled?: boolean
  weekly_digest_enabled?: boolean
  weekly_digest_day?: number
  weekly_digest_hour?: number
  weekly_digest_minute?: number
  online_counter_enabled?: boolean
  online_counter_mode?: 'real' | 'simulated'
  online_real_scope?: 'all' | 'logged_in' | 'guest'
  online_sim_base?: number
  online_sim_delta?: number
  online_sim_interval_sec?: number
  online_counter_label?: string
}

export async function apiGetPublicSettings(): Promise<PublicSiteSettings> {
  try {
    return await apiRequest<PublicSiteSettings>('/api/public/settings', { method: 'GET' })
  } catch {
    return {
      monitor_public: false,
      access_mode: 'public',
      invite_required: false,
      login_required: false,
      feedback_enabled: true,
      feedback_notice: '欢迎反馈页面问题、数据纠错或功能建议，镜信编辑团队将尽快查阅并回复。',
      feedback_daily_limit: 5,
      growth_stage: 'stage_1_cold_start',
      welcome_hero_enabled: true,
      soft_auth_prompts_enabled: true,
      guest_qa_daily_limit: 5,
      auth_qa_daily_limit: 30,
      crowd_vote_min_unlock: 3,
      user_referral_enabled: false,
      user_invite_quota: 3,
      referral_bonus_qa_quota: 15,
      invite_waitlist_enabled: false,
      prediction_daily_market_enabled: true,
      prediction_rewards_enabled: true,
      prediction_proposals_enabled: true,
      weekly_digest_enabled: true,
      weekly_digest_day: 0,
      weekly_digest_hour: 18,
      weekly_digest_minute: 0,
      online_counter_enabled: true,
      online_counter_label: '在线',
    }
  }
}

export async function apiAdminGetSiteSettings(token: string): Promise<PublicSiteSettings> {
  return apiRequest<PublicSiteSettings>('/api/admin/site-settings', { method: 'GET' }, token)
}

export async function apiAdminSaveSiteSettings(
  token: string,
  settings: Partial<PublicSiteSettings>,
): Promise<PublicSiteSettings & { ok: boolean; updated_at: string }> {
  return apiRequest('/api/admin/site-settings', { method: 'PUT', body: JSON.stringify(settings) }, token)
}

export async function apiAdminRevealUserPassword(
  token: string,
  userId: number,
  adminPassword: string,
): Promise<{ ok: boolean; password_plain: string | null }> {
  return apiRequest(
    `/api/admin/users/${userId}/reveal-password`,
    { method: 'POST', body: JSON.stringify({ admin_password: adminPassword }) },
    token,
  )
}

export async function apiAdminFeedbackList(
  token: string,
  status = '',
): Promise<{ items: FeedbackRecordItem[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiRequest(`/api/admin/feedback${qs}`, { method: 'GET' }, token)
}

export async function apiAdminUpdateFeedback(
  token: string,
  feedbackId: number,
  body: { status?: string; admin_reply?: string },
): Promise<{ ok: boolean; item: FeedbackRecordItem }> {
  return apiRequest(
    `/api/admin/feedback/${feedbackId}`,
    { method: 'PATCH', body: JSON.stringify(body) },
    token,
  )
}

export async function apiAdminDeleteFeedback(
  token: string,
  feedbackId: number,
): Promise<{ ok: boolean }> {
  return apiRequest(`/api/admin/feedback/${feedbackId}`, { method: 'DELETE' }, token)
}

export interface AdminContentEventRow {
  event_id: string
  title: string
  title_fingerprint: string
  category: string
  severity_tier: 'S' | 'A' | 'B' | string
  heavy_reason_tag?: string | null
  importance: string
  published_at?: string | null
  source_count: number
}

export interface AdminContentWireRow {
  id: string
  title: string
  title_fingerprint: string
  category: string
  severity_tier: 'S' | 'A' | 'B' | string
  heavy_reason_tag?: string | null
  importance: string
  source_name: string
  published_at?: string | null
}

export async function apiAdminContentList(token: string): Promise<{
  events: AdminContentEventRow[]
  wire: AdminContentWireRow[]
  overrides: import('./overrides').EditorialOverridesDoc
}> {
  return apiRequest('/api/admin/content', { method: 'GET' }, token)
}

export async function apiAdminSaveEditorialOverride(
  token: string,
  body: {
    key: string
    target_type: 'event' | 'wire'
    event_id?: string
    title: string
    title_fingerprint?: string
    severity_override?: 'S' | 'A' | 'B' | null
    heavy_reason_tag?: string | null
    pinned?: boolean
    hidden?: boolean
  },
): Promise<{ ok: boolean; overrides: import('./overrides').EditorialOverridesDoc }> {
  return apiRequest('/api/admin/editorial-overrides', { method: 'PUT', body: JSON.stringify(body) }, token)
}

export async function apiAdminDeleteEditorialOverride(
  token: string,
  key: string,
): Promise<{ ok: boolean; overrides: import('./overrides').EditorialOverridesDoc }> {
  return apiRequest(`/api/admin/editorial-overrides/${encodeURIComponent(key)}`, { method: 'DELETE' }, token)
}

export interface AdminInviteCodeRow {
  id: number
  code: string
  note: string
  created_by: string
  created_at: string
  expires_at: string
  used_by_user_id: number | null
  used_by_username: string
  used_at: string
  revoked: number
}

export async function apiAdminInviteCodes(token: string, limit = 100): Promise<{ items: AdminInviteCodeRow[] }> {
  return apiRequest(`/api/admin/invite-codes?limit=${limit}`, { method: 'GET' }, token)
}

export async function apiAdminCreateInviteCodes(
  token: string,
  body: { count?: number; note?: string; expires_days?: number | null },
): Promise<{ ok: boolean; items: AdminInviteCodeRow[] }> {
  return apiRequest('/api/admin/invite-codes', { method: 'POST', body: JSON.stringify(body) }, token)
}

export async function apiAdminRevokeInviteCode(token: string, code: string): Promise<{ ok: boolean }> {
  return apiRequest(`/api/admin/invite-codes/${encodeURIComponent(code)}`, { method: 'DELETE' }, token)
}

// ---------------- User Referral Invites, Waitlist & Structured Reactions ----------------

export interface MyInvitesResponse {
  enabled: boolean
  member_number: number
  quota: number
  generated_count: number
  remaining_quota: number
  invited_count: number
  bonus_qa_quota: number
  extra_qa_quota?: number
  items: AdminInviteCodeRow[]
}

export async function apiFetchMyInvites(token: string): Promise<MyInvitesResponse> {
  return apiRequest('/api/auth/my-invites', { method: 'GET' }, token)
}

export async function apiCreateMyInvite(token: string): Promise<MyInvitesResponse & { ok: boolean; item: AdminInviteCodeRow | null }> {
  return apiRequest('/api/auth/my-invites', { method: 'POST' }, token)
}

export interface WaitlistEntryRow {
  id: number
  contact: string
  focus_areas: string
  note: string
  status: 'pending' | 'approved' | 'rejected' | string
  assigned_code: string
  ip: string
  created_at: string
  reviewed_at: string
}

export async function apiSubmitWaitlist(body: {
  contact: string
  focus_areas: string | string[]
  note?: string
}): Promise<{ ok: boolean; id: number; status: string }> {
  return apiRequest('/api/public/waitlist', {
    method: 'POST',
    headers: { 'X-Device-ID': getOrCreateDeviceId() },
    body: JSON.stringify(body),
  })
}

export async function apiAdminListWaitlist(
  token: string,
  status = '',
): Promise<{ items: WaitlistEntryRow[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiRequest(`/api/admin/waitlist${qs}`, { method: 'GET' }, token)
}

export async function apiAdminApproveWaitlist(
  token: string,
  id: number,
): Promise<{ ok: boolean; item: WaitlistEntryRow; code: string }> {
  return apiRequest(`/api/admin/waitlist/${id}/approve`, { method: 'POST' }, token)
}

export async function apiAdminRejectWaitlist(
  token: string,
  id: number,
): Promise<{ ok: boolean; item: WaitlistEntryRow }> {
  return apiRequest(`/api/admin/waitlist/${id}/reject`, { method: 'POST' }, token)
}

export async function apiAdminListPredictionProposals(
  token: string,
  status = '',
): Promise<{ items: PredictionProposalRow[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiRequest(`/api/admin/predictions/proposals${qs}`, { method: 'GET' }, token)
}

export async function apiAdminApprovePredictionProposal(
  token: string,
  id: number,
): Promise<{ ok: boolean; proposal: PredictionProposalRow; prediction: DailyPredictionRow | null; already_approved?: boolean }> {
  return apiRequest(`/api/admin/predictions/proposals/${id}/approve`, { method: 'POST' }, token)
}

export async function apiAdminRejectPredictionProposal(
  token: string,
  id: number,
): Promise<{ ok: boolean; proposal: PredictionProposalRow }> {
  return apiRequest(`/api/admin/predictions/proposals/${id}/reject`, { method: 'POST' }, token)
}

export async function apiAdminListDailyPredictions(
  token: string,
): Promise<{ items: DailyPredictionRow[] }> {
  return apiRequest('/api/admin/predictions/daily', { method: 'GET' }, token)
}

export async function apiAdminSettleDailyPrediction(
  token: string,
  predictionId: string,
  body: { outcome: 'yes' | 'no' | 'void'; settled_value?: number | null },
): Promise<{ ok: boolean; already_settled?: boolean; settled_votes: number; outcome: string }> {
  return apiRequest(
    `/api/admin/predictions/${encodeURIComponent(predictionId)}/settle`,
    { method: 'POST', body: JSON.stringify(body) },
    token,
  )
}

export async function apiAdminRunDailyPredictionCron(
  token: string,
): Promise<{ ok: boolean; generated: number; locked: number; settled: number }> {
  return apiRequest('/api/admin/predictions/run-daily-cron', { method: 'POST' }, token)
}

export type ReactionTargetType = 'event' | 'finance' | 'prediction'

export interface ReactionSummary {
  target_type: ReactionTargetType
  target_id: string
  counts: Record<string, number>
  total: number
  my_reaction: string | null
}

export async function apiFetchReactionsBatch(
  targetType: ReactionTargetType,
  ids: string[],
  token?: string | null,
): Promise<{ target_type: ReactionTargetType; items: Record<string, ReactionSummary> }> {
  const cleanIds = Array.from(new Set(ids.map((s) => s.trim()).filter(Boolean))).slice(0, 100)
  if (cleanIds.length === 0) {
    return { target_type: targetType, items: {} }
  }
  const qs = `target_type=${encodeURIComponent(targetType)}&ids=${encodeURIComponent(cleanIds.join(','))}`
  return apiRequest(
    `/api/reactions/batch?${qs}`,
    {
      method: 'GET',
      headers: { 'X-Device-ID': getOrCreateDeviceId() },
    },
    token || undefined,
  )
}

export async function apiSubmitReaction(
  body: { target_type: ReactionTargetType; target_id: string; reaction_key: string },
  token?: string | null,
): Promise<{ ok: boolean; item: ReactionSummary }> {
  return apiRequest(
    '/api/reactions',
    {
      method: 'POST',
      headers: { 'X-Device-ID': getOrCreateDeviceId() },
      body: JSON.stringify(body),
    },
    token || undefined,
  )
}

// ---------------- Live Online Presence & Admin IP Visit Analytics ----------------

export interface PresencePingResponse {
  ok: boolean
  enabled: boolean
  count: number
  label: string
  mode: 'real' | 'simulated'
  real_scope: 'all' | 'logged_in' | 'guest'
  server_time_ms: number
  poll_interval_sec: number
  sim_drift: {
    base: number
    delta: number
    interval_sec: number
  } | null
}

export interface AdminTrafficHourlyRow {
  hour: number
  label: string
  total_visits: number
  auth_visits: number
  guest_visits: number
  unique_ips: number
}

export interface AdminTrafficIpRow {
  day_cst: string
  ip: string
  country: string
  visit_count: number
  auth_visit_count: number
  guest_visit_count: number
  heartbeat_count: number
  last_user_id: number | null
  last_username: string
  usernames: string[]
  platforms: string[]
  last_tab: string
  first_seen_at: string
  last_seen_at: string
  is_online: boolean
  has_auth: boolean
}

export interface AdminActiveSessionRow {
  session_key: string
  ip: string
  country: string
  user_id: number | null
  username: string
  display_name: string
  is_logged_in: boolean
  platform: 'desktop' | 'mobile' | 'android' | string
  current_tab: string
  last_seen_at: string
}

export interface AdminTrafficResponse {
  day: string
  today_cst: string
  available_days: string[]
  online: {
    real_total: number
    real_logged_in: number
    real_guest: number
    display_count: number
    enabled: boolean
    mode: 'real' | 'simulated'
    real_scope: 'all' | 'logged_in' | 'guest'
    label: string
    sim_base: number
    sim_delta: number
    sim_interval_sec: number
    window_sec: number
  }
  summary: {
    total_visits: number
    auth_visits: number
    guest_visits: number
    unique_ips: number
    auth_ips: number
    guest_only_ips: number
    repeat_ips: number
    total_heartbeats: number
    avg_visits_per_ip: number
    peak_hour: { hour: number; label: string; total_visits: number } | null
  }
  hourly: AdminTrafficHourlyRow[]
  ip_rows: AdminTrafficIpRow[]
  filtered_total: number
  active_sessions: AdminActiveSessionRow[]
  server_time_ms: number
}

export async function apiPresencePing(
  payload: { is_visit?: boolean; platform?: 'desktop' | 'mobile' | 'android'; tab?: string },
  token?: string | null,
): Promise<PresencePingResponse> {
  return apiRequest(
    '/api/presence/ping',
    {
      method: 'POST',
      headers: { 'X-Device-ID': getOrCreateDeviceId() },
      body: JSON.stringify(payload),
    },
    token || undefined,
  )
}

export function apiPresenceLeave(): void {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return
  const url = `${getApiBase()}/api/presence/leave`
  const payload = JSON.stringify({ device_id: getOrCreateDeviceId() })
  try {
    if (typeof navigator.sendBeacon === 'function') {
      const blob = new Blob([payload], { type: 'application/json' })
      navigator.sendBeacon(url, blob)
      return
    }
  } catch {
    // Fallback below
  }
  try {
    void fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Device-ID': getOrCreateDeviceId() },
      body: payload,
      keepalive: true,
    })
  } catch {
    // Ignore unload errors
  }
}

export async function apiAdminTraffic(
  token: string,
  params: { day?: string; filter?: string; sort?: string; q?: string; limit?: number } = {},
): Promise<AdminTrafficResponse> {
  const qs = new URLSearchParams()
  if (params.day) qs.set('day', params.day)
  if (params.filter) qs.set('filter', params.filter)
  if (params.sort) qs.set('sort', params.sort)
  if (params.q) qs.set('q', params.q)
  if (params.limit) qs.set('limit', String(params.limit))
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return apiRequest(`/api/admin/traffic${suffix}`, { method: 'GET' }, token)
}
