import {
  decryptJson,
  encryptJson,
  generateInviteCode,
  generateOtpCode,
  hashPassword,
  nowShanghaiIso,
  verifyPassword,
} from './crypto'
import type {
  AccessMode,
  CloudSyncCounts,
  Env,
  GrowthStage,
  InviteCodeRow,
  PublicUser,
  UserRole,
  UserRow,
} from './types'

const AVATAR_PRESET_RE = /^preset:[a-z0-9_-]{1,32}$/
const AVATAR_DATA_URL_RE = /^data:image\/(?:webp|jpeg|png);base64,[A-Za-z0-9+/=]+$/

let bootstrapChecked = false

export function resetBootstrapCacheForTests(): void {
  bootstrapChecked = false
}

export function sanitizeAvatarValue(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const val = raw.trim()
  if (!val) return ''
  if (AVATAR_PRESET_RE.test(val)) return val
  if (val.length <= 28_000 && AVATAR_DATA_URL_RE.test(val)) return val
  return ''
}

export function toPublicUser(u: UserRow): PublicUser {
  const uid = Number(u.id)
  return {
    id: uid,
    member_number: uid,
    username: u.username,
    display_name: u.display_name || '',
    email: u.email || '',
    phone: u.phone || '',
    email_digest_enabled: Boolean(u.email_digest_enabled ?? 1),
    avatar: u.avatar || '',
    role: (u.role || 'user') as UserRole,
    is_active: Boolean(u.is_active),
    created_at: u.created_at,
    last_login_at: u.last_login_at ?? null,
    login_count: Number(u.login_count ?? 0),
    extra_qa_quota: Number(u.extra_qa_quota ?? 0),
    invited_by_code: u.invited_by_code || '',
  }
}

export async function ensureBootstrapAdmin(env: Env): Promise<void> {
  if (bootstrapChecked) return
  const adminUser = (env.ADMIN_BOOTSTRAP_USER || 'admin').trim()
  const adminPass = (env.ADMIN_BOOTSTRAP_PASS || '').trim()
  bootstrapChecked = true
  if (!adminPass || !adminUser) return

  const existing = await env.DB.prepare('SELECT id, role FROM users WHERE username = ?1 LIMIT 1')
    .bind(adminUser)
    .first<{ id: number; role: string }>()

  if (existing) {
    if (existing.role !== 'super_admin') {
      await env.DB.prepare("UPDATE users SET role = 'super_admin' WHERE id = ?1").bind(existing.id).run()
    }
    return
  }

  const ts = nowShanghaiIso()
  const pwHash = await hashPassword(adminPass)
  const encPw = await encryptJson({ pw: adminPass }, env.DATA_ENCRYPTION_KEY)
  const res = await env.DB.prepare(
    `INSERT INTO users (
       username, display_name, role, password_hash, encrypted_password,
       is_active, token_version, created_at
     ) VALUES (?1, ?2, 'super_admin', ?3, ?4, 1, 1, ?5)`,
  )
    .bind(adminUser, '一级最高管理员', pwHash, encPw, ts)
    .run()

  const uid = Number(res.meta?.last_row_id ?? 0) || null
  await logAudit(env.DB, {
    action: 'admin_seeded',
    userId: uid,
    username: adminUser,
    detail: 'Initial super_admin account seeded on Worker bootstrap',
    ip: '127.0.0.1',
  })
}

export async function logAudit(
  db: D1Database,
  opts: { action: string; userId?: number | null; username?: string | null; detail?: string; ip?: string },
): Promise<void> {
  await db
    .prepare(
      'INSERT INTO audit_logs (user_id, username, action, detail, ip, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)',
    )
    .bind(
      opts.userId ?? null,
      (opts.username || '').slice(0, 64),
      opts.action.slice(0, 80),
      (opts.detail || '').slice(0, 500),
      (opts.ip || '').slice(0, 64),
      nowShanghaiIso(),
    )
    .run()
}

export async function getUserById(db: D1Database, userId: number): Promise<UserRow | null> {
  return (await db.prepare('SELECT * FROM users WHERE id = ?1 LIMIT 1').bind(userId).first<UserRow>()) ?? null
}

export async function getUserByUsername(db: D1Database, username: string): Promise<UserRow | null> {
  return (
    (await db.prepare('SELECT * FROM users WHERE username = ?1 LIMIT 1').bind(username.trim()).first<UserRow>()) ?? null
  )
}

export async function getUserByContact(db: D1Database, target: string): Promise<UserRow | null> {
  const clean = target.trim()
  if (!clean) return null
  return (
    (await db
      .prepare(
        "SELECT * FROM users WHERE (email != '' AND email = ?1) OR (phone != '' AND phone = ?1) LIMIT 1",
      )
      .bind(clean)
      .first<UserRow>()) ?? null
  )
}

export async function createUser(
  env: Env,
  opts: {
    username: string
    password: string
    displayName?: string
    email?: string
    phone?: string
    role?: UserRole
    ip?: string
  },
): Promise<UserRow> {
  const ts = nowShanghaiIso()
  const pwHash = await hashPassword(opts.password)
  const encPw = await encryptJson({ pw: opts.password }, env.DATA_ENCRYPTION_KEY)
  const role = opts.role || 'user'
  const email = (opts.email || '').trim()
  const phone = (opts.phone || '').trim()

  const inserted = await env.DB.prepare(
    `INSERT INTO users (
       username, display_name, email, phone, role,
       password_hash, encrypted_password, is_active, token_version,
       created_at, last_login_at, last_login_ip, login_count
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 1, 1, ?8, ?8, ?9, 1)
     RETURNING *`,
  )
    .bind(
      opts.username.trim(),
      (opts.displayName || '').trim() || opts.username.trim(),
      email,
      phone,
      role,
      pwHash,
      encPw,
      ts,
      (opts.ip || '').slice(0, 64),
    )
    .first<UserRow>()

  if (!inserted) {
    throw new Error('Failed to create user record')
  }

  await logAudit(env.DB, {
    action: 'register',
    userId: inserted.id,
    username: inserted.username,
    detail: `Registered role=${role} email=${Boolean(email)} phone=${Boolean(phone)}`,
    ip: opts.ip || '',
  })
  return inserted
}

export async function authenticateUser(
  env: Env,
  opts: { username: string; password: string; ip?: string },
): Promise<UserRow | null> {
  const ident = opts.username.trim()
  const ip = (opts.ip || '').slice(0, 64)
  const row = await env.DB.prepare(
    "SELECT * FROM users WHERE username = ?1 OR (email != '' AND email = ?1) OR (phone != '' AND phone = ?1) LIMIT 1",
  )
    .bind(ident)
    .first<UserRow>()

  if (!row) {
    await logAudit(env.DB, { action: 'login_failed', username: ident, detail: 'User not found', ip })
    return null
  }
  const ok = await verifyPassword(opts.password, row.password_hash)
  if (!ok) {
    await logAudit(env.DB, {
      action: 'login_failed',
      userId: row.id,
      username: row.username,
      detail: 'Wrong password',
      ip,
    })
    return null
  }
  if (!row.is_active) {
    await logAudit(env.DB, {
      action: 'login_blocked',
      userId: row.id,
      username: row.username,
      detail: 'Account disabled',
      ip,
    })
    return null
  }

  const ts = nowShanghaiIso()
  const encPw = await encryptJson({ pw: opts.password }, env.DATA_ENCRYPTION_KEY)
  const updated = await env.DB.prepare(
    'UPDATE users SET last_login_at = ?1, last_login_ip = ?2, login_count = login_count + 1, encrypted_password = ?3 WHERE id = ?4 RETURNING *',
  )
    .bind(ts, ip, encPw, row.id)
    .first<UserRow>()

  await logAudit(env.DB, {
    action: 'login',
    userId: row.id,
    username: row.username,
    detail: 'Login succeeded',
    ip,
  })
  return updated ?? row
}

export async function bindUserContact(
  db: D1Database,
  opts: { userId: number; email?: string; phone?: string; ip?: string },
): Promise<UserRow> {
  if (opts.email !== undefined) {
    const clean = opts.email.trim()
    if (clean) {
      const dup = await db
        .prepare('SELECT id FROM users WHERE email = ?1 AND id != ?2 LIMIT 1')
        .bind(clean, opts.userId)
        .first<{ id: number }>()
      if (dup) throw new Error('该邮箱已被其他账号绑定')
    }
    await db.prepare('UPDATE users SET email = ?1 WHERE id = ?2').bind(clean, opts.userId).run()
  }
  if (opts.phone !== undefined) {
    const clean = opts.phone.trim()
    if (clean) {
      const dup = await db
        .prepare('SELECT id FROM users WHERE phone = ?1 AND id != ?2 LIMIT 1')
        .bind(clean, opts.userId)
        .first<{ id: number }>()
      if (dup) throw new Error('该手机号已被其他账号绑定')
    }
    await db.prepare('UPDATE users SET phone = ?1 WHERE id = ?2').bind(clean, opts.userId).run()
  }
  const user = await getUserById(db, opts.userId)
  if (!user) throw new Error('用户不存在')
  await logAudit(db, {
    action: 'bind_contact',
    userId: opts.userId,
    username: user.username,
    detail: `email=${user.email}, phone=${user.phone}`,
    ip: opts.ip || '',
  })
  return user
}

export async function updateUserPreferences(
  db: D1Database,
  opts: { userId: number; emailDigestEnabled: boolean; ip?: string },
): Promise<UserRow> {
  const updated = await db
    .prepare('UPDATE users SET email_digest_enabled = ?1 WHERE id = ?2 RETURNING *')
    .bind(opts.emailDigestEnabled ? 1 : 0, opts.userId)
    .first<UserRow>()
  if (!updated) throw new Error('用户不存在')
  await logAudit(db, {
    action: 'update_preferences',
    userId: opts.userId,
    username: updated.username,
    detail: `email_digest_enabled=${Boolean(opts.emailDigestEnabled)}`,
    ip: opts.ip || '',
  })
  return updated
}

export async function updatePassword(
  env: Env,
  opts: { userId: number; newPassword: string; actorUsername: string; ip?: string },
): Promise<UserRow> {
  const pwHash = await hashPassword(opts.newPassword)
  const encPw = await encryptJson({ pw: opts.newPassword }, env.DATA_ENCRYPTION_KEY)
  const updated = await env.DB.prepare(
    'UPDATE users SET password_hash = ?1, encrypted_password = ?2, token_version = token_version + 1 WHERE id = ?3 RETURNING *',
  )
    .bind(pwHash, encPw, opts.userId)
    .first<UserRow>()
  if (!updated) throw new Error('用户不存在')
  await logAudit(env.DB, {
    action: 'password_change',
    userId: opts.userId,
    username: opts.actorUsername,
    detail: `Password updated for ${updated.username}`,
    ip: opts.ip || '',
  })
  return updated
}

export async function createVerificationCode(
  db: D1Database,
  opts: { target: string; channel: string; purpose: string; ip?: string },
): Promise<string> {
  const code = generateOtpCode()
  const nowIso = nowShanghaiIso()
  const expIso = nowShanghaiIso(10 * 60_000)
  const target = opts.target.trim()
  await db
    .prepare('UPDATE verification_codes SET used = 1 WHERE target = ?1 AND purpose = ?2 AND used = 0')
    .bind(target, opts.purpose)
    .run()
  await db
    .prepare(
      `INSERT INTO verification_codes (target, channel, purpose, code, expires_at, used, ip, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6, ?7)`,
    )
    .bind(target, opts.channel, opts.purpose, code, expIso, (opts.ip || '').slice(0, 64), nowIso)
    .run()
  return code
}

export async function verifyAndConsumeCode(
  db: D1Database,
  opts: { target: string; purpose: string; code: string },
): Promise<boolean> {
  const tClean = opts.target.trim()
  const cClean = opts.code.trim()
  if (!tClean || !cClean) return false
  const nowIso = nowShanghaiIso()
  const row = await db
    .prepare(
      `SELECT id FROM verification_codes
       WHERE target = ?1 AND purpose = ?2 AND code = ?3 AND used = 0 AND expires_at >= ?4
       ORDER BY id DESC LIMIT 1`,
    )
    .bind(tClean, opts.purpose, cClean, nowIso)
    .first<{ id: number }>()
  if (!row) return false
  await db.prepare('UPDATE verification_codes SET used = 1 WHERE id = ?1').bind(row.id).run()
  return true
}

function countListField(payload: Record<string, unknown>, ...keys: string[]): number {
  for (const k of keys) {
    const val = payload[k]
    if (Array.isArray(val)) return val.length
  }
  return 0
}

export async function saveUserState(
  env: Env,
  opts: { userId: number; payload: Record<string, unknown> },
): Promise<{ updated_at: string; avatar: string; counts: CloudSyncCounts }> {
  const payloadCopy: Record<string, unknown> = { ...opts.payload }
  delete payloadCopy.ai_client_config
  const hasAvatar = 'avatar' in payloadCopy
  const cleanAv = hasAvatar ? sanitizeAvatarValue(payloadCopy.avatar) : ''
  if (hasAvatar) {
    payloadCopy.avatar = cleanAv
  }

  const encrypted = await encryptJson(payloadCopy, env.DATA_ENCRYPTION_KEY)
  const encBytes = new TextEncoder().encode(encrypted).length
  const counts: CloudSyncCounts = {
    watchlist: countListField(payloadCopy, 'watchlist'),
    bookmarks: countListField(payloadCopy, 'bookmarks'),
    read_later: countListField(payloadCopy, 'read_later'),
    notes: countListField(payloadCopy, 'notes', 'research_notes'),
    predictions: countListField(payloadCopy, 'predictions', 'local_predictions'),
    muted: countListField(payloadCopy, 'muted', 'muted_events'),
  }
  const ts = nowShanghaiIso()

  await env.DB.prepare(
    `INSERT INTO user_states (
       user_id, encrypted_payload, watchlist_count, bookmarks_count,
       read_later_count, notes_count, predictions_count, muted_count,
       payload_bytes, updated_at
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)
     ON CONFLICT(user_id) DO UPDATE SET
       encrypted_payload = excluded.encrypted_payload,
       watchlist_count = excluded.watchlist_count,
       bookmarks_count = excluded.bookmarks_count,
       read_later_count = excluded.read_later_count,
       notes_count = excluded.notes_count,
       predictions_count = excluded.predictions_count,
       muted_count = excluded.muted_count,
       payload_bytes = excluded.payload_bytes,
       updated_at = excluded.updated_at`,
  )
    .bind(
      opts.userId,
      encrypted,
      counts.watchlist,
      counts.bookmarks,
      counts.read_later,
      counts.notes,
      counts.predictions,
      counts.muted,
      encBytes,
      ts,
    )
    .run()

  if (hasAvatar) {
    await env.DB.prepare('UPDATE users SET avatar = ?1 WHERE id = ?2').bind(cleanAv, opts.userId).run()
  }

  return { updated_at: ts, avatar: cleanAv, counts }
}

export async function getUserState(
  env: Env,
  userId: number,
): Promise<{
  state: Record<string, unknown>
  updated_at: string
  payload_bytes: number
  counts: CloudSyncCounts
} | null> {
  const row = await env.DB.prepare('SELECT * FROM user_states WHERE user_id = ?1 LIMIT 1')
    .bind(userId)
    .first<{
      encrypted_payload: string
      updated_at: string
      payload_bytes: number
      watchlist_count: number
      bookmarks_count: number
      read_later_count: number
      notes_count: number
      predictions_count: number
      muted_count: number
    }>()
  if (!row) return null
  const decrypted = await decryptJson<Record<string, unknown>>(
    row.encrypted_payload,
    env.DATA_ENCRYPTION_KEY,
    {},
  )
  return {
    state: decrypted,
    updated_at: row.updated_at,
    payload_bytes: Number(row.payload_bytes ?? 0),
    counts: {
      watchlist: Number(row.watchlist_count ?? 0),
      bookmarks: Number(row.bookmarks_count ?? 0),
      read_later: Number(row.read_later_count ?? 0),
      notes: Number(row.notes_count ?? 0),
      predictions: Number(row.predictions_count ?? 0),
      muted: Number(row.muted_count ?? 0),
    },
  }
}

export async function listUsersWithStats(db: D1Database): Promise<Record<string, unknown>[]> {
  const rows = await db
    .prepare(
      `SELECT
         u.id, u.username, u.display_name, u.email, u.phone, u.avatar, u.role, u.is_active,
         u.encrypted_password,
         u.created_at, u.last_login_at, u.last_login_ip, u.login_count,
         s.watchlist_count, s.bookmarks_count, s.read_later_count,
         s.notes_count, s.predictions_count, s.muted_count,
         s.payload_bytes, s.updated_at AS state_updated_at
       FROM users u
       LEFT JOIN user_states s ON u.id = s.user_id
       ORDER BY
         CASE u.role WHEN 'super_admin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END ASC,
         u.id ASC`,
    )
    .all<Record<string, unknown>>()

  return (rows.results || []).map((r) => {
    const enc = String(r.encrypted_password || '')
    const copy: Record<string, unknown> = { ...r }
    delete copy.encrypted_password
    copy.has_saved_password = Boolean(enc)
    copy.password_plain = null
    return copy
  })
}

export async function getUserPlainPassword(env: Env, userId: number): Promise<string | null> {
  const row = await env.DB.prepare('SELECT encrypted_password FROM users WHERE id = ?1 LIMIT 1')
    .bind(userId)
    .first<{ encrypted_password: string }>()
  if (!row) return null
  if (!row.encrypted_password) return ''
  const obj = await decryptJson<{ pw?: string }>(row.encrypted_password, env.DATA_ENCRYPTION_KEY, {})
  return typeof obj.pw === 'string' ? obj.pw : ''
}

export async function adminUpdateUser(
  env: Env,
  opts: {
    userId: number
    isActive?: boolean
    newPassword?: string
    displayName?: string
    email?: string
    phone?: string
    role?: string
    actorUsername: string
    ip?: string
  },
): Promise<UserRow | null> {
  const existing = await getUserById(env.DB, opts.userId)
  if (!existing) return null

  const sets: string[] = []
  const vals: unknown[] = []
  const details: string[] = []
  let idx = 1

  if (opts.isActive !== undefined) {
    sets.push(`is_active = ?${idx++}`)
    vals.push(opts.isActive ? 1 : 0)
    if (!opts.isActive) {
      sets.push('token_version = token_version + 1')
    }
    details.push(`is_active=${opts.isActive}`)
  }
  if (opts.newPassword) {
    sets.push(`password_hash = ?${idx++}`)
    vals.push(await hashPassword(opts.newPassword))
    sets.push(`encrypted_password = ?${idx++}`)
    vals.push(await encryptJson({ pw: opts.newPassword }, env.DATA_ENCRYPTION_KEY))
    sets.push('token_version = token_version + 1')
    details.push('password_reset')
  }
  if (opts.displayName !== undefined) {
    sets.push(`display_name = ?${idx++}`)
    vals.push(opts.displayName.trim().slice(0, 64))
    details.push('display_name_updated')
  }
  if (opts.email !== undefined) {
    sets.push(`email = ?${idx++}`)
    vals.push(opts.email.trim().slice(0, 120))
    details.push('email_updated')
  }
  if (opts.phone !== undefined) {
    sets.push(`phone = ?${idx++}`)
    vals.push(opts.phone.trim().slice(0, 32))
    details.push('phone_updated')
  }
  if (opts.role && (opts.role === 'user' || opts.role === 'admin' || opts.role === 'super_admin')) {
    sets.push(`role = ?${idx++}`)
    vals.push(opts.role)
    details.push(`role=${opts.role}`)
  }

  if (sets.length === 0) return existing

  vals.push(opts.userId)
  const updated = await env.DB.prepare(
    `UPDATE users SET ${sets.join(', ')} WHERE id = ?${idx} RETURNING *`,
  )
    .bind(...vals)
    .first<UserRow>()

  await logAudit(env.DB, {
    action: 'admin_update_user',
    userId: opts.userId,
    username: opts.actorUsername,
    detail: details.join(', '),
    ip: opts.ip || '',
  })

  return updated ?? existing
}

export async function getAdminStats(db: D1Database): Promise<Record<string, number>> {
  const cutoff24h = nowShanghaiIso(-24 * 3600_000)
  const cutoff7d = nowShanghaiIso(-7 * 86_400_000)

  const [
    totalUsers,
    superAdminCount,
    subAdminCount,
    activeAccounts,
    active24h,
    active7d,
    syncedUsers,
    syncSnapshotsTotal,
    pendingFeedback,
    totalFeedback,
    totalsRow,
    pushOk,
    pushErr,
  ] = await Promise.all([
    db.prepare('SELECT COUNT(*) AS cnt FROM users').first<{ cnt: number }>(),
    db.prepare("SELECT COUNT(*) AS cnt FROM users WHERE role = 'super_admin'").first<{ cnt: number }>(),
    db.prepare("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin'").first<{ cnt: number }>(),
    db.prepare('SELECT COUNT(*) AS cnt FROM users WHERE is_active = 1').first<{ cnt: number }>(),
    db.prepare('SELECT COUNT(*) AS cnt FROM users WHERE last_login_at >= ?1').bind(cutoff24h).first<{ cnt: number }>(),
    db.prepare('SELECT COUNT(*) AS cnt FROM users WHERE last_login_at >= ?1').bind(cutoff7d).first<{ cnt: number }>(),
    db
      .prepare('SELECT COUNT(DISTINCT s.user_id) AS cnt FROM user_states s JOIN users u ON u.id = s.user_id')
      .first<{ cnt: number }>(),
    db.prepare('SELECT COUNT(*) AS cnt FROM user_states').first<{ cnt: number }>(),
    db.prepare("SELECT COUNT(*) AS cnt FROM feedback_messages WHERE status = 'pending'").first<{ cnt: number }>(),
    db.prepare('SELECT COUNT(*) AS cnt FROM feedback_messages').first<{ cnt: number }>(),
    db
      .prepare(
        `SELECT
           COALESCE(SUM(s.watchlist_count), 0) AS wl,
           COALESCE(SUM(s.bookmarks_count), 0) AS bm,
           COALESCE(SUM(s.read_later_count), 0) AS rl,
           COALESCE(SUM(s.notes_count), 0) AS nt,
           COALESCE(SUM(s.predictions_count), 0) AS pr,
           COALESCE(SUM(s.payload_bytes), 0) AS bytes
         FROM user_states s JOIN users u ON u.id = s.user_id`,
      )
      .first<{ wl: number; bm: number; rl: number; nt: number; pr: number; bytes: number }>(),
    db.prepare("SELECT COUNT(*) AS cnt FROM push_logs WHERE status = 'ok'").first<{ cnt: number }>(),
    db.prepare("SELECT COUNT(*) AS cnt FROM push_logs WHERE status != 'ok'").first<{ cnt: number }>(),
  ])

  return {
    total_users: Number(totalUsers?.cnt ?? 0),
    super_admin_count: Number(superAdminCount?.cnt ?? 0),
    sub_admin_count: Number(subAdminCount?.cnt ?? 0),
    active_accounts: Number(activeAccounts?.cnt ?? 0),
    active_24h: Number(active24h?.cnt ?? 0),
    active_7d: Number(active7d?.cnt ?? 0),
    synced_users: Number(syncedUsers?.cnt ?? 0),
    sync_snapshots_total: Number(syncSnapshotsTotal?.cnt ?? 0),
    pending_feedback_count: Number(pendingFeedback?.cnt ?? 0),
    total_feedback_count: Number(totalFeedback?.cnt ?? 0),
    total_watchlist_items: Number(totalsRow?.wl ?? 0),
    total_bookmarks: Number(totalsRow?.bm ?? 0),
    total_read_later: Number(totalsRow?.rl ?? 0),
    total_notes: Number(totalsRow?.nt ?? 0),
    total_predictions: Number(totalsRow?.pr ?? 0),
    encrypted_storage_bytes: Number(totalsRow?.bytes ?? 0),
    db_file_bytes: 0,
    push_ok_count: Number(pushOk?.cnt ?? 0),
    push_error_count: Number(pushErr?.cnt ?? 0),
  }
}

export const GROWTH_STAGE_VALUES: readonly GrowthStage[] = [
  'stage_1_cold_start',
  'stage_2_soft_invite',
  'stage_3_scarcity_invite',
  'stage_4_elite_circle',
]

export const GROWTH_SUPER_ADMIN_KEYS = new Set<string>([
  'access_mode',
  'growth_stage',
  'welcome_hero_enabled',
  'soft_auth_prompts_enabled',
  'guest_qa_daily_limit',
  'auth_qa_daily_limit',
  'crowd_vote_min_unlock',
  'user_referral_enabled',
  'user_invite_quota',
  'referral_bonus_qa_quota',
  'invite_waitlist_enabled',
  'prediction_daily_market_enabled',
  'prediction_rewards_enabled',
  'prediction_proposals_enabled',
  'weekly_digest_enabled',
  'weekly_digest_day',
  'weekly_digest_hour',
  'weekly_digest_minute',
])

export function isValidGrowthStage(raw: unknown): raw is GrowthStage {
  return typeof raw === 'string' && (GROWTH_STAGE_VALUES as readonly string[]).includes(raw)
}

const INT_SETTING_BOUNDS: Record<string, { min: number; max: number; fallback: number }> = {
  feedback_daily_limit: { min: 1, max: 100, fallback: 5 },
  guest_qa_daily_limit: { min: 0, max: 100, fallback: 5 },
  auth_qa_daily_limit: { min: 1, max: 500, fallback: 30 },
  crowd_vote_min_unlock: { min: 1, max: 50, fallback: 3 },
  user_invite_quota: { min: 0, max: 50, fallback: 3 },
  referral_bonus_qa_quota: { min: 0, max: 100, fallback: 15 },
  weekly_digest_day: { min: 0, max: 6, fallback: 0 },
  weekly_digest_hour: { min: 0, max: 23, fallback: 18 },
  weekly_digest_minute: { min: 0, max: 59, fallback: 0 },
}

export function isValidAccessMode(raw: unknown): raw is AccessMode {
  return typeof raw === 'string' && (raw === 'public' || raw === 'invite_only' || raw === 'private_gate')
}

export function resolveAccessMode(raw?: string): AccessMode {
  const clean = (raw || '').trim().toLowerCase()
  if (clean === 'private_gate' || clean === 'invite_only' || clean === 'public') {
    return clean
  }
  return 'invite_only'
}

export async function getEffectiveAccessMode(db: D1Database, envFallback?: string): Promise<AccessMode> {
  const row = await db
    .prepare("SELECT value FROM site_settings WHERE key = 'access_mode' LIMIT 1")
    .first<{ value: string }>()
  const clean = (row?.value || '').trim().toLowerCase()
  if (clean === 'public' || clean === 'invite_only' || clean === 'private_gate') {
    return clean
  }
  return resolveAccessMode(envFallback)
}

export async function getSiteSettings(db: D1Database, envFallback?: string): Promise<Record<string, unknown>> {
  const defaults: Record<string, unknown> = {
    monitor_public: false,
    feedback_enabled: true,
    feedback_notice: '欢迎反馈页面问题、数据纠错或功能建议，镜信团队将尽快查阅并回复。',
    feedback_contact_wechat: '',
    feedback_contact_email: '',
    feedback_contact_group: '',
    feedback_contact_qr_url: '',
    feedback_daily_limit: 5,
    site_banner_enabled: false,
    site_banner_text: '',
    site_banner_tone: 'info',
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
  }
  const boolKeys = new Set([
    'monitor_public',
    'feedback_enabled',
    'site_banner_enabled',
    'welcome_hero_enabled',
    'soft_auth_prompts_enabled',
    'user_referral_enabled',
    'invite_waitlist_enabled',
    'prediction_daily_market_enabled',
    'prediction_rewards_enabled',
    'prediction_proposals_enabled',
    'weekly_digest_enabled',
  ])
  const rows = await db.prepare('SELECT key, value FROM site_settings').all<{ key: string; value: string }>()
  let dbAccessModeRaw = ''
  for (const r of rows.results || []) {
    if (r.key === 'access_mode') {
      dbAccessModeRaw = String(r.value || '')
      continue
    }
    if (!(r.key in defaults)) continue
    if (boolKeys.has(r.key)) {
      defaults[r.key] = ['true', '1', 'yes'].includes(String(r.value).toLowerCase())
    } else if (r.key in INT_SETTING_BOUNDS) {
      const bound = INT_SETTING_BOUNDS[r.key]
      const n = Number(r.value)
      if (Number.isFinite(n)) {
        defaults[r.key] = Math.max(bound.min, Math.min(bound.max, Math.round(n)))
      }
    } else if (r.key === 'growth_stage') {
      const stRaw = String(r.value || '').trim()
      if (isValidGrowthStage(stRaw)) defaults[r.key] = stRaw
    } else {
      defaults[r.key] = String(r.value)
    }
  }
  const normalizedDbMode = dbAccessModeRaw.trim().toLowerCase()
  const accessMode: AccessMode = isValidAccessMode(normalizedDbMode)
    ? normalizedDbMode
    : resolveAccessMode(envFallback)
  return {
    ...defaults,
    access_mode: accessMode,
    invite_required: accessMode !== 'public',
    login_required: accessMode === 'private_gate',
  }
}

export async function saveSiteSettings(
  db: D1Database,
  patch: Record<string, unknown>,
  envFallback?: string,
): Promise<Record<string, unknown>> {
  const ts = nowShanghaiIso()
  const current = await getSiteSettings(db, envFallback)
  const stmts: D1PreparedStatement[] = []

  for (const [k, v] of Object.entries(patch)) {
    if (k === 'invite_required' || k === 'login_required') continue
    if (!(k in current) || v === undefined || v === null) continue
    let serialized = ''
    if (k === 'access_mode') {
      const candidate = typeof v === 'string' ? v.trim() : ''
      if (!isValidAccessMode(candidate)) continue
      serialized = candidate
      current.access_mode = candidate
      current.invite_required = candidate !== 'public'
      current.login_required = candidate === 'private_gate'
    } else if (k === 'growth_stage') {
      const candidate = typeof v === 'string' ? v.trim() : ''
      if (!isValidGrowthStage(candidate)) continue
      serialized = candidate
      current.growth_stage = candidate
    } else if (typeof current[k] === 'boolean') {
      const boolVal =
        typeof v === 'boolean' ? v : ['true', '1', 'yes'].includes(String(v).trim().toLowerCase())
      serialized = boolVal ? 'true' : 'false'
      current[k] = boolVal
    } else if (k in INT_SETTING_BOUNDS) {
      const bound = INT_SETTING_BOUNDS[k]
      const rawNum = Number(v)
      const n = Number.isFinite(rawNum)
        ? Math.max(bound.min, Math.min(bound.max, Math.round(rawNum)))
        : bound.fallback
      serialized = String(n)
      current[k] = n
    } else if (k === 'site_banner_tone') {
      const tone = ['info', 'warning', 'important'].includes(String(v).trim()) ? String(v).trim() : 'info'
      serialized = tone
      current[k] = tone
    } else {
      const s = String(v).trim().slice(0, 500)
      serialized = s
      current[k] = s
    }
    stmts.push(
      db
        .prepare(
          `INSERT INTO site_settings (key, value, updated_at)
           VALUES (?1, ?2, ?3)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at`,
        )
        .bind(k, serialized, ts),
    )
  }

  if (stmts.length > 0) {
    await db.batch(stmts)
  }
  return { ...current, updated_at: ts }
}

// ---------------- Invite Codes (invite_only & private_gate & user referrals) ----------------

export async function createInviteCodes(
  db: D1Database,
  opts: {
    count?: number
    note?: string
    expiresInDays?: number | null
    createdBy: string
    ownerUserId?: number | null
  },
): Promise<InviteCodeRow[]> {
  const count = Math.max(1, Math.min(50, Math.round(opts.count ?? 1)))
  const note = (opts.note || '').trim().slice(0, 120)
  const createdAt = nowShanghaiIso()
  const expiresAt =
    opts.expiresInDays && opts.expiresInDays > 0
      ? nowShanghaiIso(opts.expiresInDays * 86_400_000)
      : ''
  const ownerId = opts.ownerUserId ?? null

  const created: InviteCodeRow[] = []
  for (let i = 0; i < count; i++) {
    const code = generateInviteCode()
    const row = await db
      .prepare(
        `INSERT INTO invite_codes (code, note, created_by, created_at, expires_at, revoked, owner_user_id)
         VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6)
         RETURNING *`,
      )
      .bind(code, note, opts.createdBy.slice(0, 48), createdAt, expiresAt, ownerId)
      .first<InviteCodeRow>()
    if (row) created.push(row)
  }
  return created
}

export async function listUserInviteCodes(db: D1Database, ownerUserId: number): Promise<InviteCodeRow[]> {
  const rows = await db
    .prepare('SELECT * FROM invite_codes WHERE owner_user_id = ?1 ORDER BY id DESC LIMIT 100')
    .bind(ownerUserId)
    .all<InviteCodeRow>()
  return rows.results || []
}

export async function countUserInviteCodes(db: D1Database, ownerUserId: number): Promise<number> {
  const row = await db
    .prepare('SELECT COUNT(*) AS cnt FROM invite_codes WHERE owner_user_id = ?1')
    .bind(ownerUserId)
    .first<{ cnt: number }>()
  return Number(row?.cnt ?? 0)
}

export async function countUserInvitedCount(db: D1Database, ownerUserId: number): Promise<number> {
  const row = await db
    .prepare('SELECT COUNT(*) AS cnt FROM users WHERE invited_by_user_id = ?1')
    .bind(ownerUserId)
    .first<{ cnt: number }>()
  return Number(row?.cnt ?? 0)
}

export async function recordUserReferralAndBonus(
  db: D1Database,
  opts: {
    inviteeUserId: number
    inviterUserId: number | null
    inviteCode: string
    bonusQuota: number
  },
): Promise<void> {
  const bonus = Math.max(0, Math.round(opts.bonusQuota))
  await db
    .prepare(
      `UPDATE users
       SET invited_by_user_id = ?1,
           invited_by_code = ?2,
           extra_qa_quota = COALESCE(extra_qa_quota, 0) + ?3
       WHERE id = ?4`,
    )
    .bind(opts.inviterUserId, opts.inviteCode.trim().toUpperCase().slice(0, 40), bonus, opts.inviteeUserId)
    .run()

  if (opts.inviterUserId !== null && opts.inviterUserId !== opts.inviteeUserId && bonus > 0) {
    await db
      .prepare('UPDATE users SET extra_qa_quota = COALESCE(extra_qa_quota, 0) + ?1 WHERE id = ?2')
      .bind(bonus, opts.inviterUserId)
      .run()
  }
}

export async function listInviteCodes(db: D1Database, limit = 100): Promise<InviteCodeRow[]> {
  const rows = await db
    .prepare('SELECT * FROM invite_codes ORDER BY id DESC LIMIT ?1')
    .bind(Math.max(1, Math.min(200, limit)))
    .all<InviteCodeRow>()
  return rows.results || []
}

export async function validateInviteCode(db: D1Database, rawCode: string): Promise<InviteCodeRow | null> {
  const code = rawCode.trim().toUpperCase()
  if (!code || code.length < 6 || code.length > 40) return null
  const row = await db
    .prepare('SELECT * FROM invite_codes WHERE code = ?1 LIMIT 1')
    .bind(code)
    .first<InviteCodeRow>()
  if (!row) return null
  if (row.revoked || row.used_by_user_id !== null) return null
  if (row.expires_at && row.expires_at < nowShanghaiIso()) return null
  return row
}

export async function consumeInviteCode(
  db: D1Database,
  opts: { codeId: number; userId: number; username: string },
): Promise<boolean> {
  const ts = nowShanghaiIso()
  const res = await db
    .prepare(
      `UPDATE invite_codes
       SET used_by_user_id = ?1, used_by_username = ?2, used_at = ?3
       WHERE id = ?4 AND revoked = 0 AND used_by_user_id IS NULL`,
    )
    .bind(opts.userId, opts.username.slice(0, 48), ts, opts.codeId)
    .run()
  return Number(res.meta?.changes ?? 0) > 0
}

export async function revokeInviteCode(db: D1Database, code: string): Promise<boolean> {
  const clean = code.trim().toUpperCase()
  const res = await db
    .prepare('UPDATE invite_codes SET revoked = 1 WHERE code = ?1 AND used_by_user_id IS NULL')
    .bind(clean)
    .run()
  return Number(res.meta?.changes ?? 0) > 0
}
