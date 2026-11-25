import { t } from './i18n'
import type { HealthBadgeInfo } from './types'

const SHANGHAI_TZ = 'Asia/Shanghai'

export function parseTimestampMs(isoOrDate: string | null | undefined): number | null {
  if (!isoOrDate || typeof isoOrDate !== 'string') return null
  const text = isoOrDate.trim()
  if (!text) return null
  // Handle naive "YYYY-MM-DD HH:mm(:ss)" as Asia/Shanghai (+08:00)
  const naiveMatch = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/.exec(text)
  if (naiveMatch) {
    const [, y, m, d, hh, mm, ss] = naiveMatch
    const iso = `${y}-${m}-${d}T${hh}:${mm}:${ss || '00'}+08:00`
    const parsed = Date.parse(iso)
    return Number.isNaN(parsed) ? null : parsed
  }
  // Handle pure date "YYYY-MM-DD"
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const parsed = Date.parse(`${text}T00:00:00+08:00`)
    return Number.isNaN(parsed) ? null : parsed
  }
  const parsed = Date.parse(text)
  return Number.isNaN(parsed) ? null : parsed
}

export function extractShanghaiParts(ms: number): { year: string; month: string; day: string; hour: string; minute: string } {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: SHANGHAI_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date(ms))
  const map: Record<string, string> = {}
  for (const p of parts) {
    map[p.type] = p.value
  }
  const hh = map.hour === '24' ? '00' : map.hour
  return {
    year: map.year,
    month: map.month,
    day: map.day,
    hour: hh,
    minute: map.minute,
  }
}

export function formatShanghaiDateTime(isoOrDate: string | null | undefined, includeYear = true): string {
  const ms = parseTimestampMs(isoOrDate)
  if (ms === null) return t('时间未知', 'Unknown time')
  const map = extractShanghaiParts(ms)
  if (includeYear) {
    return `${map.year}-${map.month}-${map.day} ${map.hour}:${map.minute}`
  }
  return `${map.month}-${map.day} ${map.hour}:${map.minute}`
}

export function formatShanghaiHhMm(isoOrDate: string | null | undefined): string {
  const ms = parseTimestampMs(isoOrDate)
  if (ms === null) return ''
  const map = extractShanghaiParts(ms)
  return `${map.hour}:${map.minute}`
}

export function formatShanghaiDateOnly(isoOrDate: string | null | undefined): string {
  const ms = parseTimestampMs(isoOrDate)
  if (ms === null) return t('未知日期', 'Unknown date')
  const map = extractShanghaiParts(ms)
  return `${map.year}-${map.month}-${map.day}`
}

export function formatRelativeAge(isoOrDate: string | null | undefined, nowMs: number): string {
  const ms = parseTimestampMs(isoOrDate)
  if (ms === null) return t('时间未知', 'Unknown time')
  const diffMs = nowMs - ms
  if (diffMs < 60_000) return t('刚刚', 'Just now')
  const diffMins = Math.floor(diffMs / 60_000)
  if (diffMins < 60) return t(`${diffMins} 分钟前`, `${diffMins}m ago`)
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) {
    return t(`${diffHours} 小时前`, `${diffHours}h ago`)
  }
  const target = extractShanghaiParts(ms)
  const nowParts = extractShanghaiParts(nowMs)
  if (target.year === nowParts.year) {
    return `${target.month}-${target.day} ${target.hour}:${target.minute}`
  }
  return `${target.year}-${target.month}-${target.day} ${target.hour}:${target.minute}`
}

/**
 * B7 Unified Timestamp Formatter:
 * - Within 24h: relative ("刚刚" / "N 分钟前" / "N 小时前" or EN equivalent)
 * - >= 24h & same year (Asia/Shanghai): "MM-DD HH:mm"
 * - Cross-year: "YYYY-MM-DD HH:mm"
 * - Always provides `title` with full "YYYY-MM-DD HH:mm CST" for hover inspection
 */
export function formatUnifiedTime(
  isoOrDate: string | null | undefined,
  nowMs: number,
  fallbackText?: string,
  ingestedIso?: string | null,
): { text: string; title: string; iso: string | undefined } {
  const ms = parseTimestampMs(isoOrDate)
  if (ms === null) {
    const fb = fallbackText || t('时间未知', 'Unknown time')
    return { text: fb, title: fb, iso: undefined }
  }
  const full = formatShanghaiDateTime(isoOrDate, true)
  const hhmm = formatShanghaiHhMm(isoOrDate)
  const diffMs = nowMs - ms
  let text: string
  if (diffMs >= -60_000 && diffMs < 24 * 3_600_000) {
    const rel = formatRelativeAge(isoOrDate, nowMs)
    text = hhmm ? `${rel} (${hhmm} ${t('发布', 'pub')})` : rel
  } else {
    const target = extractShanghaiParts(ms)
    const nowParts = extractShanghaiParts(nowMs)
    text =
      target.year === nowParts.year
        ? `${target.month}-${target.day} ${target.hour}:${target.minute}`
        : `${target.year}-${target.month}-${target.day} ${target.hour}:${target.minute}`
  }
  const ingestedStr = ingestedIso ? ` · ${t('本站收录', 'Ingested')} ${formatShanghaiDateTime(ingestedIso, false)} CST` : ''
  return {
    text,
    title: `${t('原文发布', 'Published')} ${full} CST${ingestedStr}`,
    iso: new Date(ms).toISOString(),
  }
}

export function formatFriendlyBatchId(batchId: string | null | undefined): string {
  const raw = String(batchId || '').trim()
  if (!raw) return '-'
  const m = /^(?:smart|raw)-(\d{8})-(\d{4,6})$/i.exec(raw)
  if (m) {
    return t(`云端同步批次 #${m[1]}-${m[2].slice(0, 4)}`, `Cloud Batch #${m[1]}-${m[2].slice(0, 4)}`)
  }
  return raw
}

export function parseArchiveTimeFromPath(archivePath: string | null | undefined): string | null {
  if (!archivePath) return null
  const m = /archives\/(?:raw|smart)\/(\d{4}-\d{2}-\d{2})\/(\d{2})-(\d{2})/.exec(archivePath)
  if (!m) return null
  return `${m[1]}T${m[2]}:${m[3]}:00+08:00`
}

export function evaluateRawHealth(
  fetchedAtIso: string | null | undefined,
  nowMs: number,
  targetMinutes: number,
  opts: { isHistory: boolean; status?: string; errorSources?: number; staleSources?: number },
): HealthBadgeInfo {
  if (opts.isHistory) {
    return {
      level: 'history',
      label: t('历史快照', 'Archive Snapshot'),
      detail: t(
        `当前查看的是历史采集批次（${formatShanghaiDateTime(fetchedAtIso)}）`,
        `Viewing historical raw batch (${formatShanghaiDateTime(fetchedAtIso)} CST)`,
      ),
      pillClass: 'bg-indigo-50 text-indigo-800 border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border-indigo-800',
    }
  }
  const ms = parseTimestampMs(fetchedAtIso)
  if (ms === null) {
    return {
      level: 'stale',
      label: t('采集时间未知', 'Fetch Time Unknown'),
      detail: t('未检测到有效采集元数据', 'No valid crawl metadata detected'),
      pillClass: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
    }
  }
  const ageMins = Math.max(0, Math.floor((nowMs - ms) / 60_000))
  const hasErrors = (opts.errorSources || 0) > 0 || opts.status === 'partial'

  if (ageMins > 180) {
    const hrs = (ageMins / 60).toFixed(1)
    return {
      level: 'stale',
      label: t(`长期停更/队列滞后 (${hrs}h)`, `Stale / Delayed (${hrs}h)`),
      detail: t(
        `目标每 ${targetMinutes} 分钟采集，最近一次成功入库已距今 ${hrs} 小时（受云端自动聚合管线队列影响）`,
        `Target cadence ${targetMinutes}m; last crawl was ${hrs}h ago (cloud pipeline queue delay).`,
      ),
      pillClass: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
    }
  }
  if (ageMins > targetMinutes + 15) {
    return {
      level: 'delayed',
      label: t(`采集延迟 (${ageMins} 分钟前)`, `Delayed (${ageMins}m ago)`),
      detail: t(
        `已超出目标 ${targetMinutes} 分钟节奏约 ${ageMins - targetMinutes} 分钟`,
        `Behind ${targetMinutes}m cadence by ~${ageMins - targetMinutes}m`,
      ),
      pillClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
    }
  }
  if (hasErrors) {
    return {
      level: 'partial',
      label: t(`部分来源异常 (${opts.errorSources || 0})`, `Partial Issues (${opts.errorSources || 0})`),
      detail: t(
        `本次采集如期完成，但有 ${opts.errorSources || 0} 个来源请求失败`,
        `Crawl completed with ${opts.errorSources || 0} failing source(s)`,
      ),
      pillClass: 'bg-orange-50 text-orange-800 border-orange-200 dark:bg-orange-950/60 dark:text-orange-300 dark:border-orange-800',
    }
  }
  return {
    level: 'healthy',
    label: t('采集正常', 'Healthy'),
    detail: t(
      `距离上次入库 ${formatRelativeAge(fetchedAtIso, nowMs)}`,
      `Last ingested ${formatRelativeAge(fetchedAtIso, nowMs)}`,
    ),
    pillClass: 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
  }
}

export function evaluateSmartHealth(
  generatedAtIso: string | null | undefined,
  nowMs: number,
  opts: {
    isHistory: boolean
    status?: string
    hasFallbackCat?: boolean
    fallbackCategories?: string[]
    rawFetchedAtIso?: string | null
    rawStatus?: string
    quotaDegraded?: boolean
    errorSources?: number
  },
): HealthBadgeInfo {
  if (opts.isHistory) {
    return {
      level: 'history',
      label: t('历史归档批次', 'Archive Batch'),
      detail: t(
        `正在查看历史简报（生成于 ${formatShanghaiDateTime(generatedAtIso)} CST）`,
        `Viewing historical batch (generated ${formatShanghaiDateTime(generatedAtIso)} CST)`,
      ),
      pillClass: 'bg-indigo-50 text-indigo-800 border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-300 dark:border-indigo-800',
    }
  }
  const ms = parseTimestampMs(generatedAtIso)
  if (ms === null) {
    return {
      level: 'stale',
      label: t('生成时间未知', 'Build Time Unknown'),
      detail: t('未获取到简报生成时间戳', 'No briefing generation timestamp'),
      pillClass: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
    }
  }
  const ageHours = Math.max(0, (nowMs - ms) / 3_600_000)

  const rawMs = parseTimestampMs(opts.rawFetchedAtIso)
  const rawAgeMins = rawMs !== null ? Math.max(0, Math.floor((nowMs - rawMs) / 60_000)) : null
  if (rawAgeMins !== null && rawAgeMins > 180) {
    const rawHrs = (rawAgeMins / 60).toFixed(1)
    return {
      level: 'stale',
      label: t(`上游采集滞后 (${rawHrs}h)`, `Upstream Crawl Lag (${rawHrs}h)`),
      detail: t(
        `简报生成于 ${formatRelativeAge(generatedAtIso, nowMs)}，但原始信源抓取已滞后 ${rawHrs} 小时，请注意数据时效`,
        `Briefing generated ${formatRelativeAge(generatedAtIso, nowMs)}, while upstream crawl lags ${rawHrs}h.`,
      ),
      pillClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
    }
  }
  if (opts.quotaDegraded) {
    return {
      level: 'partial',
      label: t('云端通道降级运行', 'Degraded Sync'),
      detail: t(
        '云端智能分析引擎繁忙，当前展示最近已核验及直连确定性结果',
        'Cloud engine busy; showing verified & deterministic direct feeds.',
      ),
      pillClass: 'bg-orange-50 text-orange-800 border-orange-200 dark:bg-orange-950/60 dark:text-orange-300 dark:border-orange-800',
    }
  }
  if (opts.hasFallbackCat || opts.status === 'partial') {
    const fbNames = (opts.fallbackCategories || []).filter(Boolean)
    const fbSuffix = fbNames.length > 0 ? `（${fbNames.join('、')}）` : ''
    return {
      level: 'partial',
      label: t(`部分频道沿用上次成功数据${fbSuffix}`, `Partial Cached${fbSuffix ? ` (${fbNames.join(', ')})` : ''}`),
      detail: t(
        fbNames.length > 0
          ? `${fbNames.join('、')} 在本轮抓取/分析降级，已自动保留该频道最近一次完整成功简报`
          : '部分分类在本轮更新失败，系统保留该分类最近一次有效简报并标明真实时间',
        fbNames.length > 0
          ? `${fbNames.join(', ')} fell back to their latest verified batch.`
          : 'Some categories fell back to their latest verified batch.',
      ),
      pillClass: 'bg-orange-50 text-orange-800 border-orange-200 dark:bg-orange-950/60 dark:text-orange-300 dark:border-orange-800',
    }
  }
  if (ageHours > 26) {
    return {
      level: 'stale',
      label: t(`简报停更预警 (${Math.floor(ageHours)}h)`, `Stale Briefing (${Math.floor(ageHours)}h)`),
      detail: t(
        '超过 26 小时未发布新简报批次，请检查云端自动聚合管线状态',
        'No new batch in >26h; check cloud ingestion pipeline status.',
      ),
      pillClass: 'bg-red-50 text-red-800 border-red-200 dark:bg-red-950/60 dark:text-red-300 dark:border-red-800',
    }
  }
  if (ageHours > 14) {
    return {
      level: 'delayed',
      label: t(`更新略有延迟 (${Math.floor(ageHours)}h 前)`, `Slightly Delayed (${Math.floor(ageHours)}h ago)`),
      detail: t(
        '已超过 12 小时常规更新窗口，当前展示最近一次完整成功批次',
        'Beyond 12h cycle; showing latest complete batch.',
      ),
      pillClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
    }
  }
  return {
    level: 'healthy',
    label: t('全部数据源已同步最新批次', 'All Sources Synced · Latest'),
    detail: t(
      `全部频道与模块均已同步最新完整简报批次（生成于 ${formatRelativeAge(generatedAtIso, nowMs)}）`,
      `All channels synced to latest complete batch (generated ${formatRelativeAge(generatedAtIso, nowMs)})`,
    ),
    pillClass: 'bg-emerald-50 text-emerald-800 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
  }
}
