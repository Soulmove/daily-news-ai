import { describe, expect, it, vi } from 'vitest'
import {
  buildAndroidDebugUrl,
  clearAndroidAppShellFlag,
  dispatchImportantNewsNotification,
  isAndroidAppShell,
  isImportantPushEnabled,
  setImportantPushEnabled,
} from '../../web/src/core/mobilePush'
import {
  feedDensity,
  isRedUp,
  markAllWireRead,
  markWireRead,
  marketColorMode,
  setFeedDensity,
  setMarketColorMode,
  toggleMarketColorMode,
  wireReadIdSet,
} from '../../web/src/core/uiPrefs'
import { createLiveWireController } from '../../web/src/core/wireStream'
import { centerPillIntoView } from '../../web/src/core/dom'
import { clusterRawPlatforms, computeTitleSimilarity, sanitizeExcerptText } from '../../web/src/core/dedup'
import {
  adaptRawCategoryPlatforms,
  adaptSimulatedComments,
  adaptSmartCategoryDoc,
  normalizeExternalUrl,
  sanitizeExternalUrl,
  unwrapRawDictText,
} from '../../web/src/core/legacyAdapter'
import {
  extractSmartSourceOptions,
  extractTopEntities,
  filterRawClusters,
  filterSmartEvents,
  isEventMuted,
  matchesSmartQuery,
} from '../../web/src/core/search'
import {
  clearLocalResearchState,
  exportAllResearchState,
  exportBookmarksJson,
  exportBookmarksMarkdown,
  importResearchStateJson,
  isEventRead,
  isNewSincePreviousVisit,
  loadAiClientConfig,
  loadBookmarkedEvents,
  loadFavoriteSourceIds,
  loadPortfolioConfig,
  loadPredictionStances,
  loadReadState,
  loadWeeklyHabitState,
  migrateCollidingEventStates,
  readDarkMode,
  resolveReadLaterEventsList,
  saveAiClientConfig,
  saveBookmarkedEvents,
  saveFavoriteSourceIds,
  savePortfolioConfig,
  savePredictionStances,
  saveReadState,
  saveWeeklyHabitState,
  writeDarkMode,
  loadResearchNotes,
  loadStringSetKey,
  saveStringSetKey,
  mergeResearchStateJson,
  type StorageLike,
} from '../../web/src/core/storage'
import { generateCatalystIcs } from '../../web/src/core/ics'
import { answerQuestionBounded } from '../../web/src/core/qa'
import {
  DEFAULT_PAGE_SIZE,
  buildMorningBriefSummary,
  computeLiveDomainLeaderboard,
  computePredictionStats,
  countMatchingNotesForSubject,
  countUpcomingCatalystsWithinHours,
  dedupeVisibleTodayEvents,
  getConfidentEntities,
  getEventRecommendationReasons,
  matchImpactAgainstPortfolio,
  matchesFreshnessBucket,
  matchEventAgainstWatchlist,
  paginateItems,
  selectLeadEventIndex,
  sortEvents,
  matchesWatchKeyword,
} from '../../web/src/core/v3Logic'
import {
  buildThreeColumnPerspectives,
  isOnboardingCompleted,
  resolveMustReadThumbnail,
  setOnboardingCompleted,
  WATCHLIST_PRESETS,
} from '../../web/src/core/thumbnails'
import {
  computeEchoChamberReport,
  computeWeeklyReadingReport,
  recordEventReadInHistory,
  syncDailyStateToHistory,
} from '../../web/src/core/readingProgress'
import {
  evaluateRawHealth,
  evaluateSmartHealth,
  formatFriendlyBatchId,
  formatRelativeAge,
  formatShanghaiDateTime,
  formatUnifiedTime,
  parseArchiveTimeFromPath,
  parseTimestampMs,
} from '../../web/src/core/time'
import {
  applyEditorialOverridesToEvents,
  applyEditorialOverridesToWire,
  titleFingerprint,
} from '../../web/src/core/overrides'
import { extractHeadlineQualifiers, resolveEvidenceTierBadge } from '../../web/src/core/evidence'
import { iconSvg, stripEmoji } from '../../web/src/core/icons'
import {
  getTodayShanghaiDate,
  loadDailyReadingState,
  recordTodayReadEvents,
  saveDailyReadingState,
} from '../../web/src/core/readingProgress'
import type { CatalystEvent, PredictionRecord, RawPlatform, SmartEvent, WatchlistItem } from '../../web/src/core/types'
import {
  buildBriefingUrl,
  buildMonitorUrl,
  hasInvalidBriefingUrlParams,
  parseBriefingUrlState,
  parseMonitorUrlState,
} from '../../web/src/core/urlState'
import {
  appLang,
  formatWireHeadline,
  pickBiText,
  sanitizeEnText,
  setAppLang,
  stripMarkdownArtifacts,
  translateEntityName,
  translatePortfolioSector,
  translateSourceName,
  translateTagLabel,
  truncateAtSentence,
} from '../../web/src/core/i18n'

function createMemoryStorage(initial: Record<string, string> = {}): StorageLike {
  const store = new Map(Object.entries(initial))
  return {
    getItem: (k) => store.get(k) ?? null,
    setItem: (k, v) => {
      store.set(k, v)
    },
  }
}

describe('time utilities', () => {
  it('parses UTC ISO and naive timestamps as Asia/Shanghai consistently', () => {
    const utcMs = parseTimestampMs('2026-11-15T07:26:00Z')
    const cstMs = parseTimestampMs('2026-11-15T15:26:00+08:00')
    const naiveMs = parseTimestampMs('2026-11-15 15:26:00')
    expect(utcMs).not.toBeNull()
    expect(utcMs).toBe(cstMs)
    expect(cstMs).toBe(naiveMs)
    expect(formatShanghaiDateTime('2026-11-15T07:26:00Z')).toBe('2026-11-15 15:26')
    expect(formatShanghaiDateTime(null)).toBe('时间未知')
  })

  it('keeps old data showing actual age instead of just now on page refresh', () => {
    const fetchedIso = '2026-11-15T10:00:00+08:00'
    const fiveHoursLater = Date.parse('2026-11-15T15:30:00+08:00')
    expect(formatRelativeAge(fetchedIso, fiveHoursLater)).toBe('5 小时前')

    const u5h = formatUnifiedTime(fetchedIso, fiveHoursLater)
    expect(u5h.text).toBe('5 小时前 (10:00 发布)')
    expect(u5h.title).toBe('原文发布 2026-11-15 10:00 CST')

    const twoDaysLater = Date.parse('2026-11-17T10:00:00+08:00')
    expect(formatUnifiedTime(fetchedIso, twoDaysLater).text).toBe('11-15 10:00')

    const crossYear = Date.parse('2027-01-05T10:00:00+08:00')
    expect(formatUnifiedTime(fetchedIso, crossYear).text).toBe('2026-11-15 10:00')

    const staleHealth = evaluateRawHealth(fetchedIso, fiveHoursLater, 30, { isHistory: false })
    expect(staleHealth.level).toBe('stale')
    expect(staleHealth.label).toContain('滞后')

    const historyHealth = evaluateRawHealth(fetchedIso, fiveHoursLater, 30, { isHistory: true })
    expect(historyHealth.level).toBe('history')
    expect(historyHealth.detail).toContain('2026-11-15 10:00')
  })

  it('evaluates smart briefing fallback and parses archive path time', () => {
    expect(parseArchiveTimeFromPath('archives/smart/2026-11-15/19-42/')).toBe(
      '2026-11-15T19:42:00+08:00',
    )
    const h = evaluateSmartHealth('2026-11-15T19:42:00+08:00', Date.parse('2026-11-15T20:00:00+08:00'), {
      isHistory: false,
      hasFallbackCat: true,
    })
    expect(h.level).toBe('partial')
    expect(h.label).toContain('上次成功')
  })
})

describe('legacyAdapter and source URL hygiene', () => {
  it('blocks placeholder #, javascript:, and xueqiu stock ticker URLs', () => {
    expect(sanitizeExternalUrl('#')).toBeNull()
    expect(sanitizeExternalUrl('')).toBeNull()
    expect(sanitizeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(sanitizeExternalUrl('https://xueqiu.com/s/NVDA')).toBeNull()
    expect(sanitizeExternalUrl('https://wallstreetcn.com/')).toBeNull()
    expect(sanitizeExternalUrl('https://wallstreetcn.com/articles/3750001')).toBe(
      'https://wallstreetcn.com/articles/3750001',
    )
  })

  it('adapts legacy V1 smart docs without inventing fake links', () => {
    const legacyV1 = {
      date: '2026-11-15 10:19',
      summary: '【宏观观察】(1) 市场关注通胀预期变化。',
      items: [
        {
          title: '英伟达财报预期升温',
          summary: '多家机构上调数据中心收入预期。',
          source: '华尔街见闻',
          url: '#',
          confidence: 95,
          special_note: '仅基于热榜标题整理',
        },
        {
          title: '央行公开市场操作保持平稳',
          summary: '本周流动性投放维持稳健。',
          source: '财联社电报',
          url: 'https://www.cls.cn/detail/1988888',
        },
      ],
    }

    const adapted = adaptSmartCategoryDoc(legacyV1, 'finance', 'archives/smart/2026-11-15/10-19/')
    expect(adapted.schema_version).toBe('1.0-adapted')
    expect(adapted.events).toHaveLength(2)
    // First event had '#' URL -> marked needs_verification, zero '#' URLs preserved
    expect(adapted.events[0].sources).toHaveLength(0)
    expect(adapted.events[0].evidence_status).toBe('needs_verification')
    // Second event kept verified URL
    expect(adapted.events[1].sources[0].url).toBe('https://www.cls.cn/detail/1988888')
    expect(adapted.events[1].evidence_status).toBe('single_source')
  })

  it('enforces batch consistency when loading simulated comments', () => {
    const mismatch = adaptSimulatedComments(
      {
        date: '2026-11-15 10:29',
        comments: [{ role: '路人甲', emotion: '乐观', content: '上午看法' }],
      },
      'finance',
      'smart-20261115-194200',
      '2026-11-15T19:42:00+08:00',
    )
    expect(mismatch.status).toBe('batch_mismatch')
    expect(mismatch.comments).toHaveLength(0)

    const matched = adaptSimulatedComments(
      {
        schema_version: '2.0',
        batch_id: 'smart-20261115-194200',
        generated_at: '2026-11-15T19:42:00+08:00',
        status: 'ok',
        comments: [{ id: 'c1', role: '产业分析师', perspective_tag: '基本面', content: '关注算力供给。', stance: 'neutral' }],
      },
      'tech',
      'smart-20261115-194200',
      '2026-11-15T19:42:00+08:00',
    )
    expect(matched.status).toBe('ok')
    expect(matched.comments).toHaveLength(1)
  })
})

describe('deduplication and full-text search', () => {
  it('merges duplicate URLs and high-similarity events across platforms', () => {
    const rawArray = [
      {
        id: 'wallstreetcn-news',
        name: '华尔街见闻 · 资讯',
        items: [
          {
            id: 'a1',
            title: '英伟达新一代 Rubin 芯片传出供应链测试新进展',
            url: 'https://wallstreetcn.com/articles/1001?utm_source=feed',
            extra: { hover: '多家供应链厂商反馈测试节奏正常。' },
          },
          {
            id: 'a2',
            title: '黄金期货延续震荡整理',
            url: 'https://wallstreetcn.com/articles/1002',
          },
        ],
      },
      {
        id: 'cls-telegraph',
        name: '财联社 · 电报',
        items: [
          {
            id: 'b1',
            title: '英伟达新一代 Rubin 芯片传出供应链测试最新进展',
            url: 'https://www.cls.cn/detail/2001',
          },
        ],
      },
    ]

    const platforms: RawPlatform[] = adaptRawCategoryPlatforms(
      rawArray,
      'finance',
      '2026-11-15T22:07:21+08:00',
    )
    expect(platforms).toHaveLength(2)

    const clusters = clusterRawPlatforms(platforms, true)
    expect(clusters).toHaveLength(2)
    expect(clusters[0].appearances).toHaveLength(2)
    expect(computeTitleSimilarity(rawArray[0].items[0].title, rawArray[1].items[0].title)).toBeGreaterThan(0.55)

    const nvidiaHits = filterRawClusters(clusters, { query: '英伟达 供应链' })
    expect(nvidiaHits).toHaveLength(1)
  })

  it('searches SmartEvent across title, summary, entities, and sources', () => {
    const events: SmartEvent[] = [
      {
        event_id: 'ev-1',
        title: 'AI 算力资本开支持续上行',
        category: 'tech',
        entities: ['英伟达', '微软'],
        importance: 'high',
        evidence_status: 'multi_source',
        evidence_label: '多源交叉引用',
        evidence_status_reason: '2 个独立平台报道',
        material_depth: 'title_only',
        source_count: 1,
        platform_count: 1,
        published_at: '2026-11-15T18:00:00+08:00',
        fetched_at: '2026-11-15T22:07:21+08:00',
        input_batch_id: 'raw-20261115-220721',
        fact_summary: '云厂商公布季度资本开支安排。',
        ai_analysis: '短中期加速卡需求维持高位。',
        unverified_claims: [],
        speculation_or_outlook: null,
        sources: [
          {
            item_id: 'it-1',
            source_id: 'ithome',
            source_name: 'IT之家',
            source_kind: 'tech_news',
            title: '微软与多家芯片伙伴深化算力部署',
            url: 'https://www.ithome.com/0/888/111.htm',
            published_at: '2026-11-15T18:00:00+08:00',
            fetched_at: '2026-11-15T22:07:21+08:00',
          },
        ],
        followup: null,
        is_new_in_batch: true,
      },
    ]

    const matches = filterSmartEvents(events, { query: '英伟达' })
    expect(matches).toHaveLength(1)
    expect(extractSmartSourceOptions(events)[0].id).toBe('ithome')
    expect(extractTopEntities(events).map((x) => x.entity)).toContain('英伟达')
  })
})

describe('storage compatibility and URL state', () => {
  it('migrates V1 read titles and favorites while tracking V2 bookmarks and visit delta', () => {
    const storage = createMemoryStorage({
      readItems: JSON.stringify(['旧版已读标题']),
      favorites: JSON.stringify(['cls-telegraph']),
    })

    const { readIds, legacyReadTitles } = loadReadState(storage)
    expect(isEventRead({ event_id: 'ev-99', title: '旧版已读标题' }, readIds, legacyReadTitles)).toBe(true)

    readIds.add('ev-100')
    saveReadState(readIds, legacyReadTitles, storage)
    const reloaded = loadReadState(storage)
    expect(reloaded.readIds.has('ev-100')).toBe(true)

    const favs = loadFavoriteSourceIds(storage)
    expect(favs.has('cls-telegraph')).toBe(true)
    favs.add('ithome')
    saveFavoriteSourceIds(favs, storage)
    expect(loadFavoriteSourceIds(storage).has('ithome')).toBe(true)

    saveBookmarkedEvents(
      [
        {
          event_id: 'ev-100',
          title: '收藏测试事件',
          url: 'https://www.ithome.com/0/1/2.htm',
          category: 'tech',
          source_name: 'IT之家',
          batch_id: 'smart-20261115-194200',
          saved_at: '2026-11-15T22:00:00+08:00',
        },
      ],
      storage,
    )
    expect(loadBookmarkedEvents(storage)).toHaveLength(1)

    expect(
      isNewSincePreviousVisit(
        { event_id: 'ev-new', is_new_in_batch: false },
        new Set(['ev-old']),
        'smart-20261115-101900',
      ),
    ).toBe(true)
  })

  it('serializes and parses Briefing & Monitor URL states cleanly and blocks path traversal', () => {
    const briefingUrl = buildBriefingUrl(
      {
        tab: 'briefing',
        cat: 'tech',
        history: 'archives/smart/2026-11-15/19-42/',
        event: 'ev-123',
        story: null,
        entity: null,
        fresh: 'all',
        q: '英伟达',
        scope: 'all',
        source: 'ithome',
        evidence: 'multi_source',
        unread: true,
      },
      '/daily-news-ai/index.html',
    )
    const qs = briefingUrl.split('?')[1]
    const parsed = parseBriefingUrlState(`?${qs}`)
    expect(parsed.cat).toBe('tech')
    expect(parsed.history).toBe('archives/smart/2026-11-15/19-42/')
    expect(parsed.event).toBe('ev-123')
    expect(parsed.q).toBe('英伟达')
    expect(parsed.scope).toBe('all')
    expect(parsed.unread).toBe(true)

    const unsafe = parseBriefingUrlState('?history=../../etc/passwd')
    expect(unsafe.history).toBeNull()

    const monitorUrl = buildMonitorUrl(
      {
        cat: 'favorites',
        history: null,
        view: 'connectors',
        q: '快讯',
        source: 'all',
        health: 'issue',
      },
      '/daily-news-ai/monitor.html',
    )
    const parsedMonitor = parseMonitorUrlState(`?${monitorUrl.split('?')[1]}`)
    expect(parsedMonitor.cat).toBe('favorites')
    expect(parsedMonitor.view).toBe('connectors')
    expect(parsedMonitor.health).toBe('issue')

    const v3Url = buildBriefingUrl(
      {
        tab: 'tracking',
        cat: 'finance',
        history: null,
        event: null,
        story: 'st_nvda_blackwell',
        entity: 'ent_nvidia',
        fresh: 'first_discovery',
        q: '',
        scope: 'current',
        source: 'all',
        evidence: 'all',
        unread: false,
      },
      '/daily-news-ai/index.html',
    )
    const parsedV3 = parseBriefingUrlState(`?${v3Url.split('?')[1]}`)
    expect(parsedV3.tab).toBe('tracking')
    expect(parsedV3.story).toBe('st_nvda_blackwell')
    expect(parsedV3.entity).toBe('ent_nvidia')
    expect(parsedV3.fresh).toBe('first_discovery')
  })
})

describe('V3 research workbench core logic', () => {
  it('migrates colliding omnibus legacy event_ids independently by exact title', () => {
    const storage = createMemoryStorage()
    const collidingEvents = [
      { event_id: 'evt_alpha_1111', title: '存储芯片报价大幅上涨', legacy_event_ids: ['evt_a9d2aca38270'] },
      { event_id: 'evt_beta_2222', title: '光伏组件排产维持低位', legacy_event_ids: ['evt_a9d2aca38270'] },
    ]
    const initialRead = new Set(['evt_a9d2aca38270'])
    const initialBm = [
      {
        event_id: 'evt_a9d2aca38270',
        title: '存储芯片报价大幅上涨',
        url: 'https://wallstreetcn.com/articles/1',
        category: 'finance' as const,
        source_name: '华尔街见闻',
        batch_id: 'smart-1',
        saved_at: '2026-11-15T10:00:00+08:00',
      },
    ]

    const res = migrateCollidingEventStates(collidingEvents, initialRead, initialBm, storage)
    expect(res.migrated).toBe(true)
    expect(res.bookmarks[0].event_id).toBe('evt_alpha_1111')
    expect(res.readIds.has('evt_alpha_1111')).toBe(true)
    expect(res.readIds.has('evt_beta_2222')).toBe(false)
    expect(res.readIds.has('evt_a9d2aca38270')).toBe(false)
  })

  it('matches watchlist triggers with clear reasons, handles mute/downweight, and isolates freshness buckets', () => {
    const baseEvent: SmartEvent = {
      event_id: 'ev_mem_1',
      storyline_id: 'st_mem_1',
      title: '美光与 SK 海力士披露 HBM3E 新一代存储芯片产能规划',
      category: 'tech',
      entities: ['美光', 'SK海力士'],
      entity_ids: ['ent_memory_chips'],
      importance: 'high',
      evidence_status: 'official_confirmed',
      evidence_label: '一手官方/披露已证实',
      evidence_status_reason: 'SEC 文件核验',
      material_depth: 'article_excerpt',
      source_count: 2,
      platform_count: 2,
      independent_publisher_count: 2,
      update_kind: 'new_discovery',
      published_at: '2026-11-15T18:00:00+08:00',
      fetched_at: '2026-11-15T18:10:00+08:00',
      input_batch_id: 'raw-1',
      fact_summary: '存储芯片现货及 HBM 需求维持紧平衡。',
      ai_analysis: '高带宽内存仍是算力供应链核心环节。',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    }

    const watchlist: WatchlistItem[] = [
      {
        id: 'wl_1',
        kind: 'industry',
        label: '存储芯片',
        entity_id: 'ent_memory_chips',
        keywords: ['存储芯片', 'hbm'],
        created_at: '2026-11-15T00:00:00+08:00',
      },
    ]

    const hit = matchEventAgainstWatchlist(baseEvent, watchlist)
    expect(hit.matched).toBe(true)
    expect(hit.matchReasons[0]).toContain('存储芯片')
    expect(hit.score).toBeGreaterThan(50)

    const muted = matchEventAgainstWatchlist(baseEvent, watchlist, new Set(['st_mem_1']))
    expect(muted.muted).toBe(true)
    expect(muted.matched).toBe(false)

    // Strict separation: first_discovery vs old_progress vs unread
    expect(matchesFreshnessBucket(baseEvent, 'first_discovery', new Set(), new Set())).toBe(true)
    expect(matchesFreshnessBucket(baseEvent, 'old_progress', new Set(), new Set())).toBe(false)
    expect(matchesFreshnessBucket(baseEvent, 'unread', new Set(['ev_mem_1']), new Set())).toBe(false)

    const continuingEv: SmartEvent = {
      ...baseEvent,
      event_id: 'ev_mem_2',
      update_kind: 'new_fact_update',
      followup: { is_continuing: true, prev_batch_id: 'smart-0', delta_note: '新披露细节' },
    }
    expect(matchesFreshnessBucket(continuingEv, 'first_discovery', new Set(), new Set())).toBe(false)
    expect(matchesFreshnessBucket(continuingEv, 'old_progress', new Set(), new Set())).toBe(true)
  })

  it('separates live vs replay prediction calibration stats and excludes indeterminate from hit rate', () => {
    const mkRec = (
      id: string,
      mode: 'live' | 'replay',
      status: 'open' | 'settled',
      outcome?: 'correct' | 'incorrect' | 'indeterminate',
      prob = 70,
    ): PredictionRecord => ({
      prediction_id: id,
      mode,
      status,
      title: id,
      question: '?',
      created_at: '2026-11-15T00:00:00+08:00',
      due_at: '2026-11-30T00:00:00+08:00',
      win_rule: 'w',
      lose_rule: 'l',
      supporting_evidence: [],
      opposing_evidence: [],
      core_assumption: 'a',
      invalidation_trigger: 'i',
      probability_pct: prob,
      current_judgment: 'j',
      versions: [],
      settlement: outcome
        ? { outcome, settled_at: '2026-11-16T00:00:00+08:00', note: 'n' }
        : null,
    })

    const stats = computePredictionStats([
      mkRec('l1', 'live', 'settled', 'correct', 80),
      mkRec('l2', 'live', 'settled', 'incorrect', 60),
      mkRec('l3', 'live', 'settled', 'indeterminate', 50),
      mkRec('r1', 'replay', 'settled', 'correct', 90),
    ])

    expect(stats.live.total).toBe(3)
    expect(stats.live.indeterminateCount).toBe(1)
    expect(stats.live.decisiveHitRatePct).toBe(50)
    expect(stats.live.brierScore).toBeCloseTo(((0.8 - 1) ** 2 + (0.6 - 0) ** 2) / 2, 3)

    expect(stats.replay.total).toBe(1)
    expect(stats.replay.decisiveHitRatePct).toBe(100)
  })

  it('generates valid RFC 5545 .ics calendar skipping TBD dates and bounds Evidence Q&A output', () => {
    const events: CatalystEvent[] = [
      {
        calendar_id: 'cal_fomc_nov',
        title: 'FOMC 利率决议公布',
        scheduled_at: '2026-11-18T03:00:00+08:00',
        timezone: 'Asia/Shanghai',
        certainty: 'confirmed_official',
        certainty_label: '官方已排期',
        category: 'global',
        entity_ids: ['ent_fed'],
        watch_variable: '联邦基金目标利率区间',
        source_name: 'Federal Reserve',
        source_url: 'https://www.federalreserve.gov/newsevents/pressreleases.htm',
      },
      {
        calendar_id: 'cal_tbd',
        title: '待定日程',
        scheduled_at: null,
        timezone: 'Asia/Shanghai',
        certainty: 'tbd',
        certainty_label: '待定',
        category: 'tech',
        entity_ids: [],
        watch_variable: '版本发布',
        source_name: 'GitHub',
        source_url: null,
      },
    ]

    const ics = generateCatalystIcs(events)
    expect(ics).toContain('BEGIN:VCALENDAR')
    expect(ics).toContain('UID:cal_fomc_nov@insightpro.local')
    expect(ics).toContain('SUMMARY:FOMC 利率决议公布')
    expect(ics).not.toContain('cal_tbd@insightpro.local')

    const titleOnlyEvent: SmartEvent = {
      event_id: 'ev_title_only',
      title: '某型号芯片测试消息',
      category: 'tech',
      entities: [],
      importance: 'medium',
      evidence_status: 'single_source',
      evidence_label: '单一来源线索',
      evidence_status_reason: 'rss',
      material_depth: 'title_only',
      source_count: 1,
      platform_count: 1,
      published_at: null,
      fetched_at: '2026-11-15T22:00:00+08:00',
      input_batch_id: 'raw-1',
      fact_summary: '热榜标题摘要',
      ai_analysis: '暂无深度正文',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [
        {
          item_id: 'it_1',
          source_id: 'ithome',
          source_name: 'IT之家',
          source_kind: 'tech_news',
          title: '某型号芯片测试消息',
          url: 'https://www.ithome.com/0/1/1.htm',
          published_at: null,
          fetched_at: '2026-11-15T22:00:00+08:00',
        },
      ],
      followup: null,
      is_new_in_batch: true,
    }

    const qa = answerQuestionBounded('可靠吗？', { event: titleOnlyEvent, dataCutoffAt: '2026-11-15T22:00:00+08:00' })
    expect(qa.evidenceUrls).toHaveLength(1)
    expect(qa.missingDisclosures.some((m) => m.includes('仅含热榜标题'))).toBe(true)
  })

  it('prioritizes fresh morning news over multi-day stale title-only rumors in TodayView', () => {
    const baseNow = Date.parse('2026-11-16T11:20:00+08:00')
    const wl = [
      {
        id: 'w1',
        kind: 'company' as const,
        label: '英伟达',
        entity_id: 'ent_nvidia',
        keywords: ['英伟达', 'nvidia'],
        created_at: '2026-11-15T20:00:00+08:00',
      },
    ]
    const freshMorning: SmartEvent = {
      event_id: 'evt_fresh',
      storyline_id: 'st_fresh',
      title: '摩根士丹利评估英伟达供应链最新指引',
      category: 'finance',
      entities: ['英伟达'],
      entity_ids: ['ent_nvidia'],
      importance: 'high',
      evidence_status: 'multi_source',
      evidence_label: '多独立源',
      evidence_status_reason: '2 sources',
      material_depth: 'body_lead_extracted',
      source_count: 2,
      platform_count: 2,
      published_at: '2026-11-16T09:24:00+08:00',
      first_reported_at: '2026-11-16T09:24:00+08:00',
      fetched_at: '2026-11-16T10:36:00+08:00',
      input_batch_id: 'raw-1',
      fact_summary: '完整导语摘要。',
      ai_analysis: '解读。',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    }
    const staleRumor: SmartEvent = {
      ...freshMorning,
      event_id: 'evt_stale_rumor',
      storyline_id: 'st_stale',
      title: '报道称：英伟达某陈年绯闻与丑闻',
      material_depth: 'title_only',
      published_at: '2026-11-13T16:33:00+08:00',
      first_reported_at: '2026-11-13T16:33:00+08:00',
      attribution_warning: '未获官方证实',
    }

    const freshScore = matchEventAgainstWatchlist(freshMorning, wl, new Set(), new Set(), baseNow)
    const staleScore = matchEventAgainstWatchlist(staleRumor, wl, new Set(), new Set(), baseNow)
    expect(freshScore.score).toBeGreaterThan(staleScore.score)
  })

  it('answers built-in presets and natural Chinese queries in Global Evidence QA mode without false misses', () => {
    const evs: SmartEvent[] = [
      {
        event_id: 'evt_nvda_ceo',
        storyline_id: 'st_nvda_ceo',
        title: '报道称：英伟达CEO继任不确定性引发市场关注',
        category: 'finance',
        entities: ['英伟达', '黄仁勋'],
        importance: 'high',
        evidence_status: 'multi_source',
        evidence_label: '多独立来源提及',
        evidence_status_reason: '2 sources',
        material_depth: 'body_lead_extracted',
        source_count: 2,
        platform_count: 2,
        published_at: '2026-11-16T08:30:00+08:00',
        fetched_at: '2026-11-16T10:36:00+08:00',
        input_batch_id: 'raw-1',
        fact_summary: '财联社与华尔街见闻关注英伟达高管继任讨论，尚未见 SEC 8-K 公告证实。',
        ai_analysis: '关注公司治理溢价变化。',
        unverified_claims: ['继任人选尚未官宣'],
        contradictions: ['SEC 8-K 尚未见高管离职 Item 5.02 披露'],
        attribution_warning: '未获官方证实',
        speculation_or_outlook: '观察下一次 SEC 8-K 与财报电话会回应',
        sources: [{ item_id: 's1', source_id: 'cls-depth', source_name: '财联社', source_kind: 'news', title: '英伟达回应', url: 'https://www.cls.cn/1', published_at: '2026-11-16T08:30:00+08:00', fetched_at: '2026-11-16T10:36:00+08:00' }],
        followup: null,
        is_new_in_batch: true,
      },
      {
        event_id: 'evt_nvda_dup',
        storyline_id: 'st_nvda_ceo',
        title: '报道称：英伟达CEO继任不确定性引发市场关注（重发）',
        category: 'tech',
        entities: ['英伟达'],
        importance: 'medium',
        evidence_status: 'single_source',
        evidence_label: '单一独立来源',
        evidence_status_reason: '1 source',
        material_depth: 'title_only',
        source_count: 1,
        platform_count: 1,
        published_at: '2026-11-16T09:00:00+08:00',
        fetched_at: '2026-11-16T10:36:00+08:00',
        input_batch_id: 'raw-1',
        fact_summary: '同主线事件测试。',
        ai_analysis: '解读。',
        unverified_claims: [],
        speculation_or_outlook: null,
        sources: [],
        followup: null,
        is_new_in_batch: true,
      },
    ]

    for (const preset of [
      '近7天有哪些核心变化？',
      '主要正反依据和分歧在哪里？',
      '证伪条件与下个验证节点是什么？',
      '英伟达黄仁勋继任现在什么情况？',
    ]) {
      const qa = answerQuestionBounded(preset, { allEvents: evs, dataCutoffAt: '2026-11-16T10:36:00+08:00' })
      expect(qa.answerMarkdown).not.toContain('未在当前已加载素材中检索到')
      expect(qa.evidenceUrls.length).toBeGreaterThan(0)
    }

    const deduped = dedupeVisibleTodayEvents(evs, true)
    expect(deduped).toHaveLength(1)
  })

  it('sanitizes HTML excerpt tags and performs symmetric full JSON import/clear while keeping darkMode', () => {
    expect(sanitizeExcerptText('<br/><span class="section-news">通胀数据 &amp; 央行纪要</span>')).toBe(
      '通胀数据 & 央行纪要',
    )

    const mem = new Map<string, string>()
    const store: StorageLike & { removeItem(k: string): void } = {
      getItem: (k) => mem.get(k) ?? null,
      setItem: (k, v) => mem.set(k, v),
      removeItem: (k) => {
        mem.delete(k)
      },
    }

    writeDarkMode(true, store)
    saveReadState(new Set(['evt_1']), new Set(['Old Title']), store)
    saveFavoriteSourceIds(new Set(['cls-depth']), store)
    const payloadJson = JSON.stringify({
      schema_version: '3.0',
      watchlist: [
        {
          id: 'wl_custom',
          kind: 'company',
          label: 'TSMC',
          keywords: ['台积电'],
          created_at: '2026-11-16T00:00:00+08:00',
        },
      ],
      hide_reprints: false,
      read_ids: ['evt_1', 'evt_2'],
      favorite_sources: ['cls-depth'],
      custom_catalysts: [
        {
          calendar_id: 'cal_custom_1',
          title: 'Test Custom',
          scheduled_at: '2026-11-25T20:00:00+08:00',
          timezone: 'Asia/Shanghai',
          certainty: 'confirmed_official',
          certainty_label: '自建已排期',
          category: 'custom',
          entity_ids: [],
          watch_variable: 'Margin',
          source_name: '本地',
          source_url: null,
          is_custom: true,
        },
      ],
      predictions: [],
    })

    const res = importResearchStateJson(payloadJson, store)
    expect(res.ok).toBe(true)
    expect(loadReadState(store).readIds.has('evt_2')).toBe(true)
    expect(loadFavoriteSourceIds(store).has('cls-depth')).toBe(true)
    const exported = JSON.parse(exportAllResearchState(store))
    expect(exported.hide_reprints).toBe(false)
    expect(exported.custom_catalysts).toHaveLength(1)

    clearLocalResearchState(store)
    expect(readDarkMode(store)).toBe(true)
    expect(loadReadState(store).readIds.size).toBe(0)

    // Verify BYOK AI API key is preserved on local reset and NEVER leaked into exported JSON backups
    saveAiClientConfig({ provider: 'gemini', apiKey: 'AIzaSecretTestKey', model: 'gemini-4-hydrogen', baseUrl: '' }, store)
    const exportedSafe = exportAllResearchState(store)
    expect(exportedSafe).not.toContain('AIzaSecretTestKey')
    clearLocalResearchState(store)
    expect(loadAiClientConfig(store).apiKey).toBe('AIzaSecretTestKey')

    // Verify local QA matches Major Topic Spotlights & itinerary queries cleanly
    const qaTopic = answerQuestionBounded('特朗普这次来中国的行程是什么？', {
      allEvents: [],
      topics: [
        {
          topic_id: 'topic_apec_trump_china',
          title: '特朗普访华与 2026 深圳 APEC 峰会实时行程专题',
          subtitle: '抵深接机与三边会晤',
          badge: '超级专题',
          category: 'global',
          updated_at: '2026-11-19T10:00:00+08:00',
          total_mentions: 10,
          source_count: 5,
          event_ids: [],
          timeline: [
            {
              time: '2026-11-18T18:30:00+08:00',
              stage_tag: '抵访接待',
              title: '习近平亲赴深圳机场迎接特朗普',
              summary: '罕见高规格接机仪式',
              source_name: '联合早报',
              url: 'https://www.zaobao.com/news/1',
              event_id: null,
            },
          ],
        },
      ],
      dataCutoffAt: '2026-11-19T12:00:00+08:00',
    })
    expect(qaTopic.answerMarkdown).toContain('习近平亲赴深圳机场迎接特朗普')
    expect(qaTopic.evidenceUrls.length).toBeGreaterThan(0)
  })
})

describe('Phase B URL whitelist & daily reading progress helpers', () => {
  it('flags invalid or redundant briefing URL params cleanly', () => {
    expect(hasInvalidBriefingUrlParams('?tab=xxx')).toBe(true)
    expect(hasInvalidBriefingUrlParams('?tab=today')).toBe(true)
    expect(hasInvalidBriefingUrlParams('?tab=finance')).toBe(false)
    expect(hasInvalidBriefingUrlParams('?tab=calendar&q=fed')).toBe(false)
    expect(hasInvalidBriefingUrlParams('?cat=invalid_cat')).toBe(true)
    expect(hasInvalidBriefingUrlParams('')).toBe(false)
    expect(parseBriefingUrlState('?tab=xxx').tab).toBe('today')
  })

  it('tracks daily read events and resets across midnight Asia/Shanghai without anti-addiction timer', () => {
    const store = createMemoryStorage()
    const day1Morning = Date.parse('2026-11-19T09:15:00+08:00')
    expect(getTodayShanghaiDate(day1Morning)).toBe('2026-11-19')

    let st = loadDailyReadingState(day1Morning, store)
    expect(st.readEventIdsToday).toEqual([])

    st = recordTodayReadEvents(st, ['evt_1', 'evt_2'], true, day1Morning, store)
    expect(st.readEventIdsToday).toEqual(['evt_1', 'evt_2'])

    // Same day reload preserves readEventIdsToday
    const reloadedSameDay = loadDailyReadingState(day1Morning + 3600_000, store)
    expect(reloadedSameDay.readEventIdsToday).toEqual(['evt_1', 'evt_2'])

    // Next day 00:01 Asia/Shanghai resets readEventIdsToday cleanly
    const day2AfterMidnight = Date.parse('2026-11-20T00:01:00+08:00')
    const resetNextDay = loadDailyReadingState(day2AfterMidnight, store)
    expect(resetNextDay.date).toBe('2026-11-20')
    expect(resetNextDay.readEventIdsToday).toEqual([])
  })
})

describe('Phase C features: sorting, pagination, confidence, weekly report, echo-chamber, thumbnails & bookmarks', () => {
  it('sorts by latest/credibility/relevance and paginates 20 items per page (C2 & C4 & C7)', () => {
    const mkEv = (idx: number, status: SmartEvent['evidence_status'], title: string): SmartEvent => ({
      event_id: `ev_${idx}`,
      title,
      category: 'tech',
      entities: ['英伟达', '边缘噪点词'],
      entity_confidences: { 英伟达: 0.92, 边缘噪点词: 0.42 },
      importance: idx === 1 ? 'high' : 'normal',
      evidence_status: status,
      evidence_label: status,
      evidence_status_reason: 'ok',
      material_depth: 'full',
      source_count: status === 'official_confirmed' ? 4 : 1,
      platform_count: 1,
      published_at: `2026-11-20T${String(idx % 24).padStart(2, '0')}:00:00+08:00`,
      fetched_at: '2026-11-20T18:00:00+08:00',
      input_batch_id: 'b1',
      fact_summary: title,
      ai_analysis: '加速算力需求落地，但需留意库存波动。',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    })

    const list = Array.from({ length: 25 }, (_, i) =>
      mkEv(i, i === 5 ? 'official_confirmed' : 'single_source', i === 3 ? 'Nvidia Blackwell' : `Event ${i}`),
    )

    const byCred = sortEvents(list, 'credibility')
    expect(byCred[0].event_id).toBe('ev_5')

    const byRel = sortEvents(list, 'relevance', [
      { id: 'w1', kind: 'company', label: 'Nvidia', keywords: ['nvidia'], created_at: '' },
    ])
    expect(byRel[0].event_id).toBe('ev_3')

    const page1 = paginateItems(byCred, DEFAULT_PAGE_SIZE)
    expect(page1.visible).toHaveLength(20)
    expect(page1.hasMore).toBe(true)
    expect(page1.remaining).toBe(5)

    const confident = getConfidentEntities(list[0].entities, list[0].entity_confidences)
    expect(confident.map((x) => x.name)).toEqual(['英伟达'])

    const reasons = getEventRecommendationReasons(list[5], [
      { id: 'w1', kind: 'company', label: '英伟达', keywords: ['英伟达'], created_at: '' },
    ])
    expect(reasons.some((r) => r.includes('一手官方证实'))).toBe(true)
  })

  it('tracks 7-day reading history and echo-chamber balance score (C8)', () => {
    const store = createMemoryStorage()
    const nowMs = Date.parse('2026-11-20T15:00:00+08:00')

    const daily = loadDailyReadingState(nowMs, store)
    saveDailyReadingState(daily, store)
    syncDailyStateToHistory(daily, nowMs, store)

    // Skewed reading: 4 finance reads, 0 global/tech/general -> echo_risk
    for (let i = 0; i < 4; i += 1) {
      recordEventReadInHistory(
        { event_id: `fin_${i}`, category: 'finance', entities: ['美联储'] },
        nowMs,
        store,
      )
    }

    const report = computeWeeklyReadingReport(nowMs, store)
    expect(report.totalReadCount).toBe(4)

    const echoSkewed = computeEchoChamberReport(nowMs, store)
    expect(echoSkewed.status).toBe('echo_risk')
    expect(echoSkewed.diversityScore).toBe(0)
    expect(echoSkewed.blindspotCategories).toContain('tech')

    // Diverse reading raises diversityScore cleanly
    recordEventReadInHistory({ event_id: 'g1', category: 'global', entities: ['APEC'] }, nowMs, store)
    recordEventReadInHistory({ event_id: 't1', category: 'tech', entities: ['Nvidia'] }, nowMs, store)
    recordEventReadInHistory({ event_id: 'gen1', category: 'general', entities: [] }, nowMs, store)
    const echoDiverse = computeEchoChamberReport(nowMs, store)
    expect(echoDiverse.diversityScore).toBeGreaterThan(70)
  })

  it('resolves Top-3 Must-Read thumbnails only, presets, 3 perspectives, portfolio & bookmarks export (C6–C9)', () => {
    const store = createMemoryStorage()
    expect(isOnboardingCompleted(store)).toBe(false)
    setOnboardingCompleted(true, store)
    expect(isOnboardingCompleted(store)).toBe(true)
    expect(WATCHLIST_PRESETS.length).toBe(3)

    const ev: SmartEvent = {
      event_id: 'top1',
      title: 'APEC summit diplomatic talks open in Shenzhen',
      category: 'global',
      entities: [],
      importance: 'high',
      evidence_status: 'official_confirmed',
      evidence_label: '一手证实',
      evidence_status_reason: 'Official press conference',
      material_depth: 'full',
      source_count: 3,
      platform_count: 3,
      published_at: '2026-11-20T12:00:00+08:00',
      fetched_at: '2026-11-20T12:10:00+08:00',
      input_batch_id: 'b1',
      fact_summary: 'Multilateral diplomatic talks.',
      ai_analysis: '外交突破有利于缓解贸易风险。',
      unverified_claims: ['后续关税减免细则待确认'],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    }
    const used = new Set<string>()
    expect(resolveMustReadThumbnail(ev, 0, used)).toBe('./thumbs/top1-apec-summit.webp')
    expect(resolveMustReadThumbnail(ev, 3, used)).toBeNull() // Strictly NO thumbnails on #4+ cards!

    const cols = buildThreeColumnPerspectives(ev)
    expect(cols).toHaveLength(3)
    expect(cols[0].points[0]).toContain('Official press conference')
    expect(cols[2].points[0]).toContain('待证实')

    savePortfolioConfig({ sectors: ['AI 算力 / 半导体'], tickers: ['NVDA'], riskProfile: 'aggressive' }, store)
    expect(loadPortfolioConfig(store).tickers).toEqual(['NVDA'])

    const md = exportBookmarksMarkdown([
      {
        event_id: 'bm_1',
        title: 'Anthropic IPO 募资超 810 亿美元',
        url: 'https://example.com',
        category: 'finance',
        source_name: 'Reuters',
        batch_id: 'b1',
        saved_at: '2026-11-20T12:00:00+08:00',
        tags: ['IPO', 'AI'],
      },
    ])
    expect(md).toContain('[IPO, AI]')
    const jsonTxt = exportBookmarksJson([])
    expect(JSON.parse(jsonTxt).total).toBe(0)
  })

  it('dispatches native Android push notifications once per item and preserves app=android URL state', async () => {
    const notified: Array<{ title: string; body: string; url?: string }> = []
    const prevWin = (globalThis as Record<string, unknown>).window
    const mockStorage = createMemoryStorage()
    ;(globalThis as Record<string, unknown>).window = {
      location: { search: '?app=android&tab=ai_progress', pathname: 'index.html', hostname: '111.230.153.15', protocol: 'https:' },
      localStorage: mockStorage,
      InfoFocusAndroid: {
        notify: (title: string, body: string, url?: string) => notified.push({ title, body, url }),
        isPushEnabled: () => true,
        setPushEnabled: vi.fn(),
        requestPermission: vi.fn(),
      },
    }
    try {
      expect(isImportantPushEnabled()).toBe(true)
      await setImportantPushEnabled(true)
      const ok1 = dispatchImportantNewsNotification({
        id: 'ai_wb_test_1',
        title: '🤖 腾讯混元 · 一手发布',
        body: '腾讯WorkBuddy上线电脑操控能力',
        tab: 'ai_progress',
      })
      const dup = dispatchImportantNewsNotification({
        id: 'ai_wb_test_1',
        title: '🤖 腾讯混元 · 一手发布',
        body: '腾讯WorkBuddy上线电脑操控能力',
        tab: 'ai_progress',
      })
      expect(ok1).toBe(true)
      expect(dup).toBe(false)
      expect(notified).toHaveLength(1)
      expect(notified[0].url).toContain('app=android&tab=ai_progress')

      const urlState = parseBriefingUrlState('?tab=ai_progress')
      expect(buildBriefingUrl(urlState, 'index.html')).toContain('app=android')

      const meState = parseBriefingUrlState('?tab=me')
      expect(meState.tab).toBe('me')
      expect(hasInvalidBriefingUrlParams('?tab=me')).toBe(false)
      expect(buildBriefingUrl(meState, 'index.html')).toContain('tab=me')
    } finally {
      ;(globalThis as Record<string, unknown>).window = prevWin
    }

    // Verify wireStream controller triggers onAiUpdate without browser EventSource
    const aiUpdates: string[][] = []
    const handle = createLiveWireController({
      onUpdate: () => {},
      onAiUpdate: (_doc, newIds) => aiUpdates.push(newIds),
      pollIntervalMs: 60_000,
    })
    handle.seedAiFromDoc({
      schema_version: '4.0',
      generated_at: '2026-11-20T18:00:00+08:00',
      batch_id: 'b1',
      weekly_digest: { period_label: '', summary: '', highlights: [] },
      companies: [],
      timeline: [],
    })
    handle.stop()
    expect(aiUpdates).toHaveLength(0)
  })

  it('guards false keyword matches, cleans Markdown/wire cutoffs, translates EN glossary, and merges cloud state safely', () => {
    // Watchlist substring guard: '1万亿美元' must not hit '美元'; '高盛' must not hit '黄金'
    expect(matchesWatchKeyword('软银计划向sk海力士融资1万亿美元', '美元')).toBe(false)
    expect(matchesWatchKeyword('高盛上调半导体行业目标价', '黄金')).toBe(false)
    expect(matchesWatchKeyword('美元指数走强推动汇率波动', '美元指数')).toBe(true)

    // Markdown table cleanup & sentence/wire truncation with ellipsis
    const stripped = stripMarkdownArtifacts('| Model | TPS |\n| --- | --- |\n| **SGLang** | 1200 |\n[R075] 已拦截 4 条无效引用（域名/行情页）；高吞吐推理引擎。')
    expect(stripped).not.toContain('---')
    expect(stripped).not.toContain('R075')
    expect(stripped).not.toContain('已拦截')
    expect(stripped).toContain('SGLang')

    const wireHead = formatWireHeadline('长江证券：截至2026年11月20日，公司以集中竞价方式累计回购股份948.63万股，占总股本0.17%，最高成交价7.64元/股，最低成交价6.62元/股，支')
    expect(wireHead.endsWith('…')).toBe(true)

    const truncSent = truncateAtSentence('第一句已经正式对外公布了完整结果。第二句补充细节描述非常长导致需要在这里被合理截断。', 30)
    expect(truncSent).toBe('第一句已经正式对外公布了完整结果。')
    const truncDecimal = truncateAtSentence('美联储本周累跌19.2%引发成长板块回调并冲击市场风险偏好。', 18)
    expect(truncDecimal).toContain('19.2%')
    expect(truncDecimal.endsWith('19.')).toBe(false)
    expect(truncateAtSentence('测试摘要（、仅含标题）正文。', 40)).toBe('测试摘要正文。')
    const truncEllipsis = truncateAtSentence('没有任何标点断句的连续超长技术参数说明正在输出之中', 14)
    expect(truncEllipsis.endsWith('…')).toBe(true)

    // EN entity & tag glossary
    setAppLang('en')
    try {
      expect(translateEntityName('英伟达 (NVIDIA)')).toBe('NVIDIA (NVDA)')
      expect(translateTagLabel('利空承压')).toBe('Bearish Pressure')
      expect(translateSourceName('华尔街见闻 7×24 全球')).toBe('WallStreetCN 7×24')
      expect(translatePortfolioSector('AI 算力 / 半导体')).toBe('AI Compute / Semis')
    } finally {
      setAppLang('zh')
    }

    // Bidirectional cloud merge preserves local unsynced bookmarks alongside cloud items
    const store = createMemoryStorage()
    saveBookmarkedEvents(
      [
        {
          event_id: 'local_only_bm',
          title: '本地离线收藏',
          url: 'https://example.com/local',
          category: 'tech',
          source_name: '本地',
          batch_id: 'b1',
          saved_at: '2026-11-20T10:00:00+08:00',
          tags: [],
        },
      ],
      store,
    )
    const mergeRes = mergeResearchStateJson(
      JSON.stringify({
        bookmarks: [
          {
            event_id: 'cloud_bm',
            title: '云端设备收藏',
            url: 'https://example.com/cloud',
            category: 'finance',
            source_name: 'Reuters',
            batch_id: 'b2',
            saved_at: '2026-11-20T11:00:00+08:00',
            tags: ['Fed'],
          },
        ],
      }),
      store,
    )
    expect(mergeRes.ok).toBe(true)
    expect(mergeRes.needsPush).toBe(true)
    expect(loadBookmarkedEvents(store).map((b) => b.event_id).sort()).toEqual(['cloud_bm', 'local_only_bm'])
  })

  it('builds clean Android dev debug URLs and resets shell flag cleanly', () => {
    expect(buildAndroidDebugUrl('today', 'android')).toBe('./index.html?app=android')
    expect(buildAndroidDebugUrl('me', 'android')).toBe('./index.html?tab=me&app=android')
    expect(buildAndroidDebugUrl('finance', 'web')).toBe('./index.html?tab=finance&app=web')
    expect(() => clearAndroidAppShellFlag()).not.toThrow()
    expect(typeof isAndroidAppShell()).toBe('boolean')
  })

  it('defaults feed density to compact and persists wire read state', () => {
    expect(feedDensity.value).toBe('compact')
    setFeedDensity('standard')
    expect(feedDensity.value).toBe('standard')
    setFeedDensity('compact')
    expect(feedDensity.value).toBe('compact')

    markWireRead('wire-item-1')
    expect(wireReadIdSet.value.has('wire-item-1')).toBe(true)
    markAllWireRead(['wire-item-2', 'wire-item-3'])
    expect(wireReadIdSet.value.has('wire-item-2')).toBe(true)
    expect(wireReadIdSet.value.has('wire-item-3')).toBe(true)
  })

  it('prevents false watchlist hits, uses backend radar_score without duplicate penalty, fixes Neon thumb & health lag', () => {
    // 1. SpaceX/Tesla/xAI preset includes xai & grok
    const aiTechPreset = WATCHLIST_PRESETS.find((p) => p.id === 'ai_tech')
    const muskItem = aiTechPreset?.items.find((i) => i.id === 'preset_musk')
    expect(muskItem?.keywords).toContain('xai')
    expect(muskItem?.keywords).toContain('grok')

    // 2. Watchlist precision: ignore ai_analysis/source bloat & non-gold/hormuz false substrings
    const nvdaEv: SmartEvent = {
      event_id: 'ev_nvda_test',
      title: '英伟达单日暴跌 14%，引发美股芯片板块回调',
      category: 'finance',
      entities: ['英伟达 (NVIDIA)'],
      entity_ids: ['ent_nvidia'],
      importance: 'high',
      radar_score: 92,
      evidence_status: 'multi_source',
      evidence_label: '多源',
      evidence_status_reason: '3家独立媒体',
      material_depth: 'article_excerpt',
      source_count: 3,
      platform_count: 3,
      published_at: '2026-11-21T10:00:00+08:00',
      fetched_at: '2026-11-21T10:30:00+08:00',
      input_batch_id: 'b1',
      fact_summary: 'SEC 调查报道引发科技股剧烈波动。',
      ai_analysis: '资金短暂回避高估值算力，转向黄金等避险资产或谷歌 Gemini 等生态。',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [{ item_id: 's1', source_id: 'reuters', source_name: 'Reuters', source_kind: 'news', title: 'Gemini and gold safe-haven rotation amid NVDA probe', url: 'https://reuters.com/1', published_at: '2026-11-21T10:00:00+08:00', fetched_at: '2026-11-21T10:30:00+08:00' }],
      followup: null,
      is_new_in_batch: true,
    }
    const falseWatchlist: WatchlistItem[] = [
      { id: 'w_gold', kind: 'industry', label: '黄金', keywords: ['黄金'], created_at: '2026-11-21T00:00:00+08:00' },
      { id: 'w_gemini', kind: 'tech', label: 'Gemini', keywords: ['gemini'], created_at: '2026-11-21T00:00:00+08:00' },
    ]
    const falseMatchRes = matchEventAgainstWatchlist(nvdaEv, falseWatchlist)
    expect(falseMatchRes.matched).toBe(false)

    // No duplicate frontend tabloid penalty when title mentions 丑闻
    const noDupPenalty = matchEventAgainstWatchlist({ ...nvdaEv, title: '英伟达 CEO 丑闻发酵导致股市下挫' }, [], new Set(), new Set(), Date.parse('2026-11-21T11:00:00+08:00'))
    const plainBase = matchEventAgainstWatchlist({ ...nvdaEv, title: '英伟达 CEO 事件发酵导致股市下挫' }, [], new Set(), new Set(), Date.parse('2026-11-21T11:00:00+08:00'))
    expect(noDupPenalty.score).toBe(plainBase.score)

    // 3. Gemini 4 Neon must resolve tech/chip thumbnail instead of IPO thumbnail
    const neonEv: SmartEvent = {
      ...nvdaEv,
      event_id: 'ev_neon',
      category: 'tech',
      title: 'Google 正式发布 Gemini 4 Neon：百万上下文与高速推理',
      fact_summary: 'Anthropic 等大模型竞争加速，Gemini 4 Neon 定价每百万 token 3 美元。',
    }
    expect(resolveMustReadThumbnail(neonEv, 0, new Set())).toBe('./thumbs/top3-chip-transition.webp')

    // 4. evaluateSmartHealth reports stale upstream raw lag instead of '批次一致 · 正常'
    const lagHealth = evaluateSmartHealth('2026-11-21T11:30:00+08:00', Date.parse('2026-11-21T12:00:00+08:00'), {
      isHistory: false,
      status: 'complete',
      rawFetchedAtIso: '2026-11-21T01:40:00+08:00',
    })
    expect(lagHealth.level).toBe('stale')
    expect(lagHealth.label).toContain('滞后')

    // 5. diversityScore is null at 0 reads, marketColorMode CN/EN polarity, EN sanitation & Google News publisher cleanup
    const emptyEcho = computeEchoChamberReport(Date.parse('2026-11-21T12:00:00+08:00'), createMemoryStorage())
    expect(emptyEcho.diversityScore).toBeNull()

    const prevMode = marketColorMode.value
    try {
      setMarketColorMode('auto')
      expect(isRedUp('zh')).toBe(true)
      expect(isRedUp('en')).toBe(false)
      setMarketColorMode('cn')
      expect(isRedUp('en')).toBe(true)
      setMarketColorMode('intl')
      expect(isRedUp('zh')).toBe(false)
    } finally {
      setMarketColorMode(prevMode)
    }

    expect(sanitizeEnText('【国际外交动态】Google’   s Gemini expands')).toBe("Google's Gemini expands")
    expect(sanitizeEnText('[Enbridge Inc.] Enbridge管道因污染检测长期中断')).toBe('Enbridge管道因污染检测长期中断')
    const prevLang = appLang.value
    try {
      appLang.value = 'en'
      expect(pickBiText('霍尔木兹海峡油轮触雷', 'Strait of Hormuz 油轮 strikes mine in 海峡')).toBe('霍尔木兹海峡油轮触雷')
      expect(pickBiText('特朗普在深圳明确表态不支持“台独”', '特朗普在深圳 explicitly rejects support for “台独”，引发台湾岛内舆论震动')).toBe('特朗普在深圳明确表态不支持“台独”')
      expect(pickBiText('Enbridge管道因污染检测长期中断', '[Enbridge Inc.] Enbridge管道因污染检测长期中断')).toBe('Enbridge管道因污染检测长期中断')
      expect(translateSourceName('Google News 中文', '路透社：美债收益率大幅回落 — Reuters')).toBe('Reuters')
      expect(translateSourceName('Google News 英文国际')).toBe('International Media')
      appLang.value = 'zh'
      expect(translateSourceName('Google News 英文国际')).toBe('国际媒体')
    } finally {
      appLang.value = prevLang
    }
  })

  it('parses schema_version 4.1 and 5.0 smart docs and simulated comments without V1 fallback', () => {
    for (const schemaVer of ['4.1', '5.0']) {
      const smartDoc = adaptSmartCategoryDoc(
        {
          schema_version: schemaVer,
          batch_id: 'smart-20261122-072924',
          input_batch_id: 'raw-20261122-070403',
          generated_at: '2026-11-22T07:31:28+08:00',
          published_at: '2026-11-22T07:32:24+08:00',
          category: 'tech',
          events: [
            {
              event_id: 'evt_test_v41',
              title: 'Anthropic IPO 后走势观察',
              importance: 'high',
              evidence_status: 'multi_source',
              fact_summary: '测试事实摘要。',
              ai_analysis: '测试分析。',
              sources: [
                {
                  item_id: 'src_1',
                  source_id: 'google-news-en',
                  source_name: 'Google News 英文国际',
                  publisher_name: 'Reuters',
                  url: 'https://www.reuters.com/technology/anthropic-ipo-2026',
                },
              ],
            },
          ],
        },
        'tech',
      )

      expect(smartDoc.missing).not.toBe(true)
      expect(smartDoc.events).toHaveLength(1)
      expect(smartDoc.events[0].event_id).toBe('evt_test_v41')
      expect(smartDoc.events[0].sources[0].publisher_name).toBe('Reuters')

      const commentsDoc = adaptSimulatedComments(
        {
          schema_version: schemaVer,
          batch_id: 'smart-20261122-072924',
          status: 'ok',
          comments: [{ id: 'c1', role: '研究员', stance: '中立', content: '样本观点' }],
        },
        'tech',
        'smart-20261122-072924',
      )
      expect(commentsDoc.status).toBe('ok')
      expect(commentsDoc.comments).toHaveLength(1)
    }
  })

  it('resolves read-later items across live events, saved snapshots, and orphan pruning', () => {
    const liveEv: SmartEvent = {
      event_id: 'evt_live_1',
      title: 'OpenAI 发布新推理模型',
      category: 'tech',
      entities: ['OpenAI'],
      importance: 'high',
      sentiment: 'positive',
      special_note: null,
      evidence_status: 'multi_source',
      evidence_label: '多源交叉印证',
      evidence_status_reason: '',
      material_depth: 'full',
      source_count: 1,
      platform_count: 1,
      published_at: '2026-11-22T08:00:00+08:00',
      fetched_at: '2026-11-22T08:10:00+08:00',
      input_batch_id: 'smart-20261122-081000',
      fact_summary: '摘要',
      ai_analysis: '',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    }
    const res = resolveReadLaterEventsList(
      new Set(['evt_live_1', 'evt_snap_2', 'evt_orphan_3']),
      [liveEv],
      {
        evt_snap_2: {
          event_id: 'evt_snap_2',
          title: '跨批次保留快照新闻',
          url: 'https://example.com/snap-2',
          category: 'finance',
          source_name: 'Reuters',
          saved_at: '2026-11-21T10:00:00+08:00',
        },
      },
    )
    expect(res.validEvents.map((e) => e.event_id)).toEqual(['evt_live_1', 'evt_snap_2'])
    expect(res.validEvents[1].input_batch_id).toBe('saved-snapshot')
    expect(res.orphanIds).toEqual(['evt_orphan_3'])
  })

  it('never leaks generic "综合资讯" in translateSourceName and groups gnews by publisher', () => {
    expect(translateSourceName('综合资讯')).toBe('国际媒体')
    expect(translateSourceName('Google News 中文AI')).toBe('国际媒体')
    expect(translateSourceName('Google News 英文国际', 'Event - Reuters')).toBe('Reuters')

    const events: SmartEvent[] = [
      {
        event_id: 'e1',
        title: 'AI Chip News',
        category: 'tech',
        entities: [],
        importance: 'normal',
        sentiment: null,
        special_note: null,
        evidence_status: 'single_source',
        evidence_label: '单一来源',
        evidence_status_reason: '',
        material_depth: 'title_only',
        source_count: 1,
        platform_count: 1,
        published_at: '2026-11-22T08:00:00+08:00',
        fetched_at: '2026-11-22T08:05:00+08:00',
        input_batch_id: 'b1',
        fact_summary: '',
        ai_analysis: '',
        unverified_claims: [],
        speculation_or_outlook: null,
        sources: [
          {
            item_id: 's1',
            source_id: 'rss-gnews-tech',
            source_name: '综合资讯',
            publisher_name: 'TechCrunch',
            source_kind: 'rss',
            title: 'AI Chip News',
            published_at: '2026-11-22T08:00:00+08:00',
            fetched_at: '2026-11-22T08:05:00+08:00',
            url: 'https://techcrunch.com/2026/11/22/ai-chip',
          },
        ],
        followup: null,
        is_new_in_batch: true,
      },
    ]

    const opts = extractSmartSourceOptions(events)
    expect(opts).toEqual([{ id: 'pub:TechCrunch', name: 'TechCrunch', count: 1 }])
    const matched = filterSmartEvents(events, {
      query: '',
      evidence: 'all',
      sourceId: 'pub:TechCrunch',
      entity: '',
      onlyUnreadOrNew: false,
      unreadChecker: () => true,
    })
    expect(matched).toHaveLength(1)
  })

  it('rotates stale or already-read hero lead to fresh <12h multi-source event and computes portfolio/48h dashboard counts', () => {
    const nowMs = Date.parse('2026-11-22T19:00:00+08:00')
    const mk = (id: string, title: string, iso: string, indep = 2): SmartEvent => ({
      event_id: id,
      title,
      category: 'tech',
      entities: [],
      importance: 'high',
      sentiment: null,
      special_note: null,
      evidence_status: 'multi_source',
      evidence_label: '多源',
      evidence_status_reason: '',
      material_depth: 'full',
      source_count: indep,
      platform_count: indep,
      independent_publisher_count: indep,
      published_at: iso,
      first_reported_at: iso,
      latest_reported_at: iso,
      fetched_at: iso,
      input_batch_id: 'b1',
      fact_summary: '',
      ai_analysis: '',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    })

    const staleOld = mk('ev_old', '64h Old Mega IPO', '2026-11-20T02:19:00+08:00', 5)
    const freshHot = mk('ev_hot', 'Fresh 3h Multi-Source Story', '2026-11-22T16:00:00+08:00', 4)
    expect(selectLeadEventIndex([staleOld, freshHot], new Set(), new Set(), nowMs)).toBe(1)

    const hit = matchImpactAgainstPortfolio(
      {
        id: 'imp_1',
        rule_id: 'r1',
        event_id: 'ev1',
        event_title: 'NVIDIA Export Curb',
        category: 'finance',
        published_at: '2026-11-22T16:00:00+08:00',
        source_name: 'CNBC',
        tag: 'Semis',
        polarity: 'bearish',
        intensity: 4,
        one_liner: 'Negative',
        affected_tickers: { NVDA: -0.9 },
        bars: [{ market: '美股', sector: 'GPU (NVDA)', pct_low: -4, pct_high: -1, direction: 'negative', logic: 'Curbs' }],
        if_then: [],
        milestones: [],
      },
      { sectors: [], tickers: ['NVDA'], riskProfile: 'balanced' },
    )
    expect(hit.matched).toBe(true)

    const cals = countUpcomingCatalystsWithinHours(
      [
        {
          calendar_id: 'c_soon',
          title: 'COP31 Vote',
          scheduled_at: '2026-11-23T22:00:00+08:00',
          timezone: 'Asia/Shanghai',
          certainty: 'reported_tbd',
          certainty_label: 'TBD',
          category: 'global',
          entity_ids: [],
          watch_variable: 'Text',
          source_name: 'UNFCCC',
          source_url: null,
        },
        {
          calendar_id: 'c_far',
          title: 'Two Sessions 2027',
          scheduled_at: '2027-03-05T09:00:00+08:00',
          timezone: 'Asia/Shanghai',
          certainty: 'confirmed_official',
          certainty_label: 'Official',
          category: 'global',
          entity_ids: [],
          watch_variable: 'GDP',
          source_name: 'NPC',
          source_url: null,
        },
      ],
      nowMs,
      48,
    )
    expect(cals.map((c) => c.calendar_id)).toEqual(['c_soon'])
  })

  it('demotes >24h stale or B-tier leads for fresh S-tier stories and deduplicates breaking highlights', async () => {
    const { filterActiveBreakingHighlights } = await import('../../web/src/core/v3Logic')
    const nowMs = Date.parse('2026-11-22T21:00:00+08:00')
    const mk = (id: string, title: string, pub: string, tier: 'S' | 'A' | 'B', indep: number): SmartEvent => ({
      event_id: id,
      title,
      category: 'finance',
      entities: [],
      importance: tier === 'B' ? 'normal' : 'high',
      severity_tier: tier,
      evidence_status: 'multi_source',
      evidence_label: '多源',
      evidence_status_reason: 'ok',
      material_depth: 'body_lead_extracted',
      source_count: indep,
      platform_count: indep,
      independent_publisher_count: indep,
      published_at: pub,
      first_reported_at: pub,
      latest_reported_at: pub,
      fetched_at: pub,
      input_batch_id: 'b_test',
      fact_summary: title,
      ai_analysis: '核心催化',
      unverified_claims: [],
      speculation_or_outlook: null,
      sources: [],
      followup: null,
      is_new_in_batch: true,
    })

    const stale30h = mk('ev_30h', '30h Old Event', '2026-11-21T14:00:00+08:00', 'A', 4)
    const freshS = mk('ev_fresh_s', '沪深北交易所下调融资保证金比例', '2026-11-22T18:45:00+08:00', 'S', 3)
    expect(selectLeadEventIndex([stale30h, freshS], new Set(), new Set(), nowMs)).toBe(1)

    const brks = filterActiveBreakingHighlights(
      [
        {
          id: 'brk_1',
          title: '沪深北交易所将融资保证金比例下限降至 80%，有望释放 4000 亿元增量资金',
          excerpt: '三大交易所公告。',
          category: 'finance',
          source_name: '财联社',
          url: 'https://cls.cn/1',
          published_at: '2026-11-22T19:00:00+08:00',
        },
        {
          id: 'brk_2',
          title: '菲尔兹奖得主梅纳德回应黎曼猜想形式化验证',
          excerpt: '数学界回应。',
          category: 'tech',
          source_name: '华尔街见闻',
          url: 'https://wscn.com/2',
          published_at: '2026-11-22T20:10:00+08:00',
        },
      ],
      [freshS],
      nowMs,
    )
    // brk_1 matches freshS ('保证金'), so only un-promoted brk_2 remains
    expect(brks.map((b) => b.id)).toEqual(['brk_2'])
  })

  it('supports V9 deep finance impact fields and AI lineage / 5-dimension types', async () => {
    const typesMod = await import('../../web/src/core/types')
    expect(typesMod).toBeDefined()
    const v9Impact: import('../../web/src/core/types').EventMarketImpact = {
      id: 'imp_v9',
      event_id: 'ev_v9',
      rule_id: 'a_share_capital_market_reform',
      validation_status: 'verified',
      event_title: '沪深北交易所将融资保证金比例下限降至80%',
      category: 'finance',
      published_at: '2026-11-22T20:30:00+08:00',
      source_name: '财联社',
      tag: 'A股两融松绑与资本市场稳市组合拳',
      polarity: 'bullish',
      intensity: 5,
      one_liner: '理论释放4000亿元增量资金',
      bars: [{ market: 'A股', sector: '券商与金融IT', pct_low: 2.8, pct_high: 6.4, direction: 'positive', proxy_ticker: '600030.SH', logic: '利好两融扩张' }],
      if_then: [],
      milestones: [],
      priced_in_analysis: {
        status_code: 'unpriced',
        status_label: '未计价（周一早盘增量催化）',
        session_context: '周末非交易时段发布',
        expectation_gap: '周一早盘存在增量重估缺口',
      },
      transmission_layers: [
        {
          tier: 1,
          tier_label: '一阶直接冲击',
          summary: '利好头部两融券商',
          stocks: [{ name: '中信证券', code: '600030.SH', market: 'A股', exposure_logic: '两融第一', direction: 'positive' }],
        },
      ],
      historical_precedents: [
        { date: '2023-08-27', event_title: '证监会调降融资保证金至80%', t1_reaction: '+1.13%', t5_reaction: '+2.2%', lesson: '忌高开超4%盲目追高' },
      ],
      quant_if_then: [
        { case: 'bull', label: '正向验证', trigger_metric: '首小时成交额', threshold: '>= 5500亿元', action_implication: '顺势跟随' },
      ],
    }
    expect(v9Impact.priced_in_analysis?.status_code).toBe('unpriced')
    expect(v9Impact.transmission_layers?.[0].stocks[0].code).toBe('600030.SH')
    expect(v9Impact.historical_precedents?.[0].date).toBe('2023-08-27')
    expect(v9Impact.quant_if_then?.[0].case).toBe('bull')
  })

  it('keeps prediction leaderboard strictly live-only, echoes matching notes across modules, and syncs all V10 user state keys', () => {
    const mkRec = (
      id: string,
      mode: 'live' | 'replay',
      status: 'open' | 'settled',
      outcome?: 'correct' | 'incorrect',
    ): PredictionRecord => ({
      prediction_id: id,
      mode,
      status,
      title: id,
      target_entity: 'NVIDIA',
      question: 'Q',
      created_at: '2026-11-20T00:00:00+08:00',
      due_at: '2026-12-01T00:00:00+08:00',
      win_rule: 'w',
      lose_rule: 'l',
      indeterminate_rule: 'i',
      supporting_evidence: [],
      opposing_evidence: [],
      core_assumption: 'a',
      invalidation_trigger: 'i',
      probability_pct: 70,
      current_judgment: 'j',
      versions: [],
      settlement: outcome ? { outcome, settled_at: '2026-11-22T00:00:00+08:00', note: 'done' } : null,
    })

    // 2 settled replay records + 1 open live record -> leaderboard MUST NOT unlock or show 100%!
    const lbLocked = computeLiveDomainLeaderboard([
      mkRec('r1', 'replay', 'settled', 'correct'),
      mkRec('r2', 'replay', 'settled', 'correct'),
      mkRec('l1', 'live', 'open'),
    ])
    expect(lbLocked.replaySettledDecisive).toBe(2)
    expect(lbLocked.liveSettledDecisive).toBe(0)
    expect(lbLocked.unlocked).toBe(false)
    expect(lbLocked.rows.every((r) => r.hitPct === null)).toBe(true)

    // Cross-module note entity/ticker echo
    const notesCount = countMatchingNotesForSubject(
      [
        {
          note_id: 'n1',
          target_type: 'event',
          target_id: 'evt_1',
          title: 'NVDA 链分析',
          entity_ids: ['ent_nvidia'],
          tickers: ['NVDA', '600030.SH'],
          answer_markdown: '重点看两融增量',
          evidence_urls: [],
          created_at: '2026-11-22T12:00:00+08:00',
        },
      ],
      { eventId: 'evt_other', tickers: ['600030'] },
    )
    expect(notesCount).toBe(1)

    // Morning brief & V10 cloud state round-trip (portfolio + prediction_stances + read_ids)
    const mb = buildMorningBriefSummary(
      [
        {
          id: 'imp_1',
          event_id: 'evt_1',
          rule_id: 'a_share_capital_market_reform',
          validation_status: 'verified',
          event_title: '两融保证金下调至80%',
          category: 'finance',
          published_at: '2026-11-22T20:00:00+08:00',
          source_name: '财联社',
          tag: '券商两融',
          polarity: 'bullish',
          intensity: 5,
          one_liner: '释放流动性',
          affected_tickers: { '600030.SH': 1 },
          bars: [{ market: 'A股', sector: '券商', pct_low: 2, pct_high: 5, direction: 'positive', logic: '两融提升' }],
          if_then: [],
          milestones: [],
        },
      ],
      { sectors: ['券商'], tickers: ['600030'], riskProfile: 'balanced' },
      [],
      [],
      Date.parse('2026-11-22T21:00:00+08:00'),
    )
    expect(mb.portfolioHits).toHaveLength(1)

    const mem = new Map<string, string>()
    const store: StorageLike = {
      getItem: (k) => mem.get(k) ?? null,
      setItem: (k, v) => mem.set(k, v),
    }
    savePortfolioConfig({ sectors: ['半导体'], tickers: ['NVDA'], riskProfile: 'aggressive' }, store)
    savePredictionStances({ pred_live_fomc_2026_12: 'agree' }, store)
    saveReadState(new Set(['evt_99']), new Set(), store)
    const exp = JSON.parse(exportAllResearchState(store))
    expect(exp.portfolio.tickers).toContain('NVDA')
    expect(exp.prediction_stances.pred_live_fomc_2026_12).toBe('agree')
    expect(exp.read_ids).toContain('evt_99')

    const mem2 = new Map<string, string>()
    const store2: StorageLike = {
      getItem: (k) => mem2.get(k) ?? null,
      setItem: (k, v) => mem2.set(k, v),
    }
    const merged = mergeResearchStateJson(JSON.stringify(exp), store2)
    expect(merged.ok).toBe(true)
    expect(loadPortfolioConfig(store2).tickers).toContain('NVDA')
    expect(loadPredictionStances(store2).pred_live_fomc_2026_12).toBe('agree')
    expect(loadReadState(store2).readIds.has('evt_99')).toBe(true)
  })

  it('v11: unifies 4-tier evidence badges, headline qualifiers, <24h clock format, and honest batch health labels', () => {
    const off = resolveEvidenceTierBadge({
      sources: [{ source_name: '中国证监会', is_reprint_copy: false }],
      title: '沪深北交易所降低两融保证金比例至80%',
    })
    expect(off.tier).toBe('official')
    expect(off.iconKey).toBe('official')
    expect(off.label).toContain('官方公告')
    expect(off.label).not.toMatch(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u)
    expect(off.shortLabel).not.toMatch(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u)
    expect(off.isUnverifiedOrResearch).toBe(false)

    const resBadge = resolveEvidenceTierBadge({
      sources: [{ source_name: '招商证券', is_reprint_copy: false }],
      title: '招商证券研报称A股估值底部',
    })
    expect(resBadge.tier).toBe('research')
    expect(resBadge.iconKey).toBe('research')
    expect(resBadge.isUnverifiedOrResearch).toBe(true)

    const sinBadge = resolveEvidenceTierBadge({
      evidence_status: 'single_source',
      sources: [{ source_name: 'IT之家', is_reprint_copy: false }],
      title: '某公司董事会传闻',
    })
    expect(sinBadge.tier).toBe('single_source')
    expect(sinBadge.iconKey).toBe('clue')
    expect(sinBadge.isUnverifiedOrResearch).toBe(true)

    const quals = extractHeadlineQualifiers('自2026年11月30日起正式施行，最高提价45%')
    expect(quals.effectiveDateLabel).toContain('11月30日')
    expect(quals.effectiveDateLabel).not.toMatch(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u)
    expect(quals.qualifierBadge).toContain('45%')
    expect(quals.qualifierBadge).not.toMatch(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/u)
    expect(stripEmoji('🚀 旗舰模型 🏛️')).toBe('旗舰模型')
    expect(iconSvg('flame', 14)).toContain('<svg')

    const nowMs = Date.parse('2026-11-22T20:00:00+08:00')
    const ut = formatUnifiedTime('2026-11-22T15:14:00+08:00', nowMs, undefined, '2026-11-22T15:28:00+08:00')
    expect(ut.text).toContain('4 小时前')
    expect(ut.text).toContain('15:14 发布')
    expect(ut.title).toContain('原文发布 2026-11-22 15:14 CST')
    expect(ut.title).toContain('本站收录 11-22 15:28 CST')

    const healthy = evaluateSmartHealth('2026-11-22T19:30:00+08:00', nowMs, { isHistory: false })
    expect(healthy.label).toBe('全部数据源已同步最新批次')

    const partial = evaluateSmartHealth('2026-11-22T19:30:00+08:00', nowMs, {
      isHistory: false,
      hasFallbackCat: true,
      fallbackCategories: ['科技/AI'],
    })
    expect(partial.label).toContain('科技/AI')
  })

  it('v16: centers clicked pills cleanly without throwing on missing scrollIntoView', () => {
    const spy = vi.fn()
    centerPillIntoView({ currentTarget: { scrollIntoView: spy } } as unknown as Event)
    expect(spy).toHaveBeenCalledWith({ behavior: 'smooth', inline: 'center', block: 'nearest' })
    expect(() => centerPillIntoView(null)).not.toThrow()
    expect(() => centerPillIntoView({ currentTarget: {} } as unknown as Event)).not.toThrow()
  })

  it('v17: formats friendly batch labels and applies editorial overrides to events & wire', () => {
    expect(formatFriendlyBatchId('smart-20261123-141522')).toBe('云端同步批次 #20261123-1415')
    expect(formatFriendlyBatchId('raw-20261123-090511')).toBe('云端同步批次 #20261123-0905')
    expect(formatFriendlyBatchId('  ')).toBe('-')

    const events = [
      { event_id: 'e1', title: '普通新闻一条', severity_tier: 'B', severity_label: 'B级常规', importance: 'normal', heavy_reason_tag: null as string | null },
      { event_id: 'e2', title: '券商评级研报一条', severity_tier: 'A', severity_label: 'A级要闻', importance: 'high', heavy_reason_tag: '巨头重大变动' as string | null },
      { event_id: 'e3', title: '需要隐藏的重复条', severity_tier: 'B', severity_label: 'B级常规', importance: 'normal', heavy_reason_tag: null as string | null },
    ]
    const doc = {
      updated_at: '2026-11-23T14:30:00+08:00',
      items: {
        'event:e1': {
          key: 'event:e1',
          target_type: 'event' as const,
          event_id: 'e1',
          title: '普通新闻一条',
          title_fingerprint: titleFingerprint('普通新闻一条'),
          severity_override: 'S' as const,
          heavy_reason_tag: '监管新政',
          pinned: true,
          hidden: false,
        },
        'event:e2': {
          key: 'event:e2',
          target_type: 'event' as const,
          event_id: 'e2',
          title: '券商评级研报一条',
          title_fingerprint: titleFingerprint('券商评级研报一条'),
          severity_override: 'B' as const,
          heavy_reason_tag: null,
          pinned: false,
          hidden: false,
        },
        'event:e3': {
          key: 'event:e3',
          target_type: 'event' as const,
          event_id: 'e3',
          title: '需要隐藏的重复条',
          title_fingerprint: titleFingerprint('需要隐藏的重复条'),
          hidden: true,
        },
        'wire:w1': {
          key: 'wire:w1',
          target_type: 'wire' as const,
          title: '突发快讯提级',
          title_fingerprint: titleFingerprint('突发快讯提级'),
          severity_override: 'S' as const,
          heavy_reason_tag: '地缘与军事突发',
          pinned: true,
          hidden: false,
        },
      },
    }

    const patchedEvents = applyEditorialOverridesToEvents(events, doc)
    expect(patchedEvents.map((e) => e.event_id)).toEqual(['e1', 'e2'])
    expect(patchedEvents[0].severity_tier).toBe('S')
    expect(patchedEvents[0].heavy_reason_tag).toBe('监管新政')
    expect(patchedEvents[1].severity_tier).toBe('B')
    expect(patchedEvents[1].importance).toBe('normal')
    expect(patchedEvents[1].heavy_reason_tag).toBeNull()

    const wireItems = [
      { id: 'w2', title: '常规快讯', severity_tier: 'B', importance: 'normal', heavy_reason_tag: null as string | null },
      { id: 'w1', title: '突发快讯提级', severity_tier: 'B', importance: 'normal', heavy_reason_tag: null as string | null },
    ]
    const patchedWire = applyEditorialOverridesToWire(wireItems, doc)
    expect(patchedWire.map((w) => w.id)).toEqual(['w1', 'w2'])
    expect(patchedWire[0].severity_tier).toBe('S')
    expect(patchedWire[0].heavy_reason_tag).toBe('地缘与军事突发')
  })

  it('V18 vector avatar presets, admin obsidian shield default, validation & cloud sync merge', async () => {
    const avatarsMod = await import('../../web/src/core/avatars')
    const storageMod = await import('../../web/src/core/storage')

    expect(avatarsMod.AVATAR_PRESETS).toHaveLength(12)
    expect(avatarsMod.resolveDefaultAvatarSpec('admin', 'super_admin').id).toBe('default:obsidian_shield')
    expect(avatarsMod.resolveDefaultAvatarSpec('ops', 'admin').kind).toBe('obsidian_shield')
    const u1 = avatarsMod.resolveDefaultAvatarSpec('alice', 'user')
    const u2 = avatarsMod.resolveDefaultAvatarSpec('alice', 'user')
    expect(u1.id).toBe(u2.id)
    expect(u1.kind).not.toBe('obsidian_shield')

    expect(avatarsMod.isValidAvatarValue('preset:star_compass')).toBe(true)
    expect(avatarsMod.isValidAvatarValue('preset:unknown_999')).toBe(false)
    expect(avatarsMod.isValidAvatarValue('data:image/webp;base64,AAAA')).toBe(true)
    expect(avatarsMod.isValidAvatarValue(`data:image/webp;base64,${'A'.repeat(29000)}`)).toBe(false)
    expect(avatarsMod.isValidAvatarValue('javascript:alert(1)')).toBe(false)

    const mem = createMemoryStorage()
    storageMod.saveUserAvatar('preset:quant_bull', mem)
    expect(storageMod.loadUserAvatar(mem)).toBe('preset:quant_bull')
    const exported = JSON.parse(storageMod.exportAllResearchState(mem))
    expect(exported.avatar).toBe('preset:quant_bull')

    const freshMem = createMemoryStorage()
    const mergeRes = storageMod.mergeResearchStateJson(
      JSON.stringify({ avatar: 'preset:quantum_cube', bookmarks: [] }),
      freshMem,
    )
    expect(mergeRes.ok).toBe(true)
    expect(storageMod.loadUserAvatar(freshMem)).toBe('preset:quantum_cube')
  })

  it('V20 infers prediction categories accurately & tracks early live settlement stats', async () => {
    const logicMod = await import('../../web/src/core/v3Logic')
    expect(
      logicMod.inferPredictionCategory({
        category: 'tech_ai',
        title: '黄仁勋能否在 14 天内正式重返英伟达出任 CEO？',
      }),
    ).toBe('tech_ai')
    expect(
      logicMod.inferPredictionCategory({
        title: '神舟二十四号载人飞船能否在 11 月 26 日前顺利发射入轨并对接空间站？',
        target_entity_id: 'ent_china_aerospace',
      }),
    ).toBe('global_space')
    expect(
      logicMod.inferPredictionCategory({
        title: '现货黄金 11 月底（11 月 30 日收盘）前能否重新站上 3,700 美元/盎司？',
      }),
    ).toBe('market')
    expect(
      logicMod.inferPredictionCategory({
        title: '11 月 30 日中国官方 11 月制造业 PMI 能否站上 50.0 荣枯线？',
      }),
    ).toBe('macro')

    const makeRec = (
      id: string,
      status: 'open' | 'settled',
      outcome: 'correct' | 'incorrect' | null = null,
    ): PredictionRecord => ({
      prediction_id: id,
      mode: 'live',
      status,
      category: 'tech_ai',
      title: `Question ${id}`,
      target_entity: '英伟达 (NVIDIA)',
      question: 'Test question?',
      created_at: '2026-11-24T12:00:00+08:00',
      due_at: '2026-11-30T20:00:00+08:00',
      win_rule: 'Yes',
      lose_rule: 'No',
      supporting_evidence: [],
      opposing_evidence: [],
      core_assumption: 'Public filings',
      invalidation_trigger: 'Canceled',
      probability_pct: 65,
      current_judgment: 'Resolved',
      versions: [],
      settlement: outcome
        ? {
            outcome,
            settled_at: '2026-11-24T12:00:00+08:00',
            evidence_url: 'https://www.sec.gov/',
            note: 'Confirmed by 8-K',
            brier_score: 0.1225,
          }
        : null,
    })

    const records = [makeRec('pred_seed_nvda_sec_502', 'settled', 'correct'), makeRec('pred_live_q2', 'open', null)]
    const stats = computePredictionStats(records)
    const lb = computeLiveDomainLeaderboard(records, 5)
    expect(stats.live.correctCount).toBe(1)
    expect(stats.live.openCount).toBe(1)
    expect(lb.liveSettledDecisive).toBe(1)
    expect(lb.unlocked).toBe(false)
  })

  it('V21 supports CJK bigram search, merged duplicate sources, normalizeExternalUrl, mute filtering, and market color toggle', () => {
    expect(matchesSmartQuery('央行开展 5160 亿元 7 天期逆回购操作', '央行逆回购')).toBe(true)
    expect(matchesSmartQuery('央行开展逆回购', '美联储 降息')).toBe(false)

    const bbcEvA = {
      event_id: 'ev_bbc_1',
      category: 'global' as const,
      title: 'BBC Report 1',
      summary: 'Test',
      fact_summary: 'Test',
      sources: [{ source_id: 'bbc_world_a', source_name: 'BBC News World', url: 'https://www.bbc.com/news/1' }],
      entities: [],
      importance: 'medium' as const,
    } as unknown as SmartEvent
    const bbcEvB = {
      event_id: 'ev_bbc_2',
      category: 'global' as const,
      title: 'BBC Report 2',
      summary: 'Test',
      fact_summary: 'Test',
      sources: [{ source_id: 'bbc_world_b', source_name: 'BBC News World', url: 'https://www.bbc.com/news/2' }],
      entities: [],
      importance: 'medium' as const,
    } as unknown as SmartEvent
    const mergedSources = extractSmartSourceOptions([bbcEvA, bbcEvB])
    expect(mergedSources).toHaveLength(1)
    expect(mergedSources[0].name).toBe('BBC News World')
    expect(mergedSources[0].count).toBe(2)

    const muted = new Set(['ev_bbc_1'])
    expect(isEventMuted(bbcEvA, muted)).toBe(true)
    expect(isEventMuted(bbcEvB, muted)).toBe(false)

    expect(normalizeExternalUrl('https://www.bbc.com/news/1')).toBe('https://www.bbc.com/news/1')
    expect(normalizeExternalUrl('javascript:alert(1)')).toBeNull()
    expect(normalizeExternalUrl('#')).toBeNull()

    setMarketColorMode('cn')
    expect(toggleMarketColorMode()).toBe('intl')
    expect(isRedUp()).toBe(false)
    expect(toggleMarketColorMode()).toBe('cn')
    expect(isRedUp()).toBe(true)

    const storage = createMemoryStorage()
    saveStringSetKey('muted', new Set(['ev_bbc_1']), storage)
    storage.setItem('infofocus_market_color_v1', 'intl')
    storage.setItem('infofocus_mobile_important_push_v1', '0')
    const exported = exportAllResearchState(storage)
    expect(JSON.parse(exported).muted).toEqual(['ev_bbc_1'])
    expect(JSON.parse(exported).market_color_mode).toBe('intl')

    const targetStorage = createMemoryStorage()
    const merged = mergeResearchStateJson(exported, targetStorage)
    expect(merged.ok).toBe(true)
    expect(Array.from(loadStringSetKey('muted', targetStorage))).toEqual(['ev_bbc_1'])
    expect(targetStorage.getItem('infofocus_market_color_v1')).toBe('intl')

    expect(unwrapRawDictText("{'name': 'Anthropic SDK', 'version': 'v2.13.0', 'notes': '消息批处理接口新增错误码；优化未知值工具结果的类…")).toBe(
      '消息批处理接口新增错误码；优化未知值工具结果的类…',
    )
    expect(unwrapRawDictText('{"name": "llama.cpp", "notes": "Clean JSON summary"}')).toBe('Clean JSON summary')
    expect(unwrapRawDictText('普通中文 AI 进展描述')).toBe('普通中文 AI 进展描述')
  })

  it('supports Cloudflare polling wire mode with auth headers and clean storage exports', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        schema_version: '5.0',
        updated_at: '2026-11-25T20:00:00+08:00',
        status: 'ok',
        sources_online: 'Edge',
        total: 1,
        items: [
          {
            id: 'w_cf_1',
            title: 'Cloudflare Worker Cron wire test item',
            excerpt: 'Test excerpt',
            category: 'tech',
            source_name: '财联社',
            url: 'https://www.cls.cn/detail/1',
            published_at: '2026-11-25T20:00:00+08:00',
            importance: 'high',
            tag: '重要快讯',
          },
        ],
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    const arrived: string[] = []
    const handle = createLiveWireController({
      pollUrl: 'https://mirrorinfo.xyz/api/wire/latest',
      getAuthToken: () => 'jwt-demo-token',
      onUpdate: (_doc, newIds) => {
        arrived.push(...newIds)
      },
    })
    expect(handle.getMode()).toBe('polling')
    handle.seedFromDoc({
      schema_version: '5.0',
      updated_at: '2026-11-25T19:50:00+08:00',
      status: 'ok',
      sources_online: 'Edge',
      total: 0,
      items: [],
    })
    await new Promise((resolve) => setTimeout(resolve, 15))
    handle.stop()

    expect(fetchMock).toHaveBeenCalled()
    const callInit = (fetchMock.mock.calls[0] as unknown[])[1] as { headers?: Record<string, string> }
    expect(callInit?.headers?.Authorization).toBe('Bearer jwt-demo-token')
    expect(arrived).toContain('w_cf_1')

    const md = exportBookmarksMarkdown([])
    expect(md).toContain('镜信 MirrorBrief')
    expect(md).not.toContain('InfoFocus')
    vi.unstubAllGlobals()
  })

  it('persists, exports, and bi-directionally merges weekly digest habit streak & stances', () => {
    const store = createMemoryStorage()
    saveWeeklyHabitState(
      {
        readByWeek: { '2026-W48': ['wk_a', 'wk_b'] },
        completedWeeks: ['2026-W47'],
        reactionsByItem: { wk_a: 'bull' },
        outlookStancesById: { '2026-W48::outlook_1': 'up' },
        lastVisitedWeekId: '2026-W48',
      },
      store,
    )
    const exported = JSON.parse(exportAllResearchState(store))
    expect(exported.weekly_habit.readByWeek['2026-W48']).toEqual(['wk_a', 'wk_b'])

    const mergeRes = mergeResearchStateJson(
      JSON.stringify({
        weekly_habit: {
          readByWeek: { '2026-W48': ['wk_b', 'wk_c'], '2026-W47': ['wk_old'] },
          completedWeeks: ['2026-W46'],
          reactionsByItem: { wk_z: 'bear' },
          outlookStancesById: { '2026-W48::outlook_2': 'down' },
          lastVisitedWeekId: '2026-W47',
        },
      }),
      store,
    )
    expect(mergeRes.ok).toBe(true)
    expect(mergeRes.needsPush).toBe(true)
    const merged = loadWeeklyHabitState(store)
    expect(merged.readByWeek['2026-W48']).toEqual(['wk_b', 'wk_c', 'wk_a'])
    expect(merged.completedWeeks).toEqual(['2026-W46', '2026-W47'])
    expect(merged.reactionsByItem).toEqual({ wk_z: 'bear', wk_a: 'bull' })
    expect(merged.outlookStancesById).toEqual({
      '2026-W48::outlook_2': 'down',
      '2026-W48::outlook_1': 'up',
    })
  })
})
