import type { RawClusterEvent, RawItem, RawPlatform } from './types'

const ASCII_WORD_RE = /[a-z0-9]{2,}/g

export function sanitizeExcerptText(raw: string | null | undefined): string | null {
  if (!raw || typeof raw !== 'string') return null
  const text = raw
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim()
  return text || null
}

export function extractTokens(text: string): Set<string> {
  const tokens = new Set<string>()
  if (!text) return tokens
  const lowered = text.toLowerCase()
  const asciiMatches = lowered.match(ASCII_WORD_RE)
  if (asciiMatches) {
    for (const w of asciiMatches) tokens.add(w)
  }
  const cjkRuns = lowered.match(/[\u4e00-\u9fff]+/g)
  if (cjkRuns) {
    for (const run of cjkRuns) {
      for (let i = 0; i < run.length - 1; i++) {
        tokens.add(run.slice(i, i + 2))
      }
    }
  }
  return tokens
}

export function computeTitleSimilarity(a: string, b: string): number {
  const ta = extractTokens(a)
  const tb = extractTokens(b)
  if (ta.size === 0 || tb.size === 0) return 0
  let inter = 0
  for (const t of ta) {
    if (tb.has(t)) inter++
  }
  if (inter === 0) return 0
  const union = ta.size + tb.size - inter
  const minSize = Math.min(ta.size, tb.size)
  return 0.45 * (inter / union) + 0.55 * (inter / minSize)
}

export function clusterRawPlatforms(platforms: RawPlatform[], includeFallback = true): RawClusterEvent[] {
  const flatItems: RawItem[] = []
  for (const p of platforms) {
    for (const it of p.items) {
      flatItems.push(it)
    }
    if (includeFallback && p.status === 'error' && p.fallback_used && p.fallback_items?.length) {
      for (const it of p.fallback_items) {
        flatItems.push({ ...it, is_fallback: true })
      }
    }
  }

  const byUrl = new Map<string, RawClusterEvent>()
  const ordered: { cluster: RawClusterEvent; tokens: Set<string> }[] = []

  for (const item of flatItems) {
    const cleanedExcerpt = sanitizeExcerptText(item.excerpt)
    const app = {
      item_id: item.item_id,
      source_id: item.source_id,
      source_name: item.source_name,
      title: item.title,
      url: item.url,
      published_at: item.published_at,
      excerpt: cleanedExcerpt,
      metric_label: item.metric_label || null,
      is_fallback: Boolean(item.is_fallback),
    }

    const canon = item.canonical_url || item.url
    const urlExisting = byUrl.get(canon)
    if (urlExisting) {
      if (!urlExisting.appearances.some((a) => a.source_id === app.source_id)) {
        urlExisting.appearances.push(app)
      }
      if (!urlExisting.published_at && item.published_at) urlExisting.published_at = item.published_at
      if (!urlExisting.excerpt && cleanedExcerpt) urlExisting.excerpt = cleanedExcerpt
      continue
    }

    const cluster: RawClusterEvent = {
      cluster_id: item.item_id,
      primary_title: item.title,
      primary_url: item.url,
      category: item.category,
      source_kind: item.source_kind,
      published_at: item.published_at,
      fetched_at: item.fetched_at,
      excerpt: cleanedExcerpt,
      metric_label: item.metric_label || null,
      appearances: [app],
    }

    const tokens = extractTokens(item.title)
    let matched: { cluster: RawClusterEvent; tokens: Set<string> } | null = null

    if (item.source_kind !== 'market_ticker' && tokens.size >= 3) {
      for (const existing of ordered) {
        if (existing.cluster.source_kind === 'market_ticker') continue
        let inter = 0
        for (const t of tokens) {
          if (existing.tokens.has(t)) inter++
        }
        if (inter < 3) continue
        const union = tokens.size + existing.tokens.size - inter
        const minSize = Math.min(tokens.size, existing.tokens.size)
        const overlap = inter / minSize
        const score = 0.45 * (inter / union) + 0.55 * overlap
        if (score >= 0.58 || (inter >= 5 && overlap >= 0.36)) {
          matched = existing
          break
        }
      }
    }

    if (matched) {
      if (!matched.cluster.appearances.some((a) => a.item_id === app.item_id)) {
        matched.cluster.appearances.push(app)
      }
      if (!matched.cluster.published_at && item.published_at) matched.cluster.published_at = item.published_at
      if (!matched.cluster.excerpt && item.excerpt) matched.cluster.excerpt = item.excerpt
    } else {
      byUrl.set(canon, cluster)
      ordered.push({ cluster, tokens })
    }
  }

  return ordered.map((o) => o.cluster)
}
