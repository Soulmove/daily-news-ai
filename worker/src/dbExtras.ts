import { decryptJson, encryptJson, nowShanghaiIso } from './crypto'
import type { Env } from './types'

// ---------------- Audit & Push Logs / Push Config ----------------

export async function listAuditLogs(db: D1Database, limit = 100): Promise<Record<string, unknown>[]> {
  const safeLimit = Math.max(1, Math.min(500, Math.round(limit)))
  const rows = await db
    .prepare('SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?1')
    .bind(safeLimit)
    .all<Record<string, unknown>>()
  return rows.results || []
}

export async function getPushConfig(env: Env, configId = 'global'): Promise<Record<string, unknown>> {
  const defaults: Record<string, unknown> = {
    enabled: false,
    site_url: env.SITE_PUBLIC_URL || 'https://mirrorinfo.xyz',
    feishu_webhook: '',
    wecom_webhook: '',
    dingtalk_webhook: '',
    serverchan_sendkey: '',
    telegram_bot_token: '',
    telegram_chat_id: '',
    smtp_host: '',
    smtp_port: 465,
    smtp_user: '',
    smtp_pass: '',
    smtp_to: '',
    sms_webhook_url: '',
  }
  const row = await env.DB.prepare('SELECT encrypted_config FROM push_configs WHERE id = ?1 LIMIT 1')
    .bind(configId)
    .first<{ encrypted_config: string }>()
  if (!row || !row.encrypted_config) return defaults
  const cfg = await decryptJson<Record<string, unknown>>(row.encrypted_config, env.DATA_ENCRYPTION_KEY, {})
  if (!cfg || typeof cfg !== 'object') return defaults
  return { ...defaults, ...cfg }
}

export async function savePushConfig(
  env: Env,
  config: Record<string, unknown>,
  configId = 'global',
): Promise<string> {
  const encrypted = await encryptJson(config, env.DATA_ENCRYPTION_KEY)
  const ts = nowShanghaiIso()
  await env.DB.prepare(
    `INSERT INTO push_configs (id, encrypted_config, updated_at)
     VALUES (?1, ?2, ?3)
     ON CONFLICT(id) DO UPDATE SET
       encrypted_config = excluded.encrypted_config,
       updated_at = excluded.updated_at`,
  )
    .bind(configId, encrypted, ts)
    .run()
  return ts
}

export async function logPush(
  db: D1Database,
  opts: { channel: string; status: string; batchId: string; summary?: string; errorMsg?: string },
): Promise<void> {
  await db
    .prepare(
      'INSERT INTO push_logs (channel, status, batch_id, summary, error_msg, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)',
    )
    .bind(
      opts.channel.slice(0, 64),
      opts.status.slice(0, 32),
      opts.batchId.slice(0, 64),
      (opts.summary || '').slice(0, 300),
      (opts.errorMsg || '').slice(0, 500),
      nowShanghaiIso(),
    )
    .run()
}

export async function listPushLogs(db: D1Database, limit = 50): Promise<Record<string, unknown>[]> {
  const safeLimit = Math.max(1, Math.min(200, Math.round(limit)))
  const rows = await db
    .prepare('SELECT * FROM push_logs ORDER BY id DESC LIMIT ?1')
    .bind(safeLimit)
    .all<Record<string, unknown>>()
  return rows.results || []
}

// ---------------- Feedback Messages ----------------

export async function countRecentFeedback(
  db: D1Database,
  opts: { ip?: string; userId?: number | null; deviceId?: string; hours?: number },
): Promise<number> {
  const cutoff = nowShanghaiIso(-(Math.max(1, opts.hours ?? 24) * 3600_000))
  if (opts.userId !== null && opts.userId !== undefined) {
    const r = await db
      .prepare('SELECT COUNT(*) AS cnt FROM feedback_messages WHERE user_id = ?1 AND created_at >= ?2')
      .bind(opts.userId, cutoff)
      .first<{ cnt: number }>()
    return Number(r?.cnt ?? 0)
  }
  if (opts.deviceId) {
    const r = await db
      .prepare(
        "SELECT COUNT(*) AS cnt FROM feedback_messages WHERE (device_id = ?1 OR (ip = ?2 AND ip != '')) AND created_at >= ?3",
      )
      .bind(opts.deviceId.slice(0, 80), (opts.ip || '').slice(0, 64), cutoff)
      .first<{ cnt: number }>()
    return Number(r?.cnt ?? 0)
  }
  if (opts.ip) {
    const r = await db
      .prepare('SELECT COUNT(*) AS cnt FROM feedback_messages WHERE ip = ?1 AND created_at >= ?2')
      .bind(opts.ip.slice(0, 64), cutoff)
      .first<{ cnt: number }>()
    return Number(r?.cnt ?? 0)
  }
  return 0
}

export async function saveFeedback(
  db: D1Database,
  opts: {
    content: string
    contact?: string
    category?: string
    pageUrl?: string
    ip?: string
    userId?: number | null
    username?: string
    deviceId?: string
  },
): Promise<{ id: number; status: string; created_at: string }> {
  const ts = nowShanghaiIso()
  const row = await db
    .prepare(
      `INSERT INTO feedback_messages (
         user_id, username, device_id, contact, category, content, page_url, ip, status, created_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'pending', ?9)
       RETURNING id`,
    )
    .bind(
      opts.userId ?? null,
      (opts.username || '').slice(0, 48),
      (opts.deviceId || '').slice(0, 80),
      (opts.contact || '').slice(0, 160),
      (opts.category || 'suggestion').slice(0, 48),
      opts.content.slice(0, 4000),
      (opts.pageUrl || '').slice(0, 400),
      (opts.ip || '').slice(0, 64),
      ts,
    )
    .first<{ id: number }>()
  return { id: Number(row?.id ?? 0), status: 'pending', created_at: ts }
}

export async function listFeedback(
  db: D1Database,
  opts: { limit?: number; statusFilter?: string } = {},
): Promise<Record<string, unknown>[]> {
  const safeLimit = Math.max(1, Math.min(300, Math.round(opts.limit ?? 150)))
  const st = (opts.statusFilter || '').trim()
  if (st && ['pending', 'adopted', 'replied', 'ignored'].includes(st)) {
    const rows = await db
      .prepare('SELECT * FROM feedback_messages WHERE status = ?1 ORDER BY id DESC LIMIT ?2')
      .bind(st, safeLimit)
      .all<Record<string, unknown>>()
    return rows.results || []
  }
  const rows = await db
    .prepare('SELECT * FROM feedback_messages ORDER BY id DESC LIMIT ?1')
    .bind(safeLimit)
    .all<Record<string, unknown>>()
  return rows.results || []
}

export async function listUserFeedback(
  db: D1Database,
  opts: { userId?: number | null; deviceId?: string; limit?: number },
): Promise<Record<string, unknown>[]> {
  const safeLimit = Math.max(1, Math.min(100, Math.round(opts.limit ?? 30)))
  const uid = opts.userId ?? null
  const dev = (opts.deviceId || '').slice(0, 80)

  if (uid !== null && dev) {
    const rows = await db
      .prepare(
        `SELECT id, category, contact, content, status, admin_reply, replied_by, replied_at, created_at
         FROM feedback_messages WHERE user_id = ?1 OR device_id = ?2 ORDER BY id DESC LIMIT ?3`,
      )
      .bind(uid, dev, safeLimit)
      .all<Record<string, unknown>>()
    return rows.results || []
  }
  if (uid !== null) {
    const rows = await db
      .prepare(
        `SELECT id, category, contact, content, status, admin_reply, replied_by, replied_at, created_at
         FROM feedback_messages WHERE user_id = ?1 ORDER BY id DESC LIMIT ?2`,
      )
      .bind(uid, safeLimit)
      .all<Record<string, unknown>>()
    return rows.results || []
  }
  if (dev) {
    const rows = await db
      .prepare(
        `SELECT id, category, contact, content, status, admin_reply, replied_by, replied_at, created_at
         FROM feedback_messages WHERE device_id = ?1 ORDER BY id DESC LIMIT ?2`,
      )
      .bind(dev, safeLimit)
      .all<Record<string, unknown>>()
    return rows.results || []
  }
  return []
}

export async function updateFeedback(
  db: D1Database,
  opts: { feedbackId: number; status?: string | null; adminReply?: string | null; actorUsername?: string },
): Promise<Record<string, unknown> | null> {
  const row = await db
    .prepare('SELECT * FROM feedback_messages WHERE id = ?1 LIMIT 1')
    .bind(opts.feedbackId)
    .first<Record<string, unknown>>()
  if (!row) return null

  let nextStatus = String(row.status || 'pending')
  if (opts.status && ['pending', 'adopted', 'replied', 'ignored'].includes(opts.status)) {
    nextStatus = opts.status
  }
  let nextReply = String(row.admin_reply || '')
  let repliedBy = String(row.replied_by || '')
  let repliedAt = String(row.replied_at || '')

  if (opts.adminReply !== undefined && opts.adminReply !== null) {
    nextReply = opts.adminReply.trim().slice(0, 2000)
    if (nextReply) {
      repliedBy = (opts.actorUsername || repliedBy).slice(0, 48)
      repliedAt = nowShanghaiIso()
      if (!opts.status && nextStatus === 'pending') {
        nextStatus = 'replied'
      }
    }
  }

  return (
    (await db
      .prepare(
        `UPDATE feedback_messages
         SET status = ?1, admin_reply = ?2, replied_by = ?3, replied_at = ?4
         WHERE id = ?5 RETURNING *`,
      )
      .bind(nextStatus, nextReply, repliedBy, repliedAt, opts.feedbackId)
      .first<Record<string, unknown>>()) ?? null
  )
}

export async function deleteFeedback(db: D1Database, feedbackId: number): Promise<boolean> {
  const res = await db.prepare('DELETE FROM feedback_messages WHERE id = ?1').bind(feedbackId).run()
  return Number(res.meta?.changes ?? 0) > 0
}

// ---------------- Prediction Crowd Consensus ----------------

export async function upsertPredictionVote(
  db: D1Database,
  opts: { predictionId: string; userId: number; probPct: number },
): Promise<{ prediction_id: string; user_prob_pct: number; updated_at: string }> {
  const pid = opts.predictionId.trim().slice(0, 120)
  const clamped = Math.round(Math.max(5.0, Math.min(95.0, opts.probPct)) * 10) / 10
  const ts = nowShanghaiIso()
  await db
    .prepare(
      `INSERT INTO prediction_crowd_votes (prediction_id, user_id, prob_pct, updated_at)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(prediction_id, user_id) DO UPDATE SET
         prob_pct = excluded.prob_pct,
         updated_at = excluded.updated_at`,
    )
    .bind(pid, opts.userId, clamped, ts)
    .run()
  return { prediction_id: pid, user_prob_pct: clamped, updated_at: ts }
}

export async function getPredictionCrowdStats(
  db: D1Database,
  opts: { userId?: number | null; minVotes?: number } = {},
): Promise<{ min_votes: number; items: Record<string, Record<string, unknown>> }> {
  const threshold = Math.max(1, Math.round(opts.minVotes ?? 10))
  const agg = await db
    .prepare(
      `SELECT
         prediction_id,
         COUNT(DISTINCT user_id) AS vote_count,
         AVG(prob_pct) AS avg_prob,
         SUM(CASE WHEN prob_pct > 55.0 THEN 1 ELSE 0 END) AS bull_votes,
         SUM(CASE WHEN prob_pct < 45.0 THEN 1 ELSE 0 END) AS bear_votes
       FROM prediction_crowd_votes
       GROUP BY prediction_id`,
    )
    .all<{
      prediction_id: string
      vote_count: number
      avg_prob: number
      bull_votes: number
      bear_votes: number
    }>()

  const userVotes: Record<string, number> = {}
  if (opts.userId !== null && opts.userId !== undefined) {
    const uRows = await db
      .prepare('SELECT prediction_id, prob_pct FROM prediction_crowd_votes WHERE user_id = ?1')
      .bind(opts.userId)
      .all<{ prediction_id: string; prob_pct: number }>()
    for (const r of uRows.results || []) {
      userVotes[r.prediction_id] = Math.round(Number(r.prob_pct) * 10) / 10
    }
  }

  const items: Record<string, Record<string, unknown>> = {}
  for (const r of agg.results || []) {
    const pid = String(r.prediction_id)
    const cnt = Number(r.vote_count ?? 0)
    const unlocked = cnt >= threshold
    items[pid] = {
      prediction_id: pid,
      vote_count: cnt,
      min_votes: threshold,
      unlocked,
      crowd_avg_pct: unlocked ? Math.round(Number(r.avg_prob) * 10) / 10 : null,
      bull_votes: unlocked ? Number(r.bull_votes ?? 0) : null,
      bear_votes: unlocked ? Number(r.bear_votes ?? 0) : null,
      user_prob_pct: pid in userVotes ? userVotes[pid] : null,
    }
  }

  for (const [pid, uProb] of Object.entries(userVotes)) {
    if (!(pid in items)) {
      items[pid] = {
        prediction_id: pid,
        vote_count: 1,
        min_votes: threshold,
        unlocked: threshold <= 1,
        crowd_avg_pct: threshold <= 1 ? uProb : null,
        bull_votes: threshold <= 1 ? (uProb > 55 ? 1 : 0) : null,
        bear_votes: threshold <= 1 ? (uProb < 45 ? 1 : 0) : null,
        user_prob_pct: uProb,
      }
    }
  }

  return { min_votes: threshold, items }
}

// ---------------- Editorial Overrides ----------------

export function titleFingerprint(txt: string): string {
  return (txt || '')
    .toLowerCase()
    .replace(/[\s\-_·:：,，.。!！?？()（）[\]【】'"]+/g, '')
    .slice(0, 40)
}

export async function getEditorialOverridesDoc(
  db: D1Database,
): Promise<{ updated_at: string | null; items: Record<string, Record<string, unknown>> }> {
  const rows = await db
    .prepare('SELECT * FROM editorial_overrides ORDER BY updated_at DESC')
    .all<{
      override_key: string
      target_type: string
      event_id: string
      title: string
      title_fingerprint: string
      severity_override: string | null
      heavy_reason_tag: string | null
      pinned: number
      hidden: number
      updated_by: string
      updated_at: string
    }>()
  const items: Record<string, Record<string, unknown>> = {}
  let latestUpdated: string | null = null
  for (const r of rows.results || []) {
    if (!latestUpdated || r.updated_at > latestUpdated) latestUpdated = r.updated_at
    items[r.override_key] = {
      key: r.override_key,
      target_type: r.target_type,
      event_id: r.event_id,
      title: r.title,
      title_fingerprint: r.title_fingerprint,
      severity_override: r.severity_override,
      heavy_reason_tag: r.heavy_reason_tag,
      pinned: Boolean(r.pinned),
      hidden: Boolean(r.hidden),
      updated_by: r.updated_by,
      updated_at: r.updated_at,
    }
  }
  return { updated_at: latestUpdated, items }
}

export async function upsertEditorialOverride(
  db: D1Database,
  opts: {
    key: string
    targetType: string
    eventId: string
    title: string
    titleFingerprint?: string
    severityOverride?: string | null
    heavyReasonTag?: string | null
    pinned?: boolean
    hidden?: boolean
    updatedBy: string
  },
): Promise<{ updated_at: string | null; items: Record<string, Record<string, unknown>> }> {
  const sevUpper = opts.severityOverride ? opts.severityOverride.toUpperCase() : null
  const sev = sevUpper && ['S', 'A', 'B'].includes(sevUpper) ? sevUpper : null
  const key = opts.key.trim().slice(0, 120)
  const fp = (opts.titleFingerprint?.trim() || titleFingerprint(opts.title)).slice(0, 200)
  const ts = nowShanghaiIso()

  await db
    .prepare(
      `INSERT INTO editorial_overrides (
         override_key, target_type, event_id, title, title_fingerprint,
         severity_override, heavy_reason_tag, pinned, hidden, updated_by, updated_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)
       ON CONFLICT(override_key) DO UPDATE SET
         target_type = excluded.target_type,
         event_id = excluded.event_id,
         title = excluded.title,
         title_fingerprint = excluded.title_fingerprint,
         severity_override = excluded.severity_override,
         heavy_reason_tag = excluded.heavy_reason_tag,
         pinned = excluded.pinned,
         hidden = excluded.hidden,
         updated_by = excluded.updated_by,
         updated_at = excluded.updated_at`,
    )
    .bind(
      key,
      opts.targetType === 'wire' ? 'wire' : 'event',
      opts.eventId.trim().slice(0, 120),
      opts.title.trim().slice(0, 300),
      fp,
      sev,
      opts.heavyReasonTag ? opts.heavyReasonTag.trim().slice(0, 48) : null,
      opts.pinned ? 1 : 0,
      opts.hidden ? 1 : 0,
      opts.updatedBy.slice(0, 48),
      ts,
    )
    .run()

  return getEditorialOverridesDoc(db)
}

export async function deleteEditorialOverride(
  db: D1Database,
  key: string,
): Promise<{ removed: boolean; doc: { updated_at: string | null; items: Record<string, Record<string, unknown>> } }> {
  const res = await db.prepare('DELETE FROM editorial_overrides WHERE override_key = ?1').bind(key).run()
  const doc = await getEditorialOverridesDoc(db)
  return { removed: Number(res.meta?.changes ?? 0) > 0, doc }
}

// ---------------- Invite Waitlist (Stage 3/4 Scarcity Application) ----------------

import type { ReactionSummary, ReactionTargetType, WaitlistRow } from './types'

export async function createWaitlistEntry(
  db: D1Database,
  opts: { contact: string; focusAreas?: string; note?: string; ip?: string },
): Promise<WaitlistRow> {
  const ts = nowShanghaiIso()
  const row = await db
    .prepare(
      `INSERT INTO invite_waitlist (contact, focus_areas, note, status, assigned_code, ip, created_at, reviewed_at)
       VALUES (?1, ?2, ?3, 'pending', '', ?4, ?5, '')
       RETURNING *`,
    )
    .bind(
      opts.contact.trim().slice(0, 160),
      (opts.focusAreas || '').trim().slice(0, 200),
      (opts.note || '').trim().slice(0, 300),
      (opts.ip || '').trim().slice(0, 64),
      ts,
    )
    .first<WaitlistRow>()
  if (!row) {
    throw new Error('Failed to create waitlist record')
  }
  return row
}

export async function listWaitlistEntries(
  db: D1Database,
  opts: { statusFilter?: string; limit?: number } = {},
): Promise<WaitlistRow[]> {
  const lim = Math.max(1, Math.min(200, opts.limit ?? 100))
  const st = (opts.statusFilter || '').trim()
  if (st) {
    const rows = await db
      .prepare('SELECT * FROM invite_waitlist WHERE status = ?1 ORDER BY id DESC LIMIT ?2')
      .bind(st, lim)
      .all<WaitlistRow>()
    return rows.results || []
  }
  const rows = await db
    .prepare('SELECT * FROM invite_waitlist ORDER BY id DESC LIMIT ?1')
    .bind(lim)
    .all<WaitlistRow>()
  return rows.results || []
}

export async function getWaitlistEntryById(db: D1Database, id: number): Promise<WaitlistRow | null> {
  return (await db.prepare('SELECT * FROM invite_waitlist WHERE id = ?1 LIMIT 1').bind(id).first<WaitlistRow>()) ?? null
}

export async function updateWaitlistEntryStatus(
  db: D1Database,
  opts: { id: number; status: 'approved' | 'rejected'; assignedCode?: string },
): Promise<WaitlistRow | null> {
  const ts = nowShanghaiIso()
  return (
    (await db
      .prepare(
        `UPDATE invite_waitlist
         SET status = ?1, assigned_code = ?2, reviewed_at = ?3
         WHERE id = ?4
         RETURNING *`,
      )
      .bind(opts.status, (opts.assignedCode || '').trim().toUpperCase().slice(0, 40), ts, opts.id)
      .first<WaitlistRow>()) ?? null
  )
}

// ---------------- Structured 1-Click Content Reactions (Zero Open-Text UGC) ----------------

export const ALLOWED_REACTION_KEYS: Record<ReactionTargetType, readonly string[]> = {
  event: ['heavy', 'track', 'noise'],
  finance: ['bullish_cat', 'bearish_hedge', 'priced_in'],
  prediction: ['agree', 'disagree', 'neutral'],
}

export function isValidReactionTargetType(raw: string): raw is ReactionTargetType {
  return raw === 'event' || raw === 'finance' || raw === 'prediction'
}

export function isValidReactionKey(targetType: ReactionTargetType, reactionKey: string): boolean {
  return ALLOWED_REACTION_KEYS[targetType].includes(reactionKey)
}

function emptyCountsMap(targetType: ReactionTargetType): Record<string, number> {
  const out: Record<string, number> = {}
  for (const k of ALLOWED_REACTION_KEYS[targetType]) {
    out[k] = 0
  }
  return out
}

export async function getReactionsBatch(
  db: D1Database,
  opts: { targetType: ReactionTargetType; ids: string[]; voterKey: string },
): Promise<Record<string, ReactionSummary>> {
  const cleanIds = Array.from(
    new Set(opts.ids.map((s) => s.trim().slice(0, 120)).filter(Boolean)),
  ).slice(0, 100)

  const items: Record<string, ReactionSummary> = {}
  for (const tid of cleanIds) {
    items[tid] = {
      target_type: opts.targetType,
      target_id: tid,
      counts: emptyCountsMap(opts.targetType),
      total: 0,
      my_reaction: null,
    }
  }
  if (cleanIds.length === 0) return items

  const placeholders = cleanIds.map((_, idx) => `?${idx + 2}`).join(', ')
  const [countRows, myRows] = await Promise.all([
    db
      .prepare(
        `SELECT target_id, reaction_key, count
         FROM content_reactions
         WHERE target_type = ?1 AND target_id IN (${placeholders})`,
      )
      .bind(opts.targetType, ...cleanIds)
      .all<{ target_id: string; reaction_key: string; count: number }>(),
    db
      .prepare(
        `SELECT target_id, reaction_key
         FROM content_reaction_votes
         WHERE target_type = ?1 AND voter_key = ?2 AND target_id IN (${cleanIds
           .map((_, idx) => `?${idx + 3}`)
           .join(', ')})`,
      )
      .bind(opts.targetType, opts.voterKey, ...cleanIds)
      .all<{ target_id: string; reaction_key: string }>(),
  ])

  for (const r of countRows.results || []) {
    const entry = items[r.target_id]
    if (!entry) continue
    if (r.reaction_key in entry.counts) {
      entry.counts[r.reaction_key] = Math.max(0, Number(r.count ?? 0))
    }
  }
  for (const r of myRows.results || []) {
    const entry = items[r.target_id]
    if (!entry) continue
    entry.my_reaction = r.reaction_key
  }
  for (const entry of Object.values(items)) {
    entry.total = Object.values(entry.counts).reduce((acc, n) => acc + n, 0)
  }

  return items
}

export async function upsertContentReaction(
  db: D1Database,
  opts: {
    targetType: ReactionTargetType
    targetId: string
    voterKey: string
    reactionKey: string
  },
): Promise<ReactionSummary> {
  const targetId = opts.targetId.trim().slice(0, 120)
  const voterKey = opts.voterKey.trim().slice(0, 128)
  const ts = nowShanghaiIso()

  const existing = await db
    .prepare(
      `SELECT reaction_key
       FROM content_reaction_votes
       WHERE target_type = ?1 AND target_id = ?2 AND voter_key = ?3
       LIMIT 1`,
    )
    .bind(opts.targetType, targetId, voterKey)
    .first<{ reaction_key: string }>()

  const prevKey = existing?.reaction_key || null
  if (prevKey !== opts.reactionKey) {
    const stmts: D1PreparedStatement[] = []
    if (prevKey) {
      stmts.push(
        db
          .prepare(
            `UPDATE content_reactions
             SET count = MAX(0, count - 1), updated_at = ?4
             WHERE target_type = ?1 AND target_id = ?2 AND reaction_key = ?3`,
          )
          .bind(opts.targetType, targetId, prevKey, ts),
      )
    }
    stmts.push(
      db
        .prepare(
          `INSERT INTO content_reactions (target_type, target_id, reaction_key, count, updated_at)
           VALUES (?1, ?2, ?3, 1, ?4)
           ON CONFLICT(target_type, target_id, reaction_key) DO UPDATE SET
             count = count + 1,
             updated_at = excluded.updated_at`,
        )
        .bind(opts.targetType, targetId, opts.reactionKey, ts),
      db
        .prepare(
          `INSERT INTO content_reaction_votes (target_type, target_id, voter_key, reaction_key, updated_at)
           VALUES (?1, ?2, ?3, ?4, ?5)
           ON CONFLICT(target_type, target_id, voter_key) DO UPDATE SET
             reaction_key = excluded.reaction_key,
             updated_at = excluded.updated_at`,
        )
        .bind(opts.targetType, targetId, voterKey, opts.reactionKey, ts),
    )
    await db.batch(stmts)
  }

  const res = await getReactionsBatch(db, {
    targetType: opts.targetType,
    ids: [targetId],
    voterKey,
  })
  return (
    res[targetId] ?? {
      target_type: opts.targetType,
      target_id: targetId,
      counts: emptyCountsMap(opts.targetType),
      total: 0,
      my_reaction: opts.reactionKey,
    }
  )
}
