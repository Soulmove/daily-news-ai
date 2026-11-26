import { getDefaultEdgeCache } from './quotes'
import type { UserRow } from './types'

export const ONLINE_WINDOW_MS = 120_000
export const PRESENCE_POLL_INTERVAL_SEC = 50
export const PRESENCE_STATUS_CACHE_KEY = 'https://mirrorinfo.xyz/__edge_cache/presence_status_v1'

export async function purgePresenceStatusEdgeCache(): Promise<void> {
  const cache = getDefaultEdgeCache()
  if (!cache) return
  try {
    await cache.delete(new Request(PRESENCE_STATUS_CACHE_KEY))
  } catch {
    // Ignore edge cache deletion failures
  }
}

export type OnlineCounterMode = 'real' | 'simulated'
export type OnlineRealScope = 'all' | 'logged_in' | 'guest'
export type PresencePlatform = 'desktop' | 'mobile' | 'android'

export interface RealOnlineCounts {
  total: number
  logged_in: number
  guest: number
}

export interface OnlineDisplayPayload {
  enabled: boolean
  count: number
  label: string
  mode: OnlineCounterMode
  real_scope: OnlineRealScope
  server_time_ms: number
  poll_interval_sec: number
  sim_drift: {
    base: number
    delta: number
    interval_sec: number
  } | null
}

function shanghaiIsoFromMs(ms: number): string {
  const d = new Date(ms + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}+08:00`
}

function hashSlot(n: number): number {
  let x = (n | 0) + 0x9e3779b9
  x = Math.imul(x ^ (x >>> 16), 0x85ebca6b)
  x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35)
  x = (x ^ (x >>> 16)) >>> 0
  return x / 4294967296
}

/**
 * Deterministic smooth mean-reverting random walk matching web/src/core/presenceStore.ts.
 */
export function computeSimulatedOnlineCount(
  base: number,
  delta: number,
  intervalSec: number,
  nowMs = Date.now(),
): number {
  const cleanBase = Math.max(1, Math.round(Number.isFinite(base) ? base : 68))
  const cleanDelta = Math.max(0, Math.round(Number.isFinite(delta) ? delta : 12))
  const cleanInterval = Math.max(3, Math.min(300, Math.round(Number.isFinite(intervalSec) ? intervalSec : 12)))
  if (cleanDelta === 0) return cleanBase
  const lo = Math.max(1, cleanBase - cleanDelta)
  const hi = Math.max(lo, cleanBase + cleanDelta)
  const slot = Math.floor(nowMs / (cleanInterval * 1000))
  let val = cleanBase
  const maxStep = Math.max(1, Math.min(cleanDelta, Math.ceil(cleanDelta * 0.25)))
  for (let s = slot - 24; s <= slot; s++) {
    const pull = (cleanBase - val) / Math.max(1, cleanDelta)
    const r = hashSlot(s) * 2 - 1 + pull * 0.45
    let step = Math.round(r * maxStep)
    if (step === 0) {
      step = r >= 0 ? 1 : -1
    }
    val = Math.max(lo, Math.min(hi, val + step))
  }
  return val
}

function sanitizePlatform(raw: unknown): PresencePlatform {
  const s = typeof raw === 'string' ? raw.trim().toLowerCase() : ''
  if (s === 'android' || s === 'mobile' || s === 'desktop') return s
  return 'desktop'
}

function sanitizeTab(raw: unknown): string {
  const s = typeof raw === 'string' ? raw.trim().replace(/[^a-zA-Z0-9_-]/g, '') : ''
  return s.slice(0, 32) || 'today'
}

function parseJsonStringArray(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((v) => String(v || '').trim()).filter(Boolean)
  } catch {
    return []
  }
}

function appendUniqueLimited(list: string[], value: string, maxLen: number): string[] {
  const clean = value.trim()
  if (!clean) return list.slice(0, maxLen)
  const next = list.filter((x) => x !== clean)
  next.unshift(clean)
  return next.slice(0, maxLen)
}

export async function getRealOnlineCounts(db: D1Database, nowMs = Date.now()): Promise<RealOnlineCounts> {
  const cutoff = nowMs - ONLINE_WINDOW_MS
  const row = await db
    .prepare(
      `SELECT
         COUNT(*) AS total,
         COALESCE(SUM(CASE WHEN has_auth = 1 THEN 1 ELSE 0 END), 0) AS logged_in,
         COALESCE(SUM(CASE WHEN has_auth = 0 THEN 1 ELSE 0 END), 0) AS guest
       FROM (
         SELECT
           CASE WHEN ip != '' AND ip != 'unknown' THEN 'ip:' || ip ELSE 'sess:' || session_key END AS person_key,
           MAX(CASE WHEN is_logged_in = 1 AND user_id IS NOT NULL THEN 1 ELSE 0 END) AS has_auth
         FROM presence_sessions
         WHERE last_seen_ms >= ?1
         GROUP BY person_key
       )`,
    )
    .bind(cutoff)
    .first<{ total: number; logged_in: number; guest: number }>()
  return {
    total: Number(row?.total ?? 0),
    logged_in: Number(row?.logged_in ?? 0),
    guest: Number(row?.guest ?? 0),
  }
}

export async function recordPresencePing(
  db: D1Database,
  opts: {
    sessionKey: string
    ip: string
    country?: string
    user: UserRow | null
    platform?: string
    tab?: string
    userAgent?: string
    isVisit?: boolean
    nowMs?: number
  },
): Promise<void> {
  const nowMs = typeof opts.nowMs === 'number' && Number.isFinite(opts.nowMs) ? opts.nowMs : Date.now()
  const nowIso = shanghaiIsoFromMs(nowMs)
  const dayCst = nowIso.slice(0, 10)
  const hourCst = Math.max(0, Math.min(23, Number(nowIso.slice(11, 13)) || 0))
  const sessionKey = (opts.sessionKey || 'anon').trim().slice(0, 96) || 'anon'
  const cleanIp = (opts.ip || 'unknown').trim().slice(0, 64) || 'unknown'
  const cleanCountry = (opts.country || '').trim().toUpperCase().slice(0, 8)
  const platform = sanitizePlatform(opts.platform)
  const tab = sanitizeTab(opts.tab)
  const ua = (opts.userAgent || '').trim().slice(0, 200)
  const userId = opts.user ? opts.user.id : null
  const username = opts.user ? (opts.user.username || '').slice(0, 48) : ''
  const displayName = opts.user ? (opts.user.display_name || opts.user.username || '').slice(0, 64) : ''
  const isLoggedIn = opts.user ? 1 : 0

  await db
    .prepare(
      `INSERT INTO presence_sessions (
         session_key, ip, country, user_id, username, display_name, is_logged_in,
         platform, current_tab, user_agent, first_seen_at, last_seen_at, last_seen_ms
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?11, ?12)
       ON CONFLICT(session_key) DO UPDATE SET
         ip = excluded.ip,
         country = CASE WHEN excluded.country != '' THEN excluded.country ELSE presence_sessions.country END,
         user_id = excluded.user_id,
         username = excluded.username,
         display_name = excluded.display_name,
         is_logged_in = excluded.is_logged_in,
         platform = excluded.platform,
         current_tab = excluded.current_tab,
         user_agent = excluded.user_agent,
         last_seen_at = excluded.last_seen_at,
         last_seen_ms = excluded.last_seen_ms`,
    )
    .bind(
      sessionKey,
      cleanIp,
      cleanCountry,
      userId,
      username,
      displayName,
      isLoggedIn,
      platform,
      tab,
      ua,
      nowIso,
      nowMs,
    )
    .run()

  const existingIp = await db
    .prepare('SELECT visit_count, usernames_json, platforms_json FROM daily_ip_visits WHERE day_cst = ?1 AND ip = ?2 LIMIT 1')
    .bind(dayCst, cleanIp)
    .first<{ visit_count: number; usernames_json: string; platforms_json: string }>()

  const prevUsernames = parseJsonStringArray(existingIp?.usernames_json)
  const prevPlatforms = parseJsonStringArray(existingIp?.platforms_json)
  const effectiveIsVisit = Boolean(opts.isVisit) || !existingIp
  const hasNewUsername = Boolean(username && !prevUsernames.includes(username))
  const hasNewPlatform = !prevPlatforms.includes(platform)

  if (effectiveIsVisit || hasNewUsername || hasNewPlatform) {
    const visitInc = effectiveIsVisit ? 1 : 0
    const authVisitInc = effectiveIsVisit && isLoggedIn === 1 ? 1 : 0
    const guestVisitInc = effectiveIsVisit && isLoggedIn === 0 ? 1 : 0

    const usernamesArr = appendUniqueLimited(prevUsernames, username, 12)
    const platformsArr = appendUniqueLimited(prevPlatforms, platform, 6)
    const usernamesJson = JSON.stringify(usernamesArr)
    const platformsJson = JSON.stringify(platformsArr)

    await db
      .prepare(
        `INSERT INTO daily_ip_visits (
           day_cst, ip, country, visit_count, auth_visit_count, guest_visit_count,
           heartbeat_count, last_user_id, last_username, usernames_json, platforms_json,
           last_tab, first_seen_at, last_seen_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, 1, ?7, ?8, ?9, ?10, ?11, ?12, ?12)
         ON CONFLICT(day_cst, ip) DO UPDATE SET
           country = CASE WHEN excluded.country != '' THEN excluded.country ELSE daily_ip_visits.country END,
           visit_count = daily_ip_visits.visit_count + ?4,
           auth_visit_count = daily_ip_visits.auth_visit_count + ?5,
           guest_visit_count = daily_ip_visits.guest_visit_count + ?6,
           heartbeat_count = daily_ip_visits.heartbeat_count + 1,
           last_user_id = COALESCE(excluded.last_user_id, daily_ip_visits.last_user_id),
           last_username = CASE WHEN excluded.last_username != '' THEN excluded.last_username ELSE daily_ip_visits.last_username END,
           usernames_json = excluded.usernames_json,
           platforms_json = excluded.platforms_json,
           last_tab = excluded.last_tab,
           last_seen_at = excluded.last_seen_at`,
      )
      .bind(
        dayCst,
        cleanIp,
        cleanCountry,
        visitInc,
        authVisitInc,
        guestVisitInc,
        userId,
        username,
        usernamesJson,
        platformsJson,
        tab,
        nowIso,
      )
      .run()
  }

  if (effectiveIsVisit) {
    await Promise.all([
      db
        .prepare(
          `INSERT INTO hourly_visit_stats (day_cst, hour_cst, total_visits, auth_visits, guest_visits)
           VALUES (?1, ?2, 1, ?3, ?4)
           ON CONFLICT(day_cst, hour_cst) DO UPDATE SET
             total_visits = hourly_visit_stats.total_visits + 1,
             auth_visits = hourly_visit_stats.auth_visits + excluded.auth_visits,
             guest_visits = hourly_visit_stats.guest_visits + excluded.guest_visits`,
        )
        .bind(dayCst, hourCst, isLoggedIn === 1 ? 1 : 0, isLoggedIn === 0 ? 1 : 0)
        .run(),
      db
        .prepare('INSERT OR IGNORE INTO hourly_ip_seen (day_cst, hour_cst, ip) VALUES (?1, ?2, ?3)')
        .bind(dayCst, hourCst, cleanIp)
        .run(),
    ])
  }
}

export async function markPresenceLeave(db: D1Database, sessionKey: string): Promise<void> {
  const clean = (sessionKey || '').trim().slice(0, 96)
  if (!clean) return
  await db.prepare('DELETE FROM presence_sessions WHERE session_key = ?1').bind(clean).run()
}

export function resolveOnlineDisplay(
  settings: Record<string, unknown>,
  realCounts: RealOnlineCounts,
  nowMs = Date.now(),
): OnlineDisplayPayload {
  const enabled = settings.online_counter_enabled !== false
  const modeRaw = typeof settings.online_counter_mode === 'string' ? settings.online_counter_mode.trim() : ''
  const mode: OnlineCounterMode = modeRaw === 'simulated' ? 'simulated' : 'real'
  const scopeRaw = typeof settings.online_real_scope === 'string' ? settings.online_real_scope.trim() : ''
  const realScope: OnlineRealScope =
    scopeRaw === 'logged_in' || scopeRaw === 'guest' || scopeRaw === 'all' ? scopeRaw : 'all'
  const base = Number(settings.online_sim_base ?? 68)
  const delta = Number(settings.online_sim_delta ?? 12)
  const intervalSec = Number(settings.online_sim_interval_sec ?? 12)
  const label =
    typeof settings.online_counter_label === 'string' && settings.online_counter_label.trim()
      ? settings.online_counter_label.trim().slice(0, 16)
      : '在线'

  let count = realCounts.total
  if (mode === 'simulated') {
    count = computeSimulatedOnlineCount(base, delta, intervalSec, nowMs)
  } else if (realScope === 'logged_in') {
    count = realCounts.logged_in
  } else if (realScope === 'guest') {
    count = realCounts.guest
  }

  return {
    enabled,
    count,
    label,
    mode,
    real_scope: realScope,
    server_time_ms: nowMs,
    poll_interval_sec: PRESENCE_POLL_INTERVAL_SEC,
    sim_drift:
      mode === 'simulated'
        ? {
            base: Math.max(1, Math.round(Number.isFinite(base) ? base : 68)),
            delta: Math.max(0, Math.round(Number.isFinite(delta) ? delta : 12)),
            interval_sec: Math.max(3, Math.min(300, Math.round(Number.isFinite(intervalSec) ? intervalSec : 12))),
          }
        : null,
  }
}

export async function getAdminTrafficReport(
  db: D1Database,
  settings: Record<string, unknown>,
  opts: {
    day?: string
    filter?: string
    sort?: string
    q?: string
    limit?: number
    nowMs?: number
  } = {},
) {
  const nowMs = typeof opts.nowMs === 'number' && Number.isFinite(opts.nowMs) ? opts.nowMs : Date.now()
  const todayCst = shanghaiIsoFromMs(nowMs).slice(0, 10)
  const reqDay = typeof opts.day === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(opts.day.trim()) ? opts.day.trim() : todayCst
  const filter = opts.filter === 'auth' || opts.filter === 'guest' || opts.filter === 'online' ? opts.filter : 'all'
  const sort = opts.sort === 'recent' ? 'recent' : 'visits'
  const q = (opts.q || '').trim().toLowerCase()
  const limit = Math.max(1, Math.min(300, Math.round(opts.limit ?? 100)))
  const cutoff = nowMs - ONLINE_WINDOW_MS

  const [realCounts, activeSessionsRes, daysRes, aggRow, hourlyStatsRes, hourlyIpRes, allDayIpRes] = await Promise.all([
    getRealOnlineCounts(db, nowMs),
    db
      .prepare(
        `SELECT session_key, ip, country, user_id, username, display_name, is_logged_in, platform, current_tab, last_seen_at, last_seen_ms
         FROM presence_sessions
         WHERE last_seen_ms >= ?1
         ORDER BY last_seen_ms DESC
         LIMIT 80`,
      )
      .bind(cutoff)
      .all<{
        session_key: string
        ip: string
        country: string
        user_id: number | null
        username: string
        display_name: string
        is_logged_in: number
        platform: string
        current_tab: string
        last_seen_at: string
        last_seen_ms: number
      }>(),
    db.prepare('SELECT DISTINCT day_cst FROM daily_ip_visits ORDER BY day_cst DESC LIMIT 14').all<{ day_cst: string }>(),
    db
      .prepare(
        `SELECT
           COALESCE(SUM(visit_count), 0) AS total_visits,
           COALESCE(SUM(auth_visit_count), 0) AS auth_visits,
           COALESCE(SUM(guest_visit_count), 0) AS guest_visits,
           COUNT(*) AS unique_ips,
           COALESCE(SUM(CASE WHEN auth_visit_count > 0 OR (usernames_json != '[]' AND usernames_json != '') THEN 1 ELSE 0 END), 0) AS auth_ips,
           COALESCE(SUM(CASE WHEN auth_visit_count = 0 AND (usernames_json = '[]' OR usernames_json = '') THEN 1 ELSE 0 END), 0) AS guest_only_ips,
           COALESCE(SUM(CASE WHEN visit_count >= 2 THEN 1 ELSE 0 END), 0) AS repeat_ips,
           COALESCE(SUM(heartbeat_count), 0) AS total_heartbeats
         FROM daily_ip_visits
         WHERE day_cst = ?1`,
      )
      .bind(reqDay)
      .first<{
        total_visits: number
        auth_visits: number
        guest_visits: number
        unique_ips: number
        auth_ips: number
        guest_only_ips: number
        repeat_ips: number
        total_heartbeats: number
      }>(),
    db
      .prepare('SELECT hour_cst, total_visits, auth_visits, guest_visits FROM hourly_visit_stats WHERE day_cst = ?1')
      .bind(reqDay)
      .all<{ hour_cst: number; total_visits: number; auth_visits: number; guest_visits: number }>(),
    db
      .prepare('SELECT hour_cst, COUNT(*) AS unique_ips FROM hourly_ip_seen WHERE day_cst = ?1 GROUP BY hour_cst')
      .bind(reqDay)
      .all<{ hour_cst: number; unique_ips: number }>(),
    db
      .prepare(
        sort === 'recent'
          ? `SELECT * FROM daily_ip_visits WHERE day_cst = ?1 ORDER BY last_seen_at DESC, visit_count DESC LIMIT 500`
          : `SELECT * FROM daily_ip_visits WHERE day_cst = ?1 ORDER BY visit_count DESC, last_seen_at DESC LIMIT 500`,
      )
      .bind(reqDay)
      .all<{
        day_cst: string
        ip: string
        country: string
        visit_count: number
        auth_visit_count: number
        guest_visit_count: number
        heartbeat_count: number
        last_user_id: number | null
        last_username: string
        usernames_json: string
        platforms_json: string
        last_tab: string
        first_seen_at: string
        last_seen_at: string
      }>(),
  ])

  const display = resolveOnlineDisplay(settings, realCounts, nowMs)
  const activeSessions = activeSessionsRes.results || []
  const onlineIpSet = new Set(activeSessions.map((s) => s.ip).filter(Boolean))

  const availableDaysSet = new Set<string>([todayCst])
  for (const r of daysRes.results || []) {
    if (r.day_cst) availableDaysSet.add(r.day_cst)
  }
  const availableDays = Array.from(availableDaysSet).sort((a, b) => b.localeCompare(a))

  const statsMap = new Map<number, { total: number; auth: number; guest: number }>()
  for (const h of hourlyStatsRes.results || []) {
    statsMap.set(Number(h.hour_cst), {
      total: Number(h.total_visits ?? 0),
      auth: Number(h.auth_visits ?? 0),
      guest: Number(h.guest_visits ?? 0),
    })
  }
  const ipHourMap = new Map<number, number>()
  for (const h of hourlyIpRes.results || []) {
    ipHourMap.set(Number(h.hour_cst), Number(h.unique_ips ?? 0))
  }
  const hourly = Array.from({ length: 24 }, (_, hour) => {
    const st = statsMap.get(hour)
    return {
      hour,
      label: `${String(hour).padStart(2, '0')}:00`,
      total_visits: st?.total ?? 0,
      auth_visits: st?.auth ?? 0,
      guest_visits: st?.guest ?? 0,
      unique_ips: ipHourMap.get(hour) ?? 0,
    }
  })

  let peakHour: { hour: number; label: string; total_visits: number } | null = null
  for (const h of hourly) {
    if (h.total_visits > 0 && (!peakHour || h.total_visits > peakHour.total_visits)) {
      peakHour = { hour: h.hour, label: h.label, total_visits: h.total_visits }
    }
  }

  const parsedRows = (allDayIpRes.results || []).map((r) => {
    const usernames = parseJsonStringArray(r.usernames_json)
    const platforms = parseJsonStringArray(r.platforms_json)
    const isAuth = Number(r.auth_visit_count ?? 0) > 0 || usernames.length > 0
    return {
      day_cst: r.day_cst,
      ip: r.ip,
      country: r.country || '',
      visit_count: Number(r.visit_count ?? 0),
      auth_visit_count: Number(r.auth_visit_count ?? 0),
      guest_visit_count: Number(r.guest_visit_count ?? 0),
      heartbeat_count: Number(r.heartbeat_count ?? 0),
      last_user_id: r.last_user_id ?? null,
      last_username: r.last_username || '',
      usernames,
      platforms,
      last_tab: r.last_tab || 'today',
      first_seen_at: r.first_seen_at,
      last_seen_at: r.last_seen_at,
      is_online: onlineIpSet.has(r.ip),
      has_auth: isAuth,
    }
  })

  const filtered = parsedRows.filter((row) => {
    if (filter === 'auth' && !row.has_auth) return false
    if (filter === 'guest' && row.has_auth) return false
    if (filter === 'online' && !row.is_online) return false
    if (q) {
      const hay = `${row.ip} ${row.country} ${row.last_username} ${row.usernames.join(' ')} ${row.last_tab}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })

  const totalVisits = Number(aggRow?.total_visits ?? 0)
  const uniqueIps = Number(aggRow?.unique_ips ?? 0)

  return {
    day: reqDay,
    today_cst: todayCst,
    available_days: availableDays,
    online: {
      real_total: realCounts.total,
      real_logged_in: realCounts.logged_in,
      real_guest: realCounts.guest,
      display_count: display.count,
      enabled: display.enabled,
      mode: display.mode,
      real_scope: display.real_scope,
      label: display.label,
      sim_base: Number(settings.online_sim_base ?? 68),
      sim_delta: Number(settings.online_sim_delta ?? 12),
      sim_interval_sec: Number(settings.online_sim_interval_sec ?? 12),
      window_sec: Math.round(ONLINE_WINDOW_MS / 1000),
    },
    summary: {
      total_visits: totalVisits,
      auth_visits: Number(aggRow?.auth_visits ?? 0),
      guest_visits: Number(aggRow?.guest_visits ?? 0),
      unique_ips: uniqueIps,
      auth_ips: Number(aggRow?.auth_ips ?? 0),
      guest_only_ips: Number(aggRow?.guest_only_ips ?? 0),
      repeat_ips: Number(aggRow?.repeat_ips ?? 0),
      total_heartbeats: Number(aggRow?.total_heartbeats ?? 0),
      avg_visits_per_ip: uniqueIps > 0 ? Number((totalVisits / uniqueIps).toFixed(2)) : 0,
      peak_hour: peakHour,
    },
    hourly,
    ip_rows: filtered.slice(0, limit),
    filtered_total: filtered.length,
    active_sessions: activeSessions.map((s) => ({
      session_key: s.session_key,
      ip: s.ip,
      country: s.country || '',
      user_id: s.user_id ?? null,
      username: s.username || '',
      display_name: s.display_name || '',
      is_logged_in: Boolean(s.is_logged_in),
      platform: s.platform || 'desktop',
      current_tab: s.current_tab || 'today',
      last_seen_at: s.last_seen_at,
    })),
    server_time_ms: nowMs,
  }
}

export async function cleanupOldPresenceAndTraffic(db: D1Database, nowMs = Date.now()): Promise<void> {
  const staleSessionCutoffMs = nowMs - 86_400_000
  const cutoffDay = shanghaiIsoFromMs(nowMs - 45 * 86_400_000).slice(0, 10)
  await Promise.all([
    db.prepare('DELETE FROM presence_sessions WHERE last_seen_ms < ?1').bind(staleSessionCutoffMs).run(),
    db.prepare('DELETE FROM daily_ip_visits WHERE day_cst < ?1').bind(cutoffDay).run(),
    db.prepare('DELETE FROM hourly_visit_stats WHERE day_cst < ?1').bind(cutoffDay).run(),
    db.prepare('DELETE FROM hourly_ip_seen WHERE day_cst < ?1').bind(cutoffDay).run(),
  ])
}
