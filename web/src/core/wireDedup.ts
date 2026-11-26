import type { LiveWireItem, LiveWireSourceRef } from './types'

const WIRE_FILLER_RE =
  /表示|指出|称|透露|宣布|据悉|消息|报道|项目|事宜|方面|进行|已经|已就|有关|相关|的|了|在|中|是|与|和|对|他|她|其|将|为|于/g

export function normalizeWireDedupKey(title: string): string {
  return String(title || '')
    .toLowerCase()
    .replace(/【[^】]+】/g, '')
    .replace(/（[^）]{1,36}）/g, '')
    .replace(/\([^)]{1,36}\)/g, '')
    .replace(/[\s\-_·:：,，.。!！?？()（）[\]【】'"%％+、/]+/g, '')
    .slice(0, 36)
}

function extractSubstantiveCore(title: string): string {
  return String(title || '')
    .toLowerCase()
    .replace(/【[^】]+】/g, '')
    .replace(/（[^）]{1,36}）/g, '')
    .replace(/\([^)]{1,36}\)/g, '')
    .replace(/[\s\-_·:：,，.。!！?？()（）[\]【】'"%％+、/]+/g, '')
    .replace(WIRE_FILLER_RE, '')
}

function buildCharBigrams(s: string): Set<string> {
  const out = new Set<string>()
  if (s.length < 2) {
    if (s) out.add(s)
    return out
  }
  for (let i = 0; i < s.length - 1; i++) {
    out.add(s.slice(i, i + 2))
  }
  return out
}

function parseEpochMs(iso: string | undefined): number {
  const t = Date.parse(String(iso || ''))
  return Number.isFinite(t) ? t : 0
}

export function areWireTitlesSimilar(aTitle: string, bTitle: string, aPubIso: string, bPubIso: string): boolean {
  const tA = parseEpochMs(aPubIso)
  const tB = parseEpochMs(bPubIso)
  if (tA > 0 && tB > 0) {
    const gapMin = Math.abs(tA - tB) / 60_000
    if (gapMin > 240) return false
  }

  const keyA = normalizeWireDedupKey(aTitle)
  const keyB = normalizeWireDedupKey(bTitle)
  if (keyA.length >= 6 && keyA === keyB) return true

  const gapMin = tA > 0 && tB > 0 ? Math.abs(tA - tB) / 60_000 : 0
  if (gapMin > 90) return false

  const aCore = extractSubstantiveCore(aTitle)
  const bCore = extractSubstantiveCore(bTitle)
  if (aCore.length < 6 || bCore.length < 6) return false

  const numsA = new Set(aTitle.match(/\d{2,}/g) || [])
  const numsB = new Set(bTitle.match(/\d{2,}/g) || [])
  if (numsA.size > 0 && numsB.size > 0) {
    let sharedNum = false
    for (const n of numsA) {
      if (numsB.has(n)) {
        sharedNum = true
        break
      }
    }
    if (!sharedNum) return false
  }

  const bgA = buildCharBigrams(aCore)
  const bgB = buildCharBigrams(bCore)
  let inter = 0
  for (const bg of bgA) {
    if (bgB.has(bg)) inter++
  }
  if (inter === 0) return false

  const dice = (2 * inter) / (bgA.size + bgB.size)
  const contain = inter / Math.max(1, Math.min(bgA.size, bgB.size))
  const minLen = Math.min(aCore.length, bCore.length)
  const maxLen = Math.max(aCore.length, bCore.length)

  if (dice >= 0.56) return true
  if (contain >= 0.72 && minLen >= 10 && maxLen / Math.max(1, minLen) <= 1.65) return true

  if (gapMin <= 20 && Math.abs(aCore.length - bCore.length) <= 8 && dice >= 0.36) {
    let prefixLen = 0
    const limit = Math.min(aCore.length, bCore.length)
    while (prefixLen < limit && aCore[prefixLen] === bCore[prefixLen]) {
      prefixLen++
    }
    const latA = new Set(aTitle.toLowerCase().match(/[a-z0-9]{2,}/g) || [])
    const latB = new Set(bTitle.toLowerCase().match(/[a-z0-9]{2,}/g) || [])
    let sharedLat = 0
    for (const tok of latA) {
      if (latB.has(tok)) sharedLat++
    }
    if (prefixLen >= 6 && sharedLat >= 1) return true
  }

  return false
}

const SEV_RANK: Record<string, number> = { S: 3, A: 2, B: 1 }

/** Client-side safety net: clusters duplicate/near-duplicate wire rows into multi-source entries. */
export function dedupeAndMergeWireItems(rawItems: LiveWireItem[]): LiveWireItem[] {
  if (!Array.isArray(rawItems) || rawItems.length === 0) return []
  const sorted = [...rawItems].sort((a, b) => String(b.published_at || '').localeCompare(String(a.published_at || '')))
  const clusters: LiveWireItem[][] = []

  for (const it of sorted) {
    if (!it || !it.title) continue
    const match = clusters.find((cl) => areWireTitlesSimilar(cl[0].title, it.title, cl[0].published_at, it.published_at))
    if (match) {
      match.push(it)
    } else {
      clusters.push([it])
    }
  }

  return clusters.map((cl) => {
    const ordered = [...cl].sort((a, b) => {
      const sevDiff = (SEV_RANK[String(b.severity_tier || 'B')] || 1) - (SEV_RANK[String(a.severity_tier || 'B')] || 1)
      if (sevDiff !== 0) return sevDiff
      const lenA = String(a.title || '').length
      const lenB = String(b.title || '').length
      if (Math.abs(lenA - lenB) > 2 && lenA <= 110 && lenB <= 110) {
        return lenB - lenA
      }
      return String(b.published_at || '').localeCompare(String(a.published_at || ''))
    })
    const primary = ordered[0]
    const newest = cl[0]

    let bestSev = primary.severity_tier || 'B'
    let bestReason = primary.heavy_reason_tag || null
    let highImp = primary.importance === 'high'
    let bestExcerpt = primary.excerpt || ''
    const srcSeen = new Set<string>()
    const mergedSources: LiveWireSourceRef[] = []

    const pushSource = (srcName: string, url: string, pubAt: string) => {
      const cleanName = String(srcName || '').trim() || '实时快讯'
      const norm = cleanName.toLowerCase().replace(/\s+/g, '')
      if (srcSeen.has(norm)) return
      srcSeen.add(norm)
      mergedSources.push({ source_name: cleanName, url: url || '', published_at: pubAt || '' })
    }

    for (const m of cl) {
      if ((SEV_RANK[String(m.severity_tier || 'B')] || 1) > (SEV_RANK[bestSev] || 1)) {
        bestSev = m.severity_tier as 'S' | 'A' | 'B'
      }
      if (!bestReason && m.heavy_reason_tag) bestReason = m.heavy_reason_tag
      if (m.importance === 'high') highImp = true
      if (m.excerpt && m.excerpt !== m.title && m.excerpt.length > bestExcerpt.length) {
        bestExcerpt = m.excerpt
      }
      if (Array.isArray(m.merged_sources) && m.merged_sources.length > 0) {
        for (const ms of m.merged_sources) {
          pushSource(ms.source_name, ms.url, ms.published_at)
        }
      } else {
        pushSource(m.source_name, m.url, m.published_at)
      }
    }

    const existingCount = cl.reduce((acc, m) => Math.max(acc, Number(m.source_count || 1)), 1)
    const sourceCount = Math.max(existingCount, mergedSources.length, 1)
    const mergedCount = cl.reduce((acc, m) => acc + Math.max(1, Number(m.merged_count || 1)), 0)

    return {
      ...primary,
      published_at: newest.published_at || primary.published_at,
      fetched_at: newest.fetched_at || primary.fetched_at,
      excerpt: bestExcerpt || primary.excerpt || primary.title,
      severity_tier: bestSev,
      heavy_reason_tag: bestReason,
      importance: highImp || bestSev !== 'B' ? 'high' : 'normal',
      source_count: sourceCount,
      merged_count: mergedCount,
      evidence_status: sourceCount >= 2 ? 'multi_source' : primary.evidence_status || 'single_source',
      merged_sources: mergedSources,
    }
  })
}
