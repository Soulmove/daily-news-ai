import { nowShanghaiIso } from './crypto'
import { getSiteSettings } from './db'
import { getPredictionCrowdStats } from './dbExtras'
import { fetchAndBuildMarketQuotes, type MarketQuoteEntry, type MarketQuotesDoc } from './quotes'
import type { Env } from './types'

export const ALLOWED_REASON_TAGS = [
  '流动性驱动',
  '业绩超预期',
  '市场已计价',
  '政策博弈',
  '逆向情绪',
] as const

export type ReasonTag = (typeof ALLOWED_REASON_TAGS)[number]

export const RANK_TIERS = [
  '见习观察员',
  '趋势捕手',
  '宏观校准师',
  '先知猎手',
  '超级预言家',
] as const

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
  status: string
  outcome: string | null
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
  status: string
  published_prediction_id: string
  created_at: string
  reviewed_at: string
}

export interface UserPredictionProfileRow {
  user_id: number
  season_key: string
  insight_points: number
  settled_count: number
  hit_count: number
  brier_sum: number
  current_streak: number
  best_streak: number
  rank_tier: string
  bonus_qa_quota: number
  bonus_qa_expires_at: string
  unlocked_referral_bonus: number
  updated_at: string
}

export function isValidReasonTag(tag: string): boolean {
  if (!tag) return true
  return (ALLOWED_REASON_TAGS as readonly string[]).includes(tag)
}

export function parseIsoMs(iso: string | null | undefined): number | null {
  if (!iso || typeof iso !== 'string') return null
  const ms = Date.parse(iso.trim())
  return Number.isFinite(ms) ? ms : null
}

export function shanghaiMsToIso(ms: number): string {
  const d = new Date(ms + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}+08:00`
}

export function getShanghaiDateParts(nowMs = Date.now()): {
  ymd: string
  dateStr: string
  dow: number
  hour: number
  minute: number
} {
  const d = new Date(nowMs + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  return {
    ymd: `${yyyy}${mm}${dd}`,
    dateStr: `${yyyy}-${mm}-${dd}`,
    dow: d.getUTCDay(),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
  }
}

export function getShanghaiSeasonKey(nowMs = Date.now()): string {
  const { dateStr } = getShanghaiDateParts(nowMs)
  return dateStr.slice(0, 7)
}

function addShanghaiDaysDateStr(nowMs: number, days: number): { dateStr: string; dow: number } {
  const { dateStr } = getShanghaiDateParts(nowMs)
  const baseMidnightMs = Date.parse(`${dateStr}T00:00:00+08:00`) + days * 86_400_000
  const d = new Date(baseMidnightMs + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  return {
    dateStr: `${yyyy}-${mm}-${dd}`,
    dow: d.getUTCDay(),
  }
}

export function computeLockAtIso(dueAtIso: string, explicitLockAt?: string | null): string {
  const lockMs = parseIsoMs(explicitLockAt)
  if (lockMs !== null) return shanghaiMsToIso(lockMs)
  const dueMs = parseIsoMs(dueAtIso)
  if (dueMs === null) return dueAtIso
  return shanghaiMsToIso(dueMs - 30 * 60_000)
}

export function isPredictionLocked(
  dueAtIso: string,
  status?: string | null,
  explicitLockAt?: string | null,
  nowMs = Date.now(),
): boolean {
  const st = (status || '').trim().toLowerCase()
  if (st === 'settled' || st === 'locked') return true
  const lockMs = parseIsoMs(explicitLockAt)
  const dueMs = parseIsoMs(dueAtIso)
  const effectiveLockMs = lockMs !== null ? lockMs : dueMs !== null ? dueMs - 30 * 60_000 : null
  if (effectiveLockMs !== null && nowMs >= effectiveLockMs) return true
  if (dueMs !== null && nowMs >= dueMs) return true
  return false
}

export function computeEarlyMultiplier(
  createdAtIso: string | null | undefined,
  lockAtIso: string | null | undefined,
  nowMs = Date.now(),
): number {
  const cMs = parseIsoMs(createdAtIso)
  const lMs = parseIsoMs(lockAtIso)
  if (cMs === null || lMs === null || lMs <= cMs) return 1.0
  const ratio = Math.max(0, (nowMs - cMs) / (lMs - cMs))
  if (ratio <= 0.25) return 1.5
  if (ratio <= 0.6) return 1.2
  return 1.0
}

export function computeRankTier(profile: {
  insight_points: number
  settled_count: number
  hit_count: number
  brier_sum: number
}): string {
  const settled = Number(profile.settled_count || 0)
  const hits = Number(profile.hit_count || 0)
  const pts = Number(profile.insight_points || 0)
  const avgBrier = settled > 0 ? Number(profile.brier_sum || 0) / settled : 1.0

  if (pts >= 1500 && settled >= 20 && avgBrier <= 0.15) return '超级预言家'
  if (pts >= 800 && settled >= 10 && avgBrier <= 0.18) return '先知猎手'
  if (pts >= 400 && settled >= 5 && avgBrier <= 0.22) return '宏观校准师'
  if (pts >= 150 || hits >= 3) return '趋势捕手'
  return '见习观察员'
}

async function loadQuotesDocForArena(env: Env, overrideDoc?: MarketQuotesDoc | null): Promise<MarketQuotesDoc | null> {
  if (overrideDoc) return overrideDoc
  try {
    const obj = await env.R2_DATA.get('data/market_quotes.json')
    if (obj) {
      const parsed = (await obj.json()) as MarketQuotesDoc
      if (parsed && parsed.quotes && Object.keys(parsed.quotes).length > 0) {
        return parsed
      }
    }
  } catch {
    // Fall back to live Edge quotes fetcher
  }
  try {
    return await fetchAndBuildMarketQuotes(env)
  } catch {
    return null
  }
}

function pickQuote(quotes: Record<string, MarketQuoteEntry>, candidates: string[]): MarketQuoteEntry | null {
  for (const ticker of candidates) {
    const q = quotes[ticker]
    if (q && Number.isFinite(Number(q.price)) && Number(q.price) > 0) {
      return q
    }
  }
  return null
}

export async function ensureDailyMarketPredictions(
  env: Env,
  opts: { nowMs?: number; quotesDoc?: MarketQuotesDoc | null; forceTradingDay?: boolean } = {},
): Promise<{ created: number; skipped?: boolean; ids: string[] }> {
  const nowMs = opts.nowMs ?? Date.now()
  const settings = await getSiteSettings(env.DB, env.SITE_ACCESS_MODE)
  if (settings.prediction_daily_market_enabled === false) {
    return { created: 0, skipped: true, ids: [] }
  }

  const parts = getShanghaiDateParts(nowMs)
  if (!opts.forceTradingDay && (parts.dow === 0 || parts.dow === 6)) {
    return { created: 0, skipped: true, ids: [] }
  }

  const quotesDoc = await loadQuotesDocForArena(env, opts.quotesDoc)
  const quotesMap = quotesDoc?.quotes || {}
  const nextAsianTradingOffset = parts.dow === 5 ? 3 : parts.dow === 6 ? 2 : 1
  const nextAsianDay = addShanghaiDaysDateStr(nowMs, nextAsianTradingOffset).dateStr

  // Find next valid US equity close (Tue-Sat morning 05:05 Beijing time) >= 4h from nowMs
  let nextUsCloseIso = `${nextAsianDay}T05:05:00+08:00`
  for (let offset = 1; offset <= 5; offset += 1) {
    const cand = addShanghaiDaysDateStr(nowMs, offset)
    // US market session closes Tue(2), Wed(3), Thu(4), Fri(5), Sat(6) mornings in Beijing
    if (cand.dow >= 2 && cand.dow <= 6) {
      const candIso = `${cand.dateStr}T05:05:00+08:00`
      const candMs = parseIsoMs(candIso)
      if (candMs !== null && candMs - nowMs >= 4 * 3600_000) {
        nextUsCloseIso = candIso
        break
      }
    }
  }

  const createdIso = shanghaiMsToIso(nowMs)
  const candidates: Array<{
    id: string
    category: string
    title: string
    question: string
    win_rule: string
    lose_rule: string
    ticker: string
    base_price: number
    target_price: number
    ai_prob_pct: number
    due_at: string
    lock_at: string
  }> = []

  const sseQuote = pickQuote(quotesMap, ['000001.SH'])
  if (sseQuote) {
    const base = Number(Number(sseQuote.price).toFixed(2))
    const dueAt = `${nextAsianDay}T15:05:00+08:00`
    const lockAt = computeLockAtIso(dueAt)
    const pctBias = Math.max(-6, Math.min(6, Number(sseQuote.pct_change || 0) * 1.8))
    candidates.push({
      id: `daily_mkt_${parts.ymd}_sse`,
      category: 'market',
      title: `T+1 日赛：上证指数 (${nextAsianDay}) 收盘能否站稳 ${base} 点之上（收红）`,
      question: `截至 ${nextAsianDay} 15:00 A股收盘，上证指数 (000001.SH) 收盘价是否高于当前参考基准 ${base} 点？`,
      win_rule: `${nextAsianDay} A股收盘行情显示 000001.SH 最新收盘价 > ${base}`,
      lose_rule: `${nextAsianDay} A股收盘行情显示 000001.SH 最新收盘价 <= ${base}`,
      ticker: sseQuote.ticker,
      base_price: base,
      target_price: base,
      ai_prob_pct: Math.round(Math.max(38, Math.min(64, 52 + pctBias))),
      due_at: dueAt,
      lock_at: lockAt,
    })
  }

  const nvdaQuote = pickQuote(quotesMap, ['NVDA', 'IXIC'])
  if (nvdaQuote) {
    const base = Number(Number(nvdaQuote.price).toFixed(2))
    const dueDateLabel = nextUsCloseIso.slice(0, 10)
    const lockAt = computeLockAtIso(nextUsCloseIso)
    const pctBias = Math.max(-7, Math.min(7, Number(nvdaQuote.pct_change || 0) * 1.6))
    const nameLabel = nvdaQuote.ticker === 'NVDA' ? '英伟达 (NVDA)' : '纳斯达克指数 (IXIC)'
    candidates.push({
      id: `daily_mkt_${parts.ymd}_nvda`,
      category: 'tech_ai',
      title: `美股日赛：${nameLabel} 今夜收盘能否高于基准 ${base}`,
      question: `截至 ${dueDateLabel} 05:00（北京时间）美股常规交易收盘，${nameLabel} 收盘价是否严格高于当前基准 ${base}？`,
      win_rule: `美股当日收盘后行情报价 ${nvdaQuote.ticker} > ${base}`,
      lose_rule: `美股当日收盘后行情报价 ${nvdaQuote.ticker} <= ${base}`,
      ticker: nvdaQuote.ticker,
      base_price: base,
      target_price: base,
      ai_prob_pct: Math.round(Math.max(40, Math.min(65, 53 + pctBias))),
      due_at: nextUsCloseIso,
      lock_at: lockAt,
    })
  }

  const goldQuote = pickQuote(quotesMap, ['XAUUSD', 'GC=F', 'GLD', '518880.SH'])
  if (goldQuote) {
    const base = Number(Number(goldQuote.price).toFixed(2))
    let target = base
    if (base >= 500) {
      const step = base >= 2000 ? 10 : 5
      const nearest = Math.round(base / step) * step
      if (Math.abs(nearest - base) / base <= 0.015) {
        target = nearest
      }
    }
    const dueAt = `${nextAsianDay}T16:00:00+08:00`
    const lockAt = computeLockAtIso(dueAt)
    const gapPct = ((base - target) / Math.max(1, target)) * 100
    const aiProb = Math.round(Math.max(38, Math.min(65, 51 + gapPct * 6)))
    candidates.push({
      id: `daily_mkt_${parts.ymd}_gold`,
      category: 'market',
      title: `大宗日赛：${goldQuote.name} (${nextAsianDay}) 能否站上关键关口 ${target}`,
      question: `截至 ${nextAsianDay} 16:00（北京时间），${goldQuote.name} (${goldQuote.ticker}) 最新参考价是否高于 ${target}（当前基准 ${base}）？`,
      win_rule: `截至 ${nextAsianDay} 16:00 实时报价 ${goldQuote.ticker} > ${target}`,
      lose_rule: `截至 ${nextAsianDay} 16:00 实时报价 ${goldQuote.ticker} <= ${target}`,
      ticker: goldQuote.ticker,
      base_price: base,
      target_price: target,
      ai_prob_pct: aiProb,
      due_at: dueAt,
      lock_at: lockAt,
    })
  }

  let created = 0
  const ids: string[] = []
  for (const item of candidates) {
    const res = await env.DB.prepare(
      `INSERT OR IGNORE INTO daily_predictions (
         id, source_type, category, title, question, win_rule, lose_rule,
         ticker, base_price, target_price, ai_prob_pct, created_at, lock_at, due_at, status
       ) VALUES (?1, 'auto_market', ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, 'open')`,
    )
      .bind(
        item.id,
        item.category,
        item.title,
        item.question,
        item.win_rule,
        item.lose_rule,
        item.ticker,
        item.base_price,
        item.target_price,
        item.ai_prob_pct,
        createdIso,
        item.lock_at,
        item.due_at,
      )
      .run()
    ids.push(item.id)
    if (Number(res.meta?.changes ?? 0) > 0) created += 1
  }

  return { created, ids }
}

export async function settleDailyPrediction(
  db: D1Database,
  opts: {
    predictionId: string
    outcome: 'yes' | 'no' | 'void'
    settledValue?: number | null
    nowMs?: number
    rewardsEnabled?: boolean
  },
): Promise<{ ok: boolean; already_settled?: boolean; settled_votes: number; outcome: string }> {
  const nowMs = opts.nowMs ?? Date.now()
  const settledIso = shanghaiMsToIso(nowMs)
  const seasonKey = getShanghaiSeasonKey(nowMs)
  const expires7dIso = shanghaiMsToIso(nowMs + 7 * 86_400_000)

  const predRow = await db
    .prepare('SELECT id, status, ai_prob_pct FROM daily_predictions WHERE id = ?1 LIMIT 1')
    .bind(opts.predictionId)
    .first<{ id: string; status: string; ai_prob_pct: number }>()

  if (predRow) {
    const upd = await db
      .prepare(
        `UPDATE daily_predictions
         SET status = 'settled', outcome = ?1, settled_value = ?2, settled_at = ?3
         WHERE id = ?4 AND status != 'settled'`,
      )
      .bind(opts.outcome, opts.settledValue ?? null, settledIso, opts.predictionId)
      .run()
    if (Number(upd.meta?.changes ?? 0) === 0) {
      return { ok: true, already_settled: true, settled_votes: 0, outcome: opts.outcome }
    }
  }

  const aiProbPct = Number(predRow?.ai_prob_pct ?? 50)
  const votesRes = await db
    .prepare(
      `SELECT user_id, prob_pct, early_multiplier
       FROM prediction_crowd_votes
       WHERE prediction_id = ?1 AND settled_at IS NULL`,
    )
    .bind(opts.predictionId)
    .all<{ user_id: number; prob_pct: number; early_multiplier: number }>()

  const voteRows = votesRes.results || []
  let settledVotes = 0
  const actualVal = opts.outcome === 'yes' ? 1 : 0
  const aiP = aiProbPct / 100
  const aiBrier = Number(((aiP - actualVal) ** 2).toFixed(4))

  for (const v of voteRows) {
    if (opts.outcome === 'void') {
      await db
        .prepare(
          `UPDATE prediction_crowd_votes
           SET brier_score = NULL, points_awarded = 0, settled_at = ?1
           WHERE prediction_id = ?2 AND user_id = ?3`,
        )
        .bind(settledIso, opts.predictionId, v.user_id)
        .run()
      settledVotes += 1
      continue
    }

    const probPct = Number(v.prob_pct)
    const p = probPct / 100
    const brier = Number(((p - actualVal) ** 2).toFixed(4))
    const isHit = (opts.outcome === 'yes' && probPct > 50) || (opts.outcome === 'no' && probPct < 50)

    const existingProfile = await db
      .prepare('SELECT * FROM user_prediction_profiles WHERE user_id = ?1 AND season_key = ?2 LIMIT 1')
      .bind(v.user_id, seasonKey)
      .first<UserPredictionProfileRow>()

    const curPoints = Number(existingProfile?.insight_points ?? 0)
    const curSettled = Number(existingProfile?.settled_count ?? 0)
    const curHits = Number(existingProfile?.hit_count ?? 0)
    const curBrierSum = Number(existingProfile?.brier_sum ?? 0)
    const curStreak = Number(existingProfile?.current_streak ?? 0)
    const curBestStreak = Number(existingProfile?.best_streak ?? 0)
    let nextBonusQa = Number(existingProfile?.bonus_qa_quota ?? 0)
    let nextBonusExpires = String(existingProfile?.bonus_qa_expires_at || '')
    let nextRefBonus = Number(existingProfile?.unlocked_referral_bonus ?? 0)

    const nextSettled = curSettled + 1
    const nextHits = curHits + (isHit ? 1 : 0)
    const nextBrierSum = Number((curBrierSum + brier).toFixed(4))
    const nextStreak = isHit ? curStreak + 1 : 0
    const nextBestStreak = Math.max(curBestStreak, nextStreak)

    let pointsAwarded = 0
    if (opts.rewardsEnabled !== false) {
      const base = isHit
        ? Math.max(10, Math.round((1 - brier) * 100))
        : Math.max(0, Math.round((0.35 - brier) * 40))
      const mult = Math.max(1, Number(v.early_multiplier || 1))
      const streakBonus = isHit && nextStreak >= 2 ? 15 * Math.min(5, nextStreak - 1) : 0
      const beatAiBonus = isHit && brier < aiBrier ? 20 : 0
      pointsAwarded = Math.round(base * mult) + streakBonus + beatAiBonus
    }

    const nextPoints = curPoints + pointsAwarded
    const nextRankTier = computeRankTier({
      insight_points: nextPoints,
      settled_count: nextSettled,
      hit_count: nextHits,
      brier_sum: nextBrierSum,
    })

    if (opts.rewardsEnabled !== false) {
      if (nextStreak >= 3) {
        nextBonusQa = Math.max(nextBonusQa, 10)
        nextBonusExpires = expires7dIso
      }
      if (nextRankTier !== '见习观察员' || nextHits >= 3) {
        nextRefBonus = Math.max(nextRefBonus, 2)
      }
    }

    await db
      .prepare(
        `UPDATE prediction_crowd_votes
         SET brier_score = ?1, points_awarded = ?2, settled_at = ?3
         WHERE prediction_id = ?4 AND user_id = ?5`,
      )
      .bind(brier, pointsAwarded, settledIso, opts.predictionId, v.user_id)
      .run()

    await db
      .prepare(
        `INSERT INTO user_prediction_profiles (
           user_id, season_key, insight_points, settled_count, hit_count, brier_sum,
           current_streak, best_streak, rank_tier, bonus_qa_quota, bonus_qa_expires_at,
           unlocked_referral_bonus, updated_at
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)
         ON CONFLICT(user_id, season_key) DO UPDATE SET
           insight_points = excluded.insight_points,
           settled_count = excluded.settled_count,
           hit_count = excluded.hit_count,
           brier_sum = excluded.brier_sum,
           current_streak = excluded.current_streak,
           best_streak = excluded.best_streak,
           rank_tier = excluded.rank_tier,
           bonus_qa_quota = excluded.bonus_qa_quota,
           bonus_qa_expires_at = excluded.bonus_qa_expires_at,
           unlocked_referral_bonus = excluded.unlocked_referral_bonus,
           updated_at = excluded.updated_at`,
      )
      .bind(
        v.user_id,
        seasonKey,
        nextPoints,
        nextSettled,
        nextHits,
        nextBrierSum,
        nextStreak,
        nextBestStreak,
        nextRankTier,
        nextBonusQa,
        nextBonusExpires,
        nextRefBonus,
        settledIso,
      )
      .run()

    settledVotes += 1
  }

  // Reward Top 30% in current monthly season leaderboard with +10 bonus QA quota (7-day expiry)
  if (opts.rewardsEnabled !== false && opts.outcome !== 'void' && settledVotes > 0) {
    const seasonRows = await db
      .prepare(
        `SELECT user_id, insight_points, settled_count, bonus_qa_quota
         FROM user_prediction_profiles
         WHERE season_key = ?1
         ORDER BY insight_points DESC, settled_count DESC, hit_count DESC`,
      )
      .bind(seasonKey)
      .all<{ user_id: number; insight_points: number; settled_count: number; bonus_qa_quota: number }>()
    const ranked = seasonRows.results || []
    const topCutoff = Math.max(1, Math.ceil(ranked.length * 0.3))
    for (let i = 0; i < Math.min(topCutoff, ranked.length); i += 1) {
      const r = ranked[i]
      if (Number(r.settled_count) >= 1 && Number(r.insight_points) > 0) {
        await db
          .prepare(
            `UPDATE user_prediction_profiles
             SET bonus_qa_quota = ?1, bonus_qa_expires_at = ?2, updated_at = ?3
             WHERE user_id = ?4 AND season_key = ?5`,
          )
          .bind(Math.max(Number(r.bonus_qa_quota || 0), 10), expires7dIso, settledIso, r.user_id, seasonKey)
          .run()
      }
    }
  }

  return { ok: true, settled_votes: settledVotes, outcome: opts.outcome }
}

export async function runPredictionArenaCron(
  env: Env,
  opts: { nowMs?: number; quotesDoc?: MarketQuotesDoc | null; forceTradingDay?: boolean } = {},
): Promise<{ generated: number; locked: number; settled: number }> {
  const nowMs = opts.nowMs ?? Date.now()
  const settings = await getSiteSettings(env.DB, env.SITE_ACCESS_MODE)
  const rewardsEnabled = settings.prediction_rewards_enabled !== false

  const genRes = await ensureDailyMarketPredictions(env, opts)

  const openRes = await env.DB.prepare(
    `SELECT * FROM daily_predictions WHERE status IN ('open', 'locked') ORDER BY due_at ASC`,
  ).all<DailyPredictionRow>()
  const rows = openRes.results || []

  let lockedCount = 0
  let settledCount = 0
  let quotesDoc: MarketQuotesDoc | null = opts.quotesDoc ?? null

  for (const row of rows) {
    if (row.status === 'open' && isPredictionLocked(row.due_at, row.status, row.lock_at, nowMs)) {
      await env.DB.prepare(`UPDATE daily_predictions SET status = 'locked' WHERE id = ?1 AND status = 'open'`)
        .bind(row.id)
        .run()
      lockedCount += 1
    }

    const dueMs = parseIsoMs(row.due_at)
    if (row.source_type === 'auto_market' && dueMs !== null && nowMs >= dueMs && row.ticker) {
      if (!quotesDoc) {
        quotesDoc = await loadQuotesDocForArena(env, null)
      }
      const q = quotesDoc?.quotes?.[row.ticker]
      const price = q ? Number(q.price) : NaN
      if (Number.isFinite(price) && price > 0) {
        const refVal = Number(row.target_price ?? row.base_price ?? price)
        const outcome: 'yes' | 'no' = price > refVal ? 'yes' : 'no'
        const res = await settleDailyPrediction(env.DB, {
          predictionId: row.id,
          outcome,
          settledValue: price,
          nowMs,
          rewardsEnabled,
        })
        if (!res.already_settled) settledCount += 1
      }
    }
  }

  return { generated: genRes.created, locked: lockedCount, settled: settledCount }
}

export async function getActivePredictionBonusQaQuota(
  db: D1Database,
  userId: number,
  nowMs = Date.now(),
): Promise<number> {
  const rows = await db
    .prepare('SELECT bonus_qa_quota, bonus_qa_expires_at FROM user_prediction_profiles WHERE user_id = ?1')
    .bind(userId)
    .all<{ bonus_qa_quota: number; bonus_qa_expires_at: string }>()
  let maxBonus = 0
  for (const r of rows.results || []) {
    const expMs = parseIsoMs(r.bonus_qa_expires_at)
    if (expMs !== null && expMs > nowMs) {
      maxBonus = Math.max(maxBonus, Math.max(0, Math.round(Number(r.bonus_qa_quota || 0))))
    }
  }
  return maxBonus
}

export async function getUserPredictionReferralBonus(db: D1Database, userId: number): Promise<number> {
  const row = await db
    .prepare('SELECT COALESCE(SUM(unlocked_referral_bonus), 0) AS total_bonus FROM user_prediction_profiles WHERE user_id = ?1')
    .bind(userId)
    .first<{ total_bonus: number }>()
  return Math.max(0, Math.round(Number(row?.total_bonus ?? 0)))
}

export async function awardProposalAdoptionReward(
  db: D1Database,
  userId: number,
  nowMs = Date.now(),
  rewardsEnabled = true,
): Promise<void> {
  if (!rewardsEnabled) return
  const ts = shanghaiMsToIso(nowMs)
  const seasonKey = getShanghaiSeasonKey(nowMs)
  const existing = await db
    .prepare('SELECT * FROM user_prediction_profiles WHERE user_id = ?1 AND season_key = ?2 LIMIT 1')
    .bind(userId, seasonKey)
    .first<UserPredictionProfileRow>()

  const nextPoints = Number(existing?.insight_points ?? 0) + 100
  const settled = Number(existing?.settled_count ?? 0)
  const hits = Number(existing?.hit_count ?? 0)
  const brierSum = Number(existing?.brier_sum ?? 0)
  const rankTier = computeRankTier({
    insight_points: nextPoints,
    settled_count: settled,
    hit_count: hits,
    brier_sum: brierSum,
  })
  const nextRefBonus = Number(existing?.unlocked_referral_bonus ?? 0) + 1

  await db
    .prepare(
      `INSERT INTO user_prediction_profiles (
         user_id, season_key, insight_points, settled_count, hit_count, brier_sum,
         current_streak, best_streak, rank_tier, bonus_qa_quota, bonus_qa_expires_at,
         unlocked_referral_bonus, updated_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)
       ON CONFLICT(user_id, season_key) DO UPDATE SET
         insight_points = excluded.insight_points,
         rank_tier = excluded.rank_tier,
         unlocked_referral_bonus = excluded.unlocked_referral_bonus,
         updated_at = excluded.updated_at`,
    )
    .bind(
      userId,
      seasonKey,
      nextPoints,
      settled,
      hits,
      brierSum,
      Number(existing?.current_streak ?? 0),
      Number(existing?.best_streak ?? 0),
      rankTier,
      Number(existing?.bonus_qa_quota ?? 0),
      String(existing?.bonus_qa_expires_at || ''),
      nextRefBonus,
      ts,
    )
    .run()
}

export async function findPredictionDeadline(
  env: Env,
  predictionId: string,
): Promise<{
  found: boolean
  status: string
  created_at: string
  lock_at: string
  due_at: string
  ai_prob_pct: number
  title: string
  question: string
  win_rule: string
  lose_rule: string
  proposer_username: string
}> {
  const row = await env.DB.prepare('SELECT * FROM daily_predictions WHERE id = ?1 LIMIT 1')
    .bind(predictionId)
    .first<DailyPredictionRow>()
  if (row) {
    return {
      found: true,
      status: row.status,
      created_at: row.created_at,
      lock_at: row.lock_at || computeLockAtIso(row.due_at),
      due_at: row.due_at,
      ai_prob_pct: Number(row.ai_prob_pct ?? 50),
      title: row.title,
      question: row.question,
      win_rule: row.win_rule,
      lose_rule: row.lose_rule,
      proposer_username: row.proposer_username || '',
    }
  }

  try {
    const obj = await env.R2_DATA.get('data/predictions_public.json')
    if (obj) {
      const doc = (await obj.json()) as { predictions?: Array<Record<string, unknown>> }
      const hit = (doc.predictions || []).find((p) => String(p.prediction_id || '') === predictionId)
      if (hit) {
        const dueAt = String(hit.due_at || '')
        const status = hit.settlement ? 'settled' : String(hit.status || 'open')
        return {
          found: true,
          status,
          created_at: String(hit.created_at || ''),
          lock_at: computeLockAtIso(dueAt),
          due_at: dueAt,
          ai_prob_pct: Number(hit.probability_pct ?? 50),
          title: String(hit.title || ''),
          question: String(hit.question || ''),
          win_rule: String(hit.win_rule || ''),
          lose_rule: String(hit.lose_rule || ''),
          proposer_username: '',
        }
      }
    }
  } catch {
    // Ignore R2 errors
  }

  return {
    found: false,
    status: 'open',
    created_at: '',
    lock_at: '',
    due_at: '',
    ai_prob_pct: 50,
    title: '',
    question: '',
    win_rule: '',
    lose_rule: '',
    proposer_username: '',
  }
}

export async function createPredictionProposal(
  db: D1Database,
  opts: {
    userId: number
    username: string
    category: string
    title: string
    question: string
    winRule: string
    loseRule: string
    dueAt: string
  },
): Promise<PredictionProposalRow> {
  const ts = nowShanghaiIso()
  const row = await db
    .prepare(
      `INSERT INTO prediction_proposals (
         user_id, username, category, title, question, win_rule, lose_rule, due_at, status, created_at
       ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, 'pending', ?9)
       RETURNING *`,
    )
    .bind(
      opts.userId,
      opts.username.slice(0, 48),
      opts.category.slice(0, 32) || 'market',
      opts.title.trim().slice(0, 140),
      opts.question.trim().slice(0, 320),
      opts.winRule.trim().slice(0, 240),
      opts.loseRule.trim().slice(0, 240),
      opts.dueAt.trim().slice(0, 48),
      ts,
    )
    .first<PredictionProposalRow>()
  if (!row) throw new Error('Failed to create proposal')
  return row
}

export async function listPredictionProposals(
  db: D1Database,
  opts: { statusFilter?: string; limit?: number } = {},
): Promise<PredictionProposalRow[]> {
  const limit = Math.max(1, Math.min(200, Math.round(opts.limit ?? 80)))
  const st = (opts.statusFilter || '').trim()
  if (st && ['pending', 'approved', 'rejected'].includes(st)) {
    const res = await db
      .prepare('SELECT * FROM prediction_proposals WHERE status = ?1 ORDER BY id DESC LIMIT ?2')
      .bind(st, limit)
      .all<PredictionProposalRow>()
    return res.results || []
  }
  const res = await db
    .prepare('SELECT * FROM prediction_proposals ORDER BY id DESC LIMIT ?1')
    .bind(limit)
    .all<PredictionProposalRow>()
  return res.results || []
}

export async function listUserPredictionProposals(db: D1Database, userId: number): Promise<PredictionProposalRow[]> {
  const res = await db
    .prepare('SELECT * FROM prediction_proposals WHERE user_id = ?1 ORDER BY id DESC LIMIT 40')
    .bind(userId)
    .all<PredictionProposalRow>()
  return res.results || []
}

export async function approvePredictionProposal(
  db: D1Database,
  opts: { proposalId: number; nowMs?: number; rewardsEnabled?: boolean },
): Promise<{ proposal: PredictionProposalRow | null; prediction: DailyPredictionRow | null; already_approved?: boolean }> {
  const nowMs = opts.nowMs ?? Date.now()
  const ts = shanghaiMsToIso(nowMs)
  const proposal = await db
    .prepare('SELECT * FROM prediction_proposals WHERE id = ?1 LIMIT 1')
    .bind(opts.proposalId)
    .first<PredictionProposalRow>()
  if (!proposal) return { proposal: null, prediction: null }
  if (proposal.status === 'approved' && proposal.published_prediction_id) {
    const existingPred = await db
      .prepare('SELECT * FROM daily_predictions WHERE id = ?1 LIMIT 1')
      .bind(proposal.published_prediction_id)
      .first<DailyPredictionRow>()
    return { proposal, prediction: existingPred ?? null, already_approved: true }
  }

  const predId = `pred_co_${proposal.id}_${nowMs.toString(36)}`
  const lockAt = computeLockAtIso(proposal.due_at)
  await db
    .prepare(
      `INSERT INTO daily_predictions (
         id, source_type, category, title, question, win_rule, lose_rule,
         ticker, base_price, target_price, ai_prob_pct, created_at, lock_at, due_at,
         status, proposer_user_id, proposer_username
       ) VALUES (?1, 'user_proposal', ?2, ?3, ?4, ?5, ?6, '', NULL, NULL, 50, ?7, ?8, ?9, 'open', ?10, ?11)`,
    )
    .bind(
      predId,
      proposal.category || 'market',
      proposal.title,
      proposal.question,
      proposal.win_rule || '官方或公开可查一手信源明确达成条件',
      proposal.lose_rule || '截至到期日仍未满足条件或公开否定',
      ts,
      lockAt,
      proposal.due_at,
      proposal.user_id,
      proposal.username,
    )
    .run()

  await db
    .prepare(
      `UPDATE prediction_proposals
       SET status = 'approved', published_prediction_id = ?1, reviewed_at = ?2
       WHERE id = ?3`,
    )
    .bind(predId, ts, proposal.id)
    .run()

  await awardProposalAdoptionReward(db, proposal.user_id, nowMs, opts.rewardsEnabled !== false)

  const [updProposal, createdPred] = await Promise.all([
    db.prepare('SELECT * FROM prediction_proposals WHERE id = ?1 LIMIT 1').bind(proposal.id).first<PredictionProposalRow>(),
    db.prepare('SELECT * FROM daily_predictions WHERE id = ?1 LIMIT 1').bind(predId).first<DailyPredictionRow>(),
  ])
  return { proposal: updProposal ?? null, prediction: createdPred ?? null }
}

export async function rejectPredictionProposal(
  db: D1Database,
  proposalId: number,
  nowMs = Date.now(),
): Promise<PredictionProposalRow | null> {
  const ts = shanghaiMsToIso(nowMs)
  return (
    (await db
      .prepare(
        `UPDATE prediction_proposals
         SET status = 'rejected', reviewed_at = ?1
         WHERE id = ?2 RETURNING *`,
      )
      .bind(ts, proposalId)
      .first<PredictionProposalRow>()) ?? null
  )
}

export async function listDailyPredictions(db: D1Database, limit = 60): Promise<DailyPredictionRow[]> {
  const safeLimit = Math.max(1, Math.min(200, Math.round(limit)))
  const res = await db
    .prepare('SELECT * FROM daily_predictions ORDER BY created_at DESC LIMIT ?1')
    .bind(safeLimit)
    .all<DailyPredictionRow>()
  return res.results || []
}

export async function buildPredictionArenaPayload(
  env: Env,
  opts: { userId: number | null; minVotes: number; nowMs?: number },
): Promise<Record<string, unknown>> {
  const nowMs = opts.nowMs ?? Date.now()
  const seasonKey = getShanghaiSeasonKey(nowMs)

  let publicPredictions: Array<Record<string, unknown>> = []
  try {
    const r2Obj = await env.R2_DATA.get('data/predictions_public.json')
    if (r2Obj) {
      const doc = (await r2Obj.json()) as { predictions?: Array<Record<string, unknown>> }
      if (Array.isArray(doc?.predictions)) publicPredictions = doc.predictions
    }
  } catch {
    publicPredictions = []
  }

  const [dailyRows, crowdStats, lbRes, myProfileRow] = await Promise.all([
    listDailyPredictions(env.DB, 40),
    getPredictionCrowdStats(env.DB, { userId: opts.userId, minVotes: opts.minVotes }),
    env.DB.prepare(
      `SELECT
         p.user_id, p.season_key, p.insight_points, p.settled_count, p.hit_count,
         p.brier_sum, p.current_streak, p.best_streak, p.rank_tier,
         u.username, u.display_name, u.avatar
       FROM user_prediction_profiles p
       JOIN users u ON u.id = p.user_id
       WHERE p.season_key = ?1
       ORDER BY p.insight_points DESC, p.hit_count DESC, p.settled_count DESC
       LIMIT 20`,
    )
      .bind(seasonKey)
      .all<Record<string, unknown>>(),
    opts.userId
      ? env.DB.prepare('SELECT * FROM user_prediction_profiles WHERE user_id = ?1 AND season_key = ?2 LIMIT 1')
          .bind(opts.userId, seasonKey)
          .first<UserPredictionProfileRow>()
      : Promise.resolve(null),
  ])

  const leaderboard = (lbRes.results || []).map((r, idx) => {
    const settled = Number(r.settled_count ?? 0)
    const hits = Number(r.hit_count ?? 0)
    const brierSum = Number(r.brier_sum ?? 0)
    return {
      rank: idx + 1,
      user_id: Number(r.user_id),
      username: String(r.username || ''),
      display_name: String(r.display_name || r.username || ''),
      avatar: String(r.avatar || ''),
      insight_points: Number(r.insight_points ?? 0),
      settled_count: settled,
      hit_count: hits,
      hit_rate_pct: settled > 0 ? Math.round((hits / settled) * 100) : null,
      avg_brier: settled > 0 ? Number((brierSum / settled).toFixed(4)) : null,
      current_streak: Number(r.current_streak ?? 0),
      best_streak: Number(r.best_streak ?? 0),
      rank_tier: String(r.rank_tier || '见习观察员'),
    }
  })

  let myProfile: Record<string, unknown> | null = null
  if (opts.userId) {
    const settled = Number(myProfileRow?.settled_count ?? 0)
    const hits = Number(myProfileRow?.hit_count ?? 0)
    const brierSum = Number(myProfileRow?.brier_sum ?? 0)
    const expMs = parseIsoMs(myProfileRow?.bonus_qa_expires_at)
    const activeBonusQa = expMs !== null && expMs > nowMs ? Number(myProfileRow?.bonus_qa_quota ?? 0) : 0
    myProfile = {
      user_id: opts.userId,
      season_key: seasonKey,
      insight_points: Number(myProfileRow?.insight_points ?? 0),
      settled_count: settled,
      hit_count: hits,
      hit_rate_pct: settled > 0 ? Math.round((hits / settled) * 100) : null,
      avg_brier: settled > 0 ? Number((brierSum / settled).toFixed(4)) : null,
      current_streak: Number(myProfileRow?.current_streak ?? 0),
      best_streak: Number(myProfileRow?.best_streak ?? 0),
      rank_tier: String(myProfileRow?.rank_tier || '见习观察员'),
      bonus_qa_quota: activeBonusQa,
      bonus_qa_expires_at: activeBonusQa > 0 ? String(myProfileRow?.bonus_qa_expires_at || '') : '',
      unlocked_referral_bonus: Number(myProfileRow?.unlocked_referral_bonus ?? 0),
    }
  }

  return {
    season_key: seasonKey,
    daily_predictions: dailyRows,
    public_predictions: publicPredictions,
    crowd_stats: crowdStats.items,
    min_votes: crowdStats.min_votes,
    my_profile: myProfile,
    leaderboard,
    allowed_reason_tags: ALLOWED_REASON_TAGS,
    server_time: shanghaiMsToIso(nowMs),
  }
}
