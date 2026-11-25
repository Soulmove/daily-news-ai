import { resolveDataUrl } from './dataBase'
import {
  adaptRawCategoryPlatforms,
  adaptSimulatedComments,
  adaptSmartCategoryDoc,
  buildLegacyRawMeta,
} from './legacyAdapter'
import { parseArchiveTimeFromPath } from './time'
import type {
  AiProgressDoc,
  CatalystEvent,
  CategoryKey,
  ConnectorsLatestDoc,
  EntityProfile,
  FinanceImpactDoc,
  HistoryIndexEntry,
  MajorTopicSpotlight,
  ManifestV2,
  PredictionRecord,
  RadarItem,
  RawBatchMeta,
  RawPlatform,
  SimulatedCommentsDoc,
  SmartCategoryDoc,
  StorylineDossier,
  TechToolEntry,
} from './types'

const ALL_CATEGORIES: CategoryKey[] = ['finance', 'global', 'tech', 'general']

function toRelativeUrl(relPath: string, cacheBust = false): string {
  return resolveDataUrl(relPath, cacheBust)
}

export async function fetchJson<T>(
  relPath: string,
  opts: { noStore?: boolean; cacheBust?: boolean; timeoutMs?: number } = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 12000)
  try {
    const url = toRelativeUrl(relPath, Boolean(opts.cacheBust))
    const resp = await fetch(url, {
      cache: opts.noStore ? 'no-store' : 'default',
      signal: controller.signal,
    })
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status} for ${relPath}`)
    }
    return (await resp.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export async function fetchManifest(forceFresh = false): Promise<ManifestV2 | null> {
  try {
    return await fetchJson<ManifestV2>('data/manifest.json', {
      noStore: true,
      cacheBust: forceFresh,
      timeoutMs: 10000,
    })
  } catch {
    return null
  }
}

export async function fetchHistoryIndex(
  kind: 'smart' | 'raw',
  forceFresh = false,
): Promise<HistoryIndexEntry[]> {
  const path = kind === 'smart' ? 'history/smart_index.json' : 'history/raw_index.json'
  const raw = await fetchJson<unknown>(path, {
    noStore: true,
    cacheBust: forceFresh,
  })
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (item): item is HistoryIndexEntry =>
      Boolean(item && typeof item === 'object' && typeof (item as HistoryIndexEntry).path === 'string'),
  )
}

function normalizeArchivePrefix(archivePath: string): string {
  const clean = archivePath.replace(/^\/+/, '').replace(/^\.\//, '')
  return clean.endsWith('/') ? clean : `${clean}/`
}

export async function fetchSmartCategory(
  category: CategoryKey,
  opts: {
    archivePath?: string | null
    manifest?: ManifestV2 | null
    forceFresh?: boolean
  } = {},
): Promise<SmartCategoryDoc> {
  const archivePrefix = opts.archivePath ? normalizeArchivePrefix(opts.archivePath) : null
  let targetPath = ''
  let fallbackMeta: { is_fallback?: boolean; fallback_reason?: string | null } = {}

  if (archivePrefix) {
    targetPath = `${archivePrefix}analysis_${category}.json`
  } else if (opts.manifest?.smart?.categories?.[category]) {
    const entry = opts.manifest.smart.categories[category]
    fallbackMeta = {
      is_fallback: entry.is_fallback,
      fallback_reason: entry.fallback_reason,
    }
    if (!entry.path) {
      return {
        schema_version: '2.0',
        batch_id: opts.manifest.smart.latest_batch_id,
        input_batch_id: opts.manifest.smart.input_batch_id,
        input_cutoff_at: opts.manifest.smart.input_cutoff_at,
        generated_at: opts.manifest.smart.generated_at,
        published_at: opts.manifest.smart.published_at,
        category,
        category_label: category,
        generation_mode: 'missing',
        key_changes: [],
        overview_sections: [],
        events: [],
        missing: true,
        error: entry.fallback_reason || '当前批次该分类尚未生成简报',
      }
    }
    targetPath = entry.path
  } else {
    targetPath = `analysis_${category}.json`
  }

  try {
    const raw = await fetchJson<unknown>(targetPath, {
      // Historical archives are immutable by timestamp folder; latest non-archive root files use no-store
      noStore: !archivePrefix && !targetPath.startsWith('archives/'),
      cacheBust: Boolean(opts.forceFresh && !archivePrefix),
    })
    const doc = adaptSmartCategoryDoc(raw, category, archivePrefix ?? undefined)
    if (fallbackMeta.is_fallback) {
      doc.is_fallback = true
      doc.fallback_reason = fallbackMeta.fallback_reason ?? '当前分类沿用上次成功生成的简报'
    }
    return doc
  } catch (err) {
    // Self-heal when manifest archive path returns 404 (e.g. CDN/sync lag): fall back to root analysis_{cat}.json or last archive
    if (!archivePrefix && targetPath !== `analysis_${category}.json`) {
      try {
        const rootRaw = await fetchJson<unknown>(`analysis_${category}.json`, {
          noStore: true,
          cacheBust: true,
        })
        const rootDoc = adaptSmartCategoryDoc(rootRaw, category)
        rootDoc.is_fallback = true
        rootDoc.fallback_reason = '当前归档分片正在同步，已自动切换至主干最新分类简报'
        return rootDoc
      } catch {
        // Also try previous smart archive entry as second safety net
        try {
          const hist = await fetchHistoryIndex('smart', Boolean(opts.forceFresh))
          for (const h of hist.slice(0, 3)) {
            if (!h.path) continue
            const pfx = normalizeArchivePrefix(h.path)
            if (pfx === normalizeArchivePrefix(targetPath.replace(/analysis_[^/]+$/, ''))) continue
            try {
              const prevRaw = await fetchJson<unknown>(`${pfx}analysis_${category}.json`)
              const prevDoc = adaptSmartCategoryDoc(prevRaw, category, pfx)
              prevDoc.is_fallback = true
              prevDoc.fallback_reason = '当前批次归档同步中，已自动回退至上一有效批次简报'
              return prevDoc
            } catch {
              continue
            }
          }
        } catch {
          // Proceed to missing sentinel below
        }
      }
    }
    return {
      schema_version: '2.0',
      batch_id: archivePrefix ? 'missing' : (opts.manifest?.smart?.latest_batch_id ?? 'error'),
      input_batch_id: '',
      input_cutoff_at: archivePrefix ? (parseArchiveTimeFromPath(archivePrefix) ?? '') : '',
      generated_at: archivePrefix ? (parseArchiveTimeFromPath(archivePrefix) ?? '') : '',
      published_at: null,
      category,
      category_label: category,
      generation_mode: 'error',
      key_changes: [],
      overview_sections: [],
      events: [],
      missing: true,
      error: err instanceof Error ? err.message : '加载简报失败',
    }
  }
}

export async function fetchSimulatedComments(
  category: CategoryKey,
  opts: {
    archivePath?: string | null
    manifest?: ManifestV2 | null
    expectedBatchId?: string | null
    expectedGeneratedAt?: string | null
  } = {},
): Promise<SimulatedCommentsDoc> {
  const archivePrefix = opts.archivePath ? normalizeArchivePrefix(opts.archivePath) : null
  let targetPath = ''

  if (archivePrefix) {
    targetPath = `${archivePrefix}comments_${category}.json`
  } else if (opts.manifest?.smart?.categories?.[category]) {
    const entry = opts.manifest.smart.categories[category]
    if (!entry.has_comments || !entry.comments_path) {
      return {
        schema_version: '2.0',
        batch_id: opts.expectedBatchId ?? null,
        generated_at: null,
        category,
        is_ai_simulated: true,
        status: 'not_generated',
        disclaimer: '当前批次未生成 AI 模拟观点。',
        comments: [],
      }
    }
    targetPath = entry.comments_path || `comments_${category}.json`
  } else {
    targetPath = `comments_${category}.json`
  }

  try {
    const raw = await fetchJson<unknown>(targetPath, {
      noStore: !archivePrefix && !targetPath.startsWith('archives/'),
    })
    return adaptSimulatedComments(
      raw,
      category,
      opts.expectedBatchId ?? undefined,
      opts.expectedGeneratedAt ?? undefined,
    )
  } catch {
    return {
      schema_version: '2.0',
      batch_id: opts.expectedBatchId ?? null,
      generated_at: null,
      category,
      is_ai_simulated: true,
      status: archivePrefix ? 'not_generated' : 'missing',
      disclaimer: archivePrefix
        ? '该历史批次未随简报保存同批次 AI 模拟观点，已按批次一致性规则留空。'
        : '未能读取当前批次的 AI 模拟观点文件。',
      comments: [],
    }
  }
}

export async function fetchRawBatch(
  opts: {
    archivePath?: string | null
    manifest?: ManifestV2 | null
    categories?: CategoryKey[]
    forceFresh?: boolean
  } = {},
): Promise<{
  meta: RawBatchMeta
  platformsByCategory: Record<CategoryKey, RawPlatform[]>
  isHistory: boolean
  archivePath: string | null
}> {
  const isHistory = Boolean(opts.archivePath)
  const archivePrefix = opts.archivePath
    ? normalizeArchivePrefix(opts.archivePath)
    : opts.manifest?.raw?.latest_path
      ? normalizeArchivePrefix(opts.manifest.raw.latest_path)
      : null

  const targetCats = opts.categories ?? ALL_CATEGORIES

  let meta: RawBatchMeta | null = null
  const metaPath = isHistory
    ? `${archivePrefix}meta.json`
    : opts.manifest?.raw?.meta_path || (archivePrefix ? `${archivePrefix}meta.json` : null)

  if (metaPath) {
    try {
      meta = await fetchJson<RawBatchMeta>(metaPath, {
        noStore: !isHistory && !metaPath.startsWith('archives/'),
        cacheBust: Boolean(opts.forceFresh && !isHistory),
      })
    } catch {
      meta = null
    }
  }

  const batchFetchedAt =
    meta?.fetched_at ||
    (!isHistory ? opts.manifest?.raw?.fetched_at : undefined) ||
    (archivePrefix ? parseArchiveTimeFromPath(archivePrefix) : null) ||
    ''

  const platformsByCategory: Record<CategoryKey, RawPlatform[]> = {
    finance: [],
    global: [],
    tech: [],
    general: [],
  }

  await Promise.all(
    targetCats.map(async (cat) => {
      const dataPath =
        !isHistory && opts.manifest?.raw?.categories?.[cat]?.path
          ? opts.manifest.raw.categories[cat].path
          : archivePrefix
            ? `${archivePrefix}data_${cat}.json`
            : `data_${cat}.json`
      try {
        const raw = await fetchJson<unknown>(dataPath, {
          noStore: !dataPath.startsWith('archives/'),
          cacheBust: Boolean(opts.forceFresh && !isHistory),
        })
        platformsByCategory[cat] = adaptRawCategoryPlatforms(raw, cat, batchFetchedAt)
      } catch {
        platformsByCategory[cat] = []
      }
    }),
  )

  if (!meta) {
    const allPlatforms = ALL_CATEGORIES.flatMap((c) => platformsByCategory[c])
    meta = buildLegacyRawMeta(allPlatforms, archivePrefix ?? '')
  }

  return {
    meta,
    platformsByCategory,
    isHistory,
    archivePath: opts.archivePath ? normalizeArchivePrefix(opts.archivePath) : null,
  }
}

export async function fetchEntitiesIndex(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  entities: EntityProfile[]
}> {
  const path = manifest?.v3?.entities_path || 'data/entities_index.json'
  try {
    const res = await fetchJson<{ generated_at?: string; entities?: EntityProfile[] }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      entities: Array.isArray(res.entities) ? res.entities : [],
    }
  } catch {
    return { generated_at: '', entities: [] }
  }
}

export async function fetchStorylinesIndex(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  storylines: Record<string, StorylineDossier>
}> {
  const path = manifest?.v3?.storylines_path || 'data/storylines_index.json'
  try {
    const res = await fetchJson<{ generated_at?: string; storylines?: Record<string, StorylineDossier> }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      storylines: res.storylines && typeof res.storylines === 'object' ? res.storylines : {},
    }
  } catch {
    return { generated_at: '', storylines: {} }
  }
}

export async function fetchCalendarEvents(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  events: CatalystEvent[]
}> {
  const path = manifest?.v3?.calendar_path || 'data/calendar.json'
  try {
    const res = await fetchJson<{ generated_at?: string; events?: CatalystEvent[] }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      events: Array.isArray(res.events) ? res.events : [],
    }
  } catch {
    return { generated_at: '', events: [] }
  }
}

export async function fetchTechTools(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  tools: TechToolEntry[]
}> {
  const path = manifest?.v3?.tech_tools_path || 'data/tech_tools.json'
  try {
    const res = await fetchJson<{ generated_at?: string; tools?: TechToolEntry[] }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      tools: Array.isArray(res.tools) ? res.tools : [],
    }
  } catch {
    return { generated_at: '', tools: [] }
  }
}

export async function fetchRadarItems(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  baseline_window_note: string
  items: RadarItem[]
}> {
  const path = manifest?.v3?.radar_path || 'data/radar.json'
  try {
    const res = await fetchJson<{ generated_at?: string; baseline_window_note?: string; items?: RadarItem[] }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      baseline_window_note: res.baseline_window_note || '',
      items: Array.isArray(res.items) ? res.items : [],
    }
  } catch {
    return { generated_at: '', baseline_window_note: '', items: [] }
  }
}

export async function fetchPredictionsPublic(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  note: string
  predictions: PredictionRecord[]
}> {
  const path = manifest?.v3?.predictions_path || 'data/predictions_public.json'
  try {
    const res = await fetchJson<{ generated_at?: string; note?: string; predictions?: PredictionRecord[] }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    return {
      generated_at: res.generated_at || '',
      note: res.note || '',
      predictions: Array.isArray(res.predictions)
        ? res.predictions.map((p) => ({ ...p, is_seed: true }))
        : [],
    }
  } catch {
    return { generated_at: '', note: '', predictions: [] }
  }
}

export async function fetchConnectorsLatest(manifest?: ManifestV2 | null, forceFresh = false): Promise<ConnectorsLatestDoc | null> {
  const path = manifest?.v3?.connectors_path || manifest?.connectors?.latest_path || 'data/connectors_latest.json'
  try {
    return await fetchJson<ConnectorsLatestDoc>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
  } catch {
    return null
  }
}

export async function fetchMajorTopics(manifest?: ManifestV2 | null, forceFresh = false): Promise<{
  generated_at: string
  topics: MajorTopicSpotlight[]
  archived_topics: MajorTopicSpotlight[]
}> {
  const path = manifest?.v3?.topics_path || 'data/topics.json'
  try {
    const res = await fetchJson<{
      generated_at?: string
      topics?: MajorTopicSpotlight[]
      archived_topics?: MajorTopicSpotlight[]
    }>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
    let archivedTopics = Array.isArray(res.archived_topics) ? res.archived_topics : []
    if (archivedTopics.length === 0) {
      try {
        const hist = await fetchJson<{ archived_topics?: MajorTopicSpotlight[] }>('data/topics_history.json', {
          noStore: true,
          cacheBust: forceFresh,
        })
        if (Array.isArray(hist.archived_topics)) {
          archivedTopics = hist.archived_topics
        }
      } catch {
        // Optional history archive file
      }
    }
    return {
      generated_at: res.generated_at || '',
      topics: Array.isArray(res.topics) ? res.topics : [],
      archived_topics: archivedTopics,
    }
  } catch {
    return { generated_at: '', topics: [], archived_topics: [] }
  }
}

export async function fetchAiProgress(manifest?: ManifestV2 | null, forceFresh = false): Promise<AiProgressDoc | null> {
  const path = manifest?.v3?.ai_progress_path || 'data/ai_progress.json'
  try {
    return await fetchJson<AiProgressDoc>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
  } catch {
    return null
  }
}

export async function fetchAiProgressArchive(manifest?: ManifestV2 | null, forceFresh = false): Promise<AiProgressDoc | null> {
  const path = (manifest?.v3 as Record<string, unknown> | undefined)?.ai_progress_archive_path as string | undefined
  try {
    return await fetchJson<AiProgressDoc>(path || 'data/ai_progress_archive.json', {
      noStore: true,
      cacheBust: forceFresh,
    })
  } catch {
    return null
  }
}

export async function fetchFinanceImpact(manifest?: ManifestV2 | null, forceFresh = false): Promise<FinanceImpactDoc | null> {
  const path = manifest?.v3?.finance_impact_path || 'data/finance_impact.json'
  try {
    return await fetchJson<FinanceImpactDoc>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
  } catch {
    return null
  }
}

export async function fetchLiveWire(manifest?: ManifestV2 | null, forceFresh = false): Promise<import('./types').LiveWireDoc | null> {
  const path = manifest?.v3?.live_wire_path || 'data/live_wire.json'
  try {
    return await fetchJson<import('./types').LiveWireDoc>(path, {
      noStore: true,
      cacheBust: forceFresh,
    })
  } catch {
    return null
  }
}
