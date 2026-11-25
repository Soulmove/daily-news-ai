import { nowShanghaiIso } from './crypto'

export interface RateLimitResult {
  allowed: boolean
  remaining: number
  retryAfterSec: number
}

/**
 * Sliding-bucket D1 rate limiter to protect auth, OTP, QA, and feedback endpoints.
 */
export async function checkAndHitRateLimit(
  db: D1Database,
  opts: { scope: string; key: string; limit: number; windowSec: number },
): Promise<RateLimitResult> {
  const nowSec = Math.floor(Date.now() / 1000)
  const windowSec = Math.max(10, Math.floor(opts.windowSec))
  const windowStart = Math.floor(nowSec / windowSec) * windowSec
  const retryAfterSec = Math.max(1, windowStart + windowSec - nowSec)
  const bucketKey = String(opts.key || 'unknown').slice(0, 128)
  const ts = nowShanghaiIso()

  const row = await db
    .prepare(
      `INSERT INTO rate_limits (scope, bucket_key, window_start, count, updated_at)
       VALUES (?1, ?2, ?3, 1, ?4)
       ON CONFLICT(scope, bucket_key, window_start) DO UPDATE SET
         count = count + 1,
         updated_at = excluded.updated_at
       RETURNING count`,
    )
    .bind(opts.scope, bucketKey, windowStart, ts)
    .first<{ count: number }>()

  const count = Number(row?.count ?? 1)
  if (count === 1 && nowSec % 23 === 0) {
    // Occasional lightweight cleanup of stale buckets (> 24h old)
    const staleBefore = nowSec - 86_400
    await db.prepare('DELETE FROM rate_limits WHERE window_start < ?1').bind(staleBefore).run()
  }

  return {
    allowed: count <= opts.limit,
    remaining: Math.max(0, opts.limit - count),
    retryAfterSec,
  }
}

export async function checkRegistrationGuards(
  db: D1Database,
  ip: string,
  deviceId: string,
): Promise<string | null> {
  const t10m = nowShanghaiIso(-10 * 60_000)
  const t30m = nowShanghaiIso(-30 * 60_000)
  const t24h = nowShanghaiIso(-24 * 3600_000)

  const [dev30m, dev24h, devTotal, ip10m, ip24h, global10m] = await db.batch<{ cnt: number }>([
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE device_id = ?1 AND created_at >= ?2').bind(deviceId, t30m),
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE device_id = ?1 AND created_at >= ?2').bind(deviceId, t24h),
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE device_id = ?1').bind(deviceId),
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE ip = ?1 AND created_at >= ?2').bind(ip, t10m),
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE ip = ?1 AND created_at >= ?2').bind(ip, t24h),
    db.prepare('SELECT COUNT(*) AS cnt FROM registration_guards WHERE created_at >= ?1').bind(t10m),
  ])

  const cDev30m = Number(dev30m.results?.[0]?.cnt ?? 0)
  if (cDev30m >= 1) return '当前设备刚完成过注册，请 30 分钟后再试（防批量注册保护）。'

  const cDev24h = Number(dev24h.results?.[0]?.cnt ?? 0)
  if (cDev24h >= 2) return '当前设备 24 小时内注册次数已达上限（每日最多 2 次）。'

  const cDevTotal = Number(devTotal.results?.[0]?.cnt ?? 0)
  if (cDevTotal >= 3) return '当前设备累计注册账号数已达上限（单台设备最多注册 3 个账号）。'

  const cIp10m = Number(ip10m.results?.[0]?.cnt ?? 0)
  if (cIp10m >= 2) return '当前网络短时间内注册请求过多，请 10 分钟后再试。'

  const cIp24h = Number(ip24h.results?.[0]?.cnt ?? 0)
  if (cIp24h >= 5) return '当前网络今日注册次数已达上限（每日最多 5 次）。'

  const cGlobal10m = Number(global10m.results?.[0]?.cnt ?? 0)
  if (cGlobal10m >= 25) return '当前全站注册并发过高，请稍后再试。'

  return null
}

export async function recordRegistrationGuard(db: D1Database, ip: string, deviceId: string): Promise<void> {
  await db
    .prepare('INSERT INTO registration_guards (ip, device_id, created_at) VALUES (?1, ?2, ?3)')
    .bind(ip.slice(0, 64), deviceId.slice(0, 128), nowShanghaiIso())
    .run()
}
