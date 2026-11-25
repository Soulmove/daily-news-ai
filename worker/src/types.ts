export type AccessMode = 'private_gate' | 'invite_only' | 'public'
export type UserRole = 'super_admin' | 'admin' | 'user'

export interface Env {
  DB: D1Database
  R2_DATA: R2Bucket
  SITE_ACCESS_MODE?: string
  SITE_PUBLIC_URL?: string
  DATA_PUBLIC_BASE_URL?: string
  ALLOWED_ORIGINS?: string
  GEMINI_MODEL?: string
  JWT_SECRET: string
  DATA_ENCRYPTION_KEY: string
  ADMIN_BOOTSTRAP_USER?: string
  ADMIN_BOOTSTRAP_PASS?: string
  GEMINI_API_KEY?: string
  RESEND_API_KEY?: string
  RESEND_FROM?: string
  SMS_WEBHOOK_URL?: string
}

export interface UserRow {
  id: number
  username: string
  display_name: string
  email: string
  phone: string
  role: UserRole
  password_hash: string
  encrypted_password: string
  is_active: number
  token_version: number
  email_digest_enabled: number
  digest_last_sent_date: string
  avatar: string
  created_at: string
  last_login_at: string | null
  last_login_ip: string | null
  login_count: number
}

export interface PublicUser {
  id: number
  username: string
  display_name: string
  email: string
  phone: string
  email_digest_enabled: boolean
  avatar: string
  role: UserRole
  is_active: boolean
  created_at: string
  last_login_at: string | null
  login_count: number
}

export interface AuthClaims {
  sub: number
  username: string
  role: UserRole
  ver: number
  iat: number
  exp: number
}

export interface CloudSyncCounts {
  watchlist: number
  bookmarks: number
  read_later: number
  notes: number
  predictions: number
  muted: number
}

export interface InviteCodeRow {
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

export interface LiveWireItem {
  id: string
  source_id: string
  source_name: string
  category: string
  title: string
  excerpt: string | null
  url: string
  canonical_url: string
  published_at: string
  fetched_at: string
  importance: string
  severity_tier: string
  heavy_reason_tag: string | null
  metric_label: string | null
  thumbnail_url: string | null
}

export type HonoVariables = {
  user: UserRow | null
  clientIp: string
  deviceId: string
  accessMode: AccessMode
}
