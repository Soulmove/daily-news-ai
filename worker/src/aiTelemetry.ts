import { nowShanghaiIso } from './crypto'
import type { Env } from './types'

export interface ModelSpecInfo {
  model: string
  tier: 'tier1' | 'tier2' | 'edge'
  rpm: number
  rpd_per_key: number
  soft_rpd_per_key: number
  role_label: string
  duties: string
}

export const MODEL_CATALOG: ModelSpecInfo[] = [
  {
    model: 'gemini-4-hydrogen',
    tier: 'tier1',
    rpm: 5,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: '旗舰深度主模型',
    duties: '每小时分类简报、每周大事复盘、AI科研前沿、长期专题脉络、事件QA与专题日历推理首选',
  },
  {
    model: 'gemini-3.8-flash',
    tier: 'tier1',
    rpm: 5,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: 'Tier1 第1顺位替补',
    duties: 'gemini-4-hydrogen 限流/503/超时/日配额满后立即接棒，也是 Tier2 跨级兜底第一站',
  },
  {
    model: 'gemini-3.6-flash',
    tier: 'tier1',
    rpm: 5,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: 'Tier1 第2顺位替补',
    duties: '3.8-flash 拥塞或冷却时的续跑引擎，兼任高吞吐任务满额后的中层安全网',
  },
  {
    model: 'gemini-3-flash',
    tier: 'tier1',
    rpm: 5,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: '经典全能 / 预览替补',
    duties: '实际映射到 gemini-3-flash-preview；承担 Tier1 第3顺位替补及全能摘要兜底',
  },
  {
    model: 'gemini-2.5-flash',
    tier: 'tier1',
    rpm: 5,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: '边缘问答默认 / 稳定替补',
    duties: 'Cloudflare Worker 在线「AI 证据问答」默认主模型；专题脉络/事件QA直连第1替补与 Tier1 核心兜底',
  },
  {
    model: 'gemini-3.5-flash-lite',
    tier: 'tier2',
    rpm: 15,
    rpd_per_key: 500,
    soft_rpd_per_key: 475,
    role_label: '高吞吐主力 (500 RPD/Key)',
    duties: '双语翻译、股市传导研判、AI 模型矩阵、GitHub 工具摘要、预测市场衍生与自动结算首选',
  },
  {
    model: 'gemini-3.1-flash-lite',
    tier: 'tier2',
    rpm: 15,
    rpd_per_key: 500,
    soft_rpd_per_key: 475,
    role_label: '高吞吐第2引擎 (500 RPD/Key)',
    duties: '3.5-flash-lite 触发 15 RPM 间隔冷却、503 或 429 时的同级别高速替补',
  },
  {
    model: 'gemini-2.5-flash-lite',
    tier: 'tier1',
    rpm: 10,
    rpd_per_key: 20,
    soft_rpd_per_key: 18,
    role_label: 'Lite 末级安全网',
    duties: 'Lite 系列双主力均冷却/受限，以及 Tier1 全链末尾时的最终兜底模型',
  },
  {
    model: 'worker-grounded-rag',
    tier: 'edge',
    rpm: 0,
    rpd_per_key: 0,
    soft_rpd_per_key: 0,
    role_label: '无密钥本地检索兜底',
    duties: 'Worker 线上问答未配密钥或 Gemini 上游超时/失败时，基于 R2 证据库实时规则合成答案（0 Gemini Token）',
  },
]

const MODEL_SPEC_MAP = new Map(MODEL_CATALOG.map((m) => [m.model, m]))

export const PIPELINE_CORE_KEY_SLOTS: string[] = [
  'KEY_TECH',
  'KEY_GLOBAL',
  'KEY_FINANCE',
  'KEY_GENERAL',
  'GOOGLE_API_KEY',
  'KEY_1',
  'KEY_2',
  'KEY_3',
  'KEY_4',
  'KEY_5',
  'KEY_6',
  'KEY_7',
  'KEY_8',
]

export interface AiRoutingGuideModule {
  module_id: string
  module_name: string
  cadence: string
  primary_model: string
  fallback_chain: string[]
  duties: string
}

export const MODEL_ROUTING_GUIDE: {
  modules: AiRoutingGuideModule[]
  switch_rules: Array<{ trigger: string; title: string; behavior: string }>
} = {
  modules: [
    {
      module_id: 'briefing_hourly',
      module_name: '每小时四分类 AI 简报 & 模拟多维观点',
      cadence: '每小时 (:15 CST)',
      primary_model: 'gemini-4-hydrogen',
      fallback_chain: [
        'gemini-3.8-flash',
        'gemini-3.6-flash',
        'gemini-3-flash',
        'gemini-2.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite',
      ],
      duties: '汇总财经/国际/科技/综合四路事实摘要、证据可信度核验与多视角评述。',
    },
    {
      module_id: 'storylines_qa_cal',
      module_name: '事件追踪脉络 / 事件深度 QA / 专题日历',
      cadence: '随简报主链每小时按需刷新',
      primary_model: 'gemini-4-hydrogen',
      fallback_chain: ['gemini-2.5-flash'],
      duties: '双模型精简深研链，生成事件时间线、核查要点与催化剂预测日历。',
    },
    {
      module_id: 'ai_radar_weekly',
      module_name: 'AI 前沿雷达 & 每周大事重磅复盘',
      cadence: 'AI雷达每小时 / 周报每周一次 (默认周日18:00)',
      primary_model: 'gemini-4-hydrogen',
      fallback_chain: [
        'gemini-3.8-flash',
        'gemini-3.6-flash',
        'gemini-3-flash',
        'gemini-2.5-flash',
        'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite',
      ],
      duties: '追踪全球 23 家大模型实验室一线进展、筛选本周 S/A 级重大事件与下周前瞻。',
    },
    {
      module_id: 'finance_impact',
      module_name: '股市传导映射 & 标的影响推导',
      cadence: '随简报主链每小时运行',
      primary_model: 'gemini-3.5-flash-lite',
      fallback_chain: [
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite',
        'gemini-3.8-flash',
        'gemini-3.6-flash',
        'gemini-3-flash',
        'gemini-2.5-flash',
      ],
      duties: '高频结构化输出事件对 A/港/美股板块及大宗商品的多空传导路径，优先使用 500 RPD 高吞吐模型。',
    },
    {
      module_id: 'bilingual_tools_matrix',
      module_name: '全站中英双语翻译 / GitHub 工具与模型矩阵',
      cadence: '随每小时批次回填',
      primary_model: 'gemini-3.5-flash-lite',
      fallback_chain: ['gemini-3.1-flash-lite', 'gemini-2.5-flash-lite'],
      duties: '批量翻译标题/摘要、提炼开源 AI 工具与大模型评测对比表。',
    },
    {
      module_id: 'predictions_arena',
      module_name: '预测市场出题 / 衍生研判 / 自动结算',
      cadence: '每日发题 + 盘后结算',
      primary_model: 'gemini-3.5-flash-lite',
      fallback_chain: [
        'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite',
        'gemini-3.8-flash',
        'gemini-3.6-flash',
        'gemini-3-flash',
        'gemini-2.5-flash',
      ],
      duties: '高并发生成/检验可验证市场竞猜命题并输出结算理由。',
    },
    {
      module_id: 'worker_qa',
      module_name: '前台用户实时「AI 证据问答」',
      cadence: '用户主动提问按需触发',
      primary_model: 'gemini-2.5-flash',
      fallback_chain: ['worker-grounded-rag'],
      duties: '优先调用 Worker 环境变量 GEMINI_MODEL（默认 gemini-2.5-flash）；若无 Key 或上游超时则 0 成本秒切本地证据检索合成。',
    },
  ],
  switch_rules: [
    {
      trigger: 'Soft-RPD 日配额防打爆保护',
      title: '接近单 Key 日上限即跳过该模型',
      behavior:
        'Tier1 模型达到 18/20 次/日、Tier2 模型达到 475/500 次/日，先轮换给当天剩余配额最宽裕的其他 Key；若 13 把 Key 均达上限，立即降级切换下一顺位模型。',
    },
    {
      trigger: 'RPM 并发防抖跳过',
      title: '距离同 Key+模型上次调用不足间隔时换路',
      behavior:
        '5 RPM 模型间隔 < 13s、15 RPM 模型间隔 < 4.2s 时，优先挑选已冷却好的 Key；若有备用模型可立即可用，直接切到下一模型避免触发 429。',
    },
    {
      trigger: '503 高负载 / 504 网关超时',
      title: '一击即切（0 秒废重试）',
      behavior:
        '单次遇到 503 Unavailable/High Demand 或 504/Timeout，立即在本轮标记该模型不可用并无缝切换顺位下一模型，避免浪费 GitHub Actions 运行时长。',
    },
    {
      trigger: '429 速率/日配额触顶',
      title: '短冷却 60 秒 / 日配额耗尽隔离 6 小时',
      behavior:
        '按分钟限流仅冷却该 Key+模型 60 秒并立刻换下一把 Key；若是 Per-Day RPD 耗尽，则将该 Key 的对应模型锁定 6 小时，其他模型仍可正常使用该 Key。',
    },
    {
      trigger: '404 / 模型名不可用',
      title: '动态校准 models.list 别名并跳过不可用名',
      behavior:
        '每 6 小时自动拉取一次真实可用模型 slug（例如把 gemini-3-flash 映射到 gemini-3-flash-preview）；若仍遇 404，立刻跳至后续替代模型。',
    },
    {
      trigger: 'Key 失效（401/403）或全池暂竭',
      title: '隔离坏 Key + 全链无密钥/缓存保底',
      behavior:
        '鉴权失败的 Key 整把隔离 24 小时不阻塞其余 Key；即便所有 Key 暂不可用，流水线仍会自动沿用上一有效简报与规则降级，确保网站不断更。',
    },
  ],
}

export function canonicalizeModelSlug(modelName: string): string {
  const slug = String(modelName || '')
    .trim()
    .toLowerCase()
    .replace(/^models\//, '')
  if (!slug) return 'unknown'
  if (MODEL_SPEC_MAP.has(slug)) return slug
  if (slug.includes('worker-grounded')) return 'worker-grounded-rag'
  if (slug.includes('gemini') && slug.includes('4') && slug.includes('hydrogen') && !slug.includes('lite')) {
    return 'gemini-4-hydrogen'
  }
  if (slug.includes('gemini') && slug.includes('3.8') && slug.includes('flash') && !slug.includes('lite')) {
    return 'gemini-3.8-flash'
  }
  if (slug.includes('gemini') && slug.includes('3.6') && slug.includes('flash') && !slug.includes('lite')) {
    return 'gemini-3.6-flash'
  }
  if (
    slug.includes('gemini') &&
    (slug.includes('3-flash') || slug.includes('3.0-flash')) &&
    !slug.includes('lite') &&
    !slug.includes('3.1') &&
    !slug.includes('3.5') &&
    !slug.includes('3.6') &&
    !slug.includes('3.8')
  ) {
    return 'gemini-3-flash'
  }
  if (slug.includes('gemini') && slug.includes('2.5') && slug.includes('flash') && !slug.includes('lite')) {
    return 'gemini-2.5-flash'
  }
  if (slug.includes('gemini') && slug.includes('3.5') && slug.includes('flash') && slug.includes('lite')) {
    return 'gemini-3.5-flash-lite'
  }
  if (slug.includes('gemini') && slug.includes('3.1') && slug.includes('flash') && slug.includes('lite')) {
    return 'gemini-3.1-flash-lite'
  }
  if (slug.includes('gemini') && slug.includes('2.5') && slug.includes('flash') && slug.includes('lite')) {
    return 'gemini-2.5-flash-lite'
  }
  return slug
}

function cstPartsFromMs(ms: number): { day: string; hour: number; min: number; sec: number } {
  const d = new Date(ms + 8 * 3600_000)
  return {
    day: d.toISOString().slice(0, 10),
    hour: d.getUTCHours(),
    min: d.getUTCMinutes(),
    sec: d.getUTCSeconds(),
  }
}

export function addDaysCst(dayStr: string, deltaDays: number): string {
  const ms = Date.parse(`${dayStr}T12:00:00+08:00`) + deltaDays * 86_400_000
  return new Date(ms + 8 * 3600_000).toISOString().slice(0, 10)
}

function cstIsoFromDayHour(dayStr: string, hour: number, min = 0, sec = 0): string {
  const hh = String(hour).padStart(2, '0')
  const mm = String(min).padStart(2, '0')
  const ss = String(sec).padStart(2, '0')
  return `${dayStr}T${hh}:${mm}:${ss}+08:00`
}

export type AiWindowMode = 'settled_21h' | 'rolling_24h' | 'current_cycle'

export interface SettlementWindowInfo {
  mode: AiWindowMode
  settlement_day: string
  latest_settled_day: string
  start_ms: number
  end_ms: number
  start_cst: string
  end_cst: string
  label: string
  next_settlement_cst: string
  is_frozen?: boolean
  frozen_at_cst?: string | null
}

export function resolve21hSettlementWindow(
  modeParam?: string,
  dayParam?: string,
  nowMs = Date.now(),
): SettlementWindowInfo {
  const { day: todayCst, hour: cstHour } = cstPartsFromMs(nowMs)
  const latestSettledDay = cstHour >= 21 ? todayCst : addDaysCst(todayCst, -1)
  const nextSettlementDay = addDaysCst(latestSettledDay, 1)
  const nextSettlementCst = cstIsoFromDayHour(nextSettlementDay, 21)

  const normMode: AiWindowMode =
    modeParam === 'rolling_24h' || modeParam === 'current_cycle' || modeParam === 'settled_21h'
      ? modeParam
      : 'settled_21h'

  if (normMode === 'rolling_24h') {
    const startMs = nowMs - 86_400_000
    return {
      mode: 'rolling_24h',
      settlement_day: todayCst,
      latest_settled_day: latestSettledDay,
      start_ms: startMs,
      end_ms: nowMs + 1,
      start_cst: cstIsoFromDayHour(cstPartsFromMs(startMs).day, cstPartsFromMs(startMs).hour, cstPartsFromMs(startMs).min),
      end_cst: cstIsoFromDayHour(todayCst, cstHour, cstPartsFromMs(nowMs).min),
      label: '实时滚动近 24 小时（含当前实时调用）',
      next_settlement_cst: nextSettlementCst,
    }
  }

  if (normMode === 'current_cycle') {
    const startDay = latestSettledDay
    const endDay = nextSettlementDay
    const startCst = cstIsoFromDayHour(startDay, 21)
    const endCst = cstIsoFromDayHour(endDay, 21)
    return {
      mode: 'current_cycle',
      settlement_day: endDay,
      latest_settled_day: latestSettledDay,
      start_ms: Date.parse(startCst),
      end_ms: Date.parse(endCst),
      start_cst: startCst,
      end_cst: endCst,
      label: `本轮累计（${startDay} 21:00 ~ ${endDay} 21:00 结算）`,
      next_settlement_cst: nextSettlementCst,
    }
  }

  const cleanDay = String(dayParam || '').trim()
  const settlementDay =
    /^\d{4}-\d{2}-\d{2}$/.test(cleanDay) && cleanDay <= latestSettledDay ? cleanDay : latestSettledDay
  const prevDay = addDaysCst(settlementDay, -1)
  const startCst = cstIsoFromDayHour(prevDay, 21)
  const endCst = cstIsoFromDayHour(settlementDay, 21)
  return {
    mode: 'settled_21h',
    settlement_day: settlementDay,
    latest_settled_day: latestSettledDay,
    start_ms: Date.parse(startCst),
    end_ms: Date.parse(endCst),
    start_cst: startCst,
    end_cst: endCst,
    label: `${settlementDay} 21:00 固定日结（前 24h：${prevDay} 21:00 ~ ${settlementDay} 21:00）`,
    next_settlement_cst: nextSettlementCst,
  }
}

export interface NormalizedAiUsageEvent {
  id: string
  ts_cst: string
  ts_ms: number
  source: string
  scope: string
  tier: string
  primary_model: string
  model_canonical: string
  model_actual: string
  is_fallback: boolean
  key_slot: string
  key_fingerprint: string
  ok: boolean
  error_code: string | null
  prompt_tokens: number
  output_tokens: number
  total_tokens: number
  token_source: string
  latency_ms: number
}

export async function recordWorkerAiUsageEvent(
  db: D1Database,
  input: {
    id: string
    tsCst?: string
    tsMs?: number
    scope?: string
    tier?: string
    primaryModel: string
    modelActual: string
    isFallback?: boolean
    keySlot?: string
    keyFingerprint?: string
    ok: boolean
    errorCode?: string | null
    promptTokens?: number
    outputTokens?: number
    totalTokens?: number
    tokenSource?: string
    latencyMs?: number
  },
): Promise<void> {
  const tsMs = input.tsMs ?? Date.now()
  const tsCst = input.tsCst ?? nowShanghaiIso()
  const canon = canonicalizeModelSlug(input.modelActual || input.primaryModel)
  const primCanon = canonicalizeModelSlug(input.primaryModel || canon)
  await db
    .prepare(
      `INSERT OR REPLACE INTO ai_usage_events (
        id, ts_cst, ts_ms, source, scope, tier, primary_model, model_canonical, model_actual,
        is_fallback, key_slot, key_fingerprint, ok, error_code,
        prompt_tokens, output_tokens, total_tokens, token_source, latency_ms
      ) VALUES (?1, ?2, ?3, 'worker', ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)`,
    )
    .bind(
      input.id,
      tsCst,
      tsMs,
      input.scope || 'worker_qa',
      input.tier || 'tier1',
      primCanon,
      canon,
      input.modelActual || primCanon,
      input.isFallback ? 1 : 0,
      input.keySlot || 'WORKER_GEMINI_API_KEY',
      input.keyFingerprint || '',
      input.ok ? 1 : 0,
      input.errorCode ?? null,
      Math.max(0, Math.round(Number(input.promptTokens ?? 0))),
      Math.max(0, Math.round(Number(input.outputTokens ?? 0))),
      Math.max(0, Math.round(Number(input.totalTokens ?? 0))),
      input.tokenSource || 'none',
      Math.max(0, Math.round(Number(input.latencyMs ?? 0))),
    )
    .run()
}

export async function cleanupOldAiUsageEvents(db: D1Database, keepDays = 16): Promise<void> {
  const cutoffMs = Date.now() - keepDays * 86_400_000
  await db.prepare('DELETE FROM ai_usage_events WHERE ts_ms < ?1').bind(cutoffMs).run()
}

interface QuotaStateDoc {
  schema_version?: string
  date_utc?: string
  updated_at?: string
  resolved_models?: Record<string, string>
  resolved_models_at?: string
  keys?: Record<
    string,
    {
      slot?: string
      fingerprint?: string
      date_utc?: string
      daily_calls?: number
      daily_tokens?: number
      model_daily_calls?: Record<string, number>
      model_daily_tokens?: Record<string, number>
      cooldown_until?: string | null
      exhausted_until?: string | null
      model_cooldown_until?: Record<string, string>
      model_exhausted_until?: Record<string, string>
      last_error_code?: string | null
      last_error?: string | null
      last_success_at?: string | null
      consecutive_errors?: number
    }
  >
}

interface R2TelemetryDoc {
  schema_version?: string
  updated_at?: string
  updated_at_cst?: string
  events?: Array<Record<string, unknown>>
}

async function readR2JsonSafe<T>(env: Env, key: string): Promise<T | null> {
  try {
    const obj = await env.R2_DATA.get(key)
    if (!obj) return null
    return (await obj.json()) as T
  } catch {
    return null
  }
}

function normalizeR2Event(raw: Record<string, unknown>): NormalizedAiUsageEvent | null {
  const tsMs = Number(raw.ts_ms || 0)
  if (!Number.isFinite(tsMs) || tsMs <= 0) return null
  const modelAct = String(raw.model_actual || raw.model || '')
  const modelCanon = canonicalizeModelSlug(String(raw.model || modelAct))
  const prim = canonicalizeModelSlug(String(raw.primary_model || modelCanon))
  return {
    id: String(raw.id || `r2_${tsMs}_${raw.key_slot || 'k'}`),
    ts_cst: String(raw.ts_cst || raw.ts_utc || ''),
    ts_ms: tsMs,
    source: String(raw.source || 'pipeline'),
    scope: String(raw.scope || 'default'),
    tier: String(raw.tier || 'tier1'),
    primary_model: prim,
    model_canonical: modelCanon,
    model_actual: modelAct || modelCanon,
    is_fallback: Boolean(raw.is_fallback) || (prim !== 'unknown' && prim !== modelCanon),
    key_slot: String(raw.key_slot || 'unknown'),
    key_fingerprint: String(raw.key_fingerprint || ''),
    ok: raw.ok !== false && raw.ok !== 0,
    error_code: raw.error_code ? String(raw.error_code) : null,
    prompt_tokens: Math.max(0, Math.round(Number(raw.prompt_tokens || 0))),
    output_tokens: Math.max(0, Math.round(Number(raw.output_tokens || 0))),
    total_tokens: Math.max(0, Math.round(Number(raw.total_tokens || 0))),
    token_source: String(raw.token_source || 'none'),
    latency_ms: Math.max(0, Math.round(Number(raw.latency_ms || 0))),
  }
}

function resolveKeyLiveStatus(
  slotName: string,
  rec: NonNullable<QuotaStateDoc['keys']>[string] | undefined,
  nowMs: number,
): 'healthy' | 'cooldown' | 'exhausted' | 'unconfigured' {
  if (!rec) {
    return slotName === 'WORKER_GEMINI_API_KEY' ? 'healthy' : 'unconfigured'
  }
  const exMs = rec.exhausted_until ? Date.parse(rec.exhausted_until) : 0
  if (Number.isFinite(exMs) && exMs > nowMs) return 'exhausted'
  const modExValues = Object.values(rec.model_exhausted_until || {})
  if (modExValues.some((v) => Number.isFinite(Date.parse(v)) && Date.parse(v) > nowMs)) {
    return 'exhausted'
  }
  const cdMs = rec.cooldown_until ? Date.parse(rec.cooldown_until) : 0
  if (Number.isFinite(cdMs) && cdMs > nowMs) return 'cooldown'
  const modCdValues = Object.values(rec.model_cooldown_until || {})
  if (modCdValues.some((v) => Number.isFinite(Date.parse(v)) && Date.parse(v) > nowMs)) {
    return 'cooldown'
  }
  return 'healthy'
}

function computeHourlyBuckets(
  win: SettlementWindowInfo,
  events: NormalizedAiUsageEvent[],
  nowMs: number,
) {
  let anchorStartMs = win.start_ms
  if (win.mode === 'rolling_24h') {
    const cstHourStart = Math.floor((nowMs + 8 * 3600_000) / 3600_000) * 3600_000 - 8 * 3600_000
    anchorStartMs = cstHourStart - 23 * 3600_000
  }

  const buckets = Array.from({ length: 24 }, (_, idx) => {
    const slotMs = anchorStartMs + idx * 3600_000
    const parts = cstPartsFromMs(slotMs)
    return {
      idx,
      hour: parts.hour,
      day_cst: parts.day,
      label: `${String(parts.hour).padStart(2, '0')}:00`,
      total_tokens: 0,
      prompt_tokens: 0,
      output_tokens: 0,
      calls: 0,
      ok_calls: 0,
      error_calls: 0,
      fallback_calls: 0,
      top_model: '',
      _modelTokens: new Map<string, number>(),
      _modelCalls: new Map<string, number>(),
    }
  })

  for (const ev of events) {
    if (ev.ts_ms < win.start_ms || ev.ts_ms >= win.end_ms) continue
    const bIdx = Math.floor((ev.ts_ms - anchorStartMs) / 3600_000)
    if (bIdx < 0 || bIdx >= 24) continue
    const b = buckets[bIdx]
    b.calls += 1
    if (ev.ok) b.ok_calls += 1
    else b.error_calls += 1
    if (ev.is_fallback) b.fallback_calls += 1
    b.prompt_tokens += ev.prompt_tokens
    b.output_tokens += ev.output_tokens
    b.total_tokens += ev.total_tokens
    b._modelTokens.set(ev.model_canonical, (b._modelTokens.get(ev.model_canonical) || 0) + ev.total_tokens)
    b._modelCalls.set(ev.model_canonical, (b._modelCalls.get(ev.model_canonical) || 0) + 1)
  }

  return buckets.map((b) => {
    let topModel = ''
    let bestScore = -1
    for (const [m, c] of b._modelCalls.entries()) {
      const score = (b._modelTokens.get(m) || 0) * 1000 + c
      if (score > bestScore) {
        bestScore = score
        topModel = m
      }
    }
    return {
      hour: b.hour,
      day_cst: b.day_cst,
      label: b.label,
      total_tokens: b.total_tokens,
      prompt_tokens: b.prompt_tokens,
      output_tokens: b.output_tokens,
      calls: b.calls,
      ok_calls: b.ok_calls,
      error_calls: b.error_calls,
      fallback_calls: b.fallback_calls,
      top_model: topModel,
    }
  })
}

async function loadWindowEvents(
  env: Env,
  win: SettlementWindowInfo,
): Promise<{
  events: NormalizedAiUsageEvent[]
  quotaDoc: QuotaStateDoc | null
  r2Doc: R2TelemetryDoc | null
}> {
  const [r2Telemetry, r2Quota, d1Rows] = await Promise.all([
    readR2JsonSafe<R2TelemetryDoc>(env, 'data/ai_usage_telemetry.json'),
    readR2JsonSafe<QuotaStateDoc>(env, 'data/gemini_quota_state.json'),
    env.DB.prepare(
      `SELECT id, ts_cst, ts_ms, source, scope, tier, primary_model, model_canonical, model_actual,
              is_fallback, key_slot, key_fingerprint, ok, error_code,
              prompt_tokens, output_tokens, total_tokens, token_source, latency_ms
       FROM ai_usage_events
       WHERE ts_ms >= ?1 AND ts_ms < ?2
       ORDER BY ts_ms DESC
       LIMIT 3000`,
    )
      .bind(win.start_ms, win.end_ms)
      .all<Record<string, unknown>>(),
  ])

  const merged = new Map<string, NormalizedAiUsageEvent>()
  for (const row of d1Rows.results || []) {
    const ev = normalizeR2Event(row)
    if (ev && ev.ts_ms >= win.start_ms && ev.ts_ms < win.end_ms) {
      merged.set(ev.id, ev)
    }
  }
  for (const raw of r2Telemetry?.events || []) {
    const ev = normalizeR2Event(raw)
    if (ev && ev.ts_ms >= win.start_ms && ev.ts_ms < win.end_ms && !merged.has(ev.id)) {
      merged.set(ev.id, ev)
    }
  }

  const events = Array.from(merged.values()).sort((a, b) => b.ts_ms - a.ts_ms)
  return { events, quotaDoc: r2Quota, r2Doc: r2Telemetry }
}

function buildCoreAggregates(
  env: Env,
  win: SettlementWindowInfo,
  events: NormalizedAiUsageEvent[],
  quotaDoc: QuotaStateDoc | null,
  r2Doc: R2TelemetryDoc | null,
  nowMs: number,
) {
  const hasPipelineEvents = events.some((e) => e.source === 'pipeline')
  const quotaUpdatedMs = quotaDoc?.updated_at ? Date.parse(quotaDoc.updated_at) : 0
  const quotaOverlapsWindow =
    Boolean(quotaDoc?.keys) &&
    Number.isFinite(quotaUpdatedMs) &&
    quotaUpdatedMs >= win.start_ms - 86_400_000 &&
    quotaUpdatedMs <= win.end_ms + 86_400_000
  const bootstrapFromQuota =
    !hasPipelineEvents &&
    quotaOverlapsWindow &&
    Object.values(quotaDoc?.keys || {}).some((k) => Number(k?.daily_calls || 0) > 0)

  const resolvedMap = quotaDoc?.resolved_models || {}
  const quotaKeyEntries = Object.entries(quotaDoc?.keys || {})
  const configuredPipelineKeys = Math.max(
    PIPELINE_CORE_KEY_SLOTS.filter((slot) => Boolean(quotaDoc?.keys?.[slot])).length,
    quotaKeyEntries.length,
    13,
  )

  const modelStatsMap = new Map<
    string,
    {
      model: string
      resolved_slug: string
      tier: 'tier1' | 'tier2' | 'edge'
      rpm_limit_per_key: number
      rpd_limit_per_key: number
      soft_rpd_per_key: number
      pool_rpd_capacity: number
      role_label: string
      duties: string
      calls: number
      ok_calls: number
      error_calls: number
      primary_calls: number
      fallback_calls: number
      prompt_tokens: number
      output_tokens: number
      total_tokens: number
      scopes: Set<string>
    }
  >()

  for (const spec of MODEL_CATALOG) {
    modelStatsMap.set(spec.model, {
      model: spec.model,
      resolved_slug: resolvedMap[spec.model] || spec.model,
      tier: spec.tier,
      rpm_limit_per_key: spec.rpm,
      rpd_limit_per_key: spec.rpd_per_key,
      soft_rpd_per_key: spec.soft_rpd_per_key,
      pool_rpd_capacity: spec.rpd_per_key > 0 ? spec.rpd_per_key * configuredPipelineKeys : 0,
      role_label: spec.role_label,
      duties: spec.duties,
      calls: 0,
      ok_calls: 0,
      error_calls: 0,
      primary_calls: 0,
      fallback_calls: 0,
      prompt_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      scopes: new Set<string>(),
    })
  }

  const keyStatsMap = new Map<
    string,
    {
      slot: string
      fingerprint: string
      status: 'healthy' | 'cooldown' | 'exhausted' | 'unconfigured'
      window_calls: number
      window_ok_calls: number
      window_error_calls: number
      window_rate_limit_calls: number
      window_fallback_calls: number
      window_tokens: number
      window_prompt_tokens: number
      window_output_tokens: number
      tier1_calls_today: number
      total_calls_today: number
      total_tokens_today: number
      last_success_at: string | null
      last_error_code: string | null
      last_error: string | null
      model_calls: Record<string, number>
    }
  >()

  const allSlots = new Set<string>(PIPELINE_CORE_KEY_SLOTS)
  for (const k of Object.keys(quotaDoc?.keys || {})) allSlots.add(k)
  if ((env.GEMINI_API_KEY || '').trim() || events.some((e) => e.key_slot === 'WORKER_GEMINI_API_KEY')) {
    allSlots.add('WORKER_GEMINI_API_KEY')
  }

  for (const slot of allSlots) {
    const qRec = quotaDoc?.keys?.[slot]
    const modDaily = qRec?.model_daily_calls || {}
    let t1Today = 0
    for (const [mKey, cnt] of Object.entries(modDaily)) {
      const cName = canonicalizeModelSlug(mKey)
      const sp = MODEL_SPEC_MAP.get(cName)
      if (!sp || sp.tier === 'tier1') t1Today += Number(cnt || 0)
    }
    keyStatsMap.set(slot, {
      slot,
      fingerprint: String(qRec?.fingerprint || ''),
      status: resolveKeyLiveStatus(slot, qRec, nowMs),
      window_calls: 0,
      window_ok_calls: 0,
      window_error_calls: 0,
      window_rate_limit_calls: 0,
      window_fallback_calls: 0,
      window_tokens: 0,
      window_prompt_tokens: 0,
      window_output_tokens: 0,
      tier1_calls_today: t1Today,
      total_calls_today: Number(qRec?.daily_calls || 0),
      total_tokens_today: Number(qRec?.daily_tokens || 0),
      last_success_at: qRec?.last_success_at || null,
      last_error_code: qRec?.last_error_code || null,
      last_error: qRec?.last_error || null,
      model_calls: {},
    })
  }

  let totalTokens = 0
  let promptTokens = 0
  let outputTokens = 0
  let exactTokenCalls = 0
  let estimatedTokenCalls = 0
  let okCalls = 0
  let errorCalls = 0
  let fallbackCalls = 0
  let rateLimitCalls = 0
  let pipelineCalls = 0
  let workerCalls = 0

  for (const ev of events) {
    if (ev.source === 'worker') workerCalls += 1
    else pipelineCalls += 1

    if (ev.ok) okCalls += 1
    else errorCalls += 1
    if (ev.is_fallback) fallbackCalls += 1
    if (ev.error_code === 'RATE_LIMIT_429' || ev.error_code === 'QUOTA_EXHAUSTED') rateLimitCalls += 1

    promptTokens += ev.prompt_tokens
    outputTokens += ev.output_tokens
    totalTokens += ev.total_tokens
    if (ev.token_source === 'exact') exactTokenCalls += 1
    else if (ev.token_source === 'estimated') estimatedTokenCalls += 1

    let mStat = modelStatsMap.get(ev.model_canonical)
    if (!mStat) {
      mStat = {
        model: ev.model_canonical,
        resolved_slug: ev.model_actual || ev.model_canonical,
        tier: ev.tier === 'tier2' ? 'tier2' : ev.model_canonical === 'worker-grounded-rag' ? 'edge' : 'tier1',
        rpm_limit_per_key: 0,
        rpd_limit_per_key: 0,
        soft_rpd_per_key: 0,
        pool_rpd_capacity: 0,
        role_label: '扩展 / 兜底模型',
        duties: '运行时动态解析到的模型或自定义兜底引擎',
        calls: 0,
        ok_calls: 0,
        error_calls: 0,
        primary_calls: 0,
        fallback_calls: 0,
        prompt_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        scopes: new Set<string>(),
      }
      modelStatsMap.set(ev.model_canonical, mStat)
    }
    mStat.calls += 1
    if (ev.ok) mStat.ok_calls += 1
    else mStat.error_calls += 1
    if (ev.is_fallback) mStat.fallback_calls += 1
    else mStat.primary_calls += 1
    mStat.prompt_tokens += ev.prompt_tokens
    mStat.output_tokens += ev.output_tokens
    mStat.total_tokens += ev.total_tokens
    if (ev.scope) mStat.scopes.add(ev.scope)

    let kStat = keyStatsMap.get(ev.key_slot)
    if (!kStat && ev.key_slot) {
      kStat = {
        slot: ev.key_slot,
        fingerprint: ev.key_fingerprint,
        status: 'healthy',
        window_calls: 0,
        window_ok_calls: 0,
        window_error_calls: 0,
        window_rate_limit_calls: 0,
        window_fallback_calls: 0,
        window_tokens: 0,
        window_prompt_tokens: 0,
        window_output_tokens: 0,
        tier1_calls_today: 0,
        total_calls_today: 0,
        total_tokens_today: 0,
        last_success_at: null,
        last_error_code: null,
        last_error: null,
        model_calls: {},
      }
      keyStatsMap.set(ev.key_slot, kStat)
    }
    if (kStat) {
      if (!kStat.fingerprint && ev.key_fingerprint) kStat.fingerprint = ev.key_fingerprint
      kStat.window_calls += 1
      if (ev.ok) kStat.window_ok_calls += 1
      else kStat.window_error_calls += 1
      if (ev.is_fallback) kStat.window_fallback_calls += 1
      if (ev.error_code === 'RATE_LIMIT_429' || ev.error_code === 'QUOTA_EXHAUSTED') {
        kStat.window_rate_limit_calls += 1
      }
      kStat.window_prompt_tokens += ev.prompt_tokens
      kStat.window_output_tokens += ev.output_tokens
      kStat.window_tokens += ev.total_tokens
      kStat.model_calls[ev.model_canonical] = (kStat.model_calls[ev.model_canonical] || 0) + 1
    }
  }

  // Bootstrap call & key rotation figures from gemini_quota_state.json before first telemetry batch arrives
  if (bootstrapFromQuota && quotaDoc?.keys) {
    for (const [slot, rec] of Object.entries(quotaDoc.keys)) {
      const kStat = keyStatsMap.get(slot)
      const calls = Number(rec?.daily_calls || 0)
      const toks = Number(rec?.daily_tokens || 0)
      if (kStat && calls > 0) {
        kStat.window_calls = calls
        kStat.window_ok_calls = rec?.last_error_code ? Math.max(0, calls - 1) : calls
        kStat.window_tokens = toks
        if (rec?.last_error_code === 'RATE_LIMIT_429' || rec?.last_error_code === 'QUOTA_EXHAUSTED') {
          kStat.window_rate_limit_calls = 1
        }
        for (const [rawM, cntRaw] of Object.entries(rec?.model_daily_calls || {})) {
          const cM = canonicalizeModelSlug(rawM)
          const cVal = Number(cntRaw || 0)
          if (cVal <= 0) continue
          kStat.model_calls[cM] = (kStat.model_calls[cM] || 0) + cVal
          const mStat = modelStatsMap.get(cM)
          if (mStat) {
            mStat.calls += cVal
            mStat.ok_calls += cVal
            mStat.primary_calls += cVal
          }
          okCalls += cVal
          pipelineCalls += cVal
        }
        const mToks = rec?.model_daily_tokens || {}
        for (const [rawM, tRaw] of Object.entries(mToks)) {
          const cM = canonicalizeModelSlug(rawM)
          const tVal = Number(tRaw || 0)
          const mStat = modelStatsMap.get(cM)
          if (mStat && tVal > 0) mStat.total_tokens += tVal
          totalTokens += tVal
        }
      }
    }
  }

  const totalCalls = okCalls + errorCalls
  const hoursSpan = 24
  const modelsList = Array.from(modelStatsMap.values()).map((m) => ({
    model: m.model,
    resolved_slug: m.resolved_slug,
    tier: m.tier,
    rpm_limit_per_key: m.rpm_limit_per_key,
    rpd_limit_per_key: m.rpd_limit_per_key,
    soft_rpd_per_key: m.soft_rpd_per_key,
    pool_rpd_capacity: m.pool_rpd_capacity,
    usage_pct_of_pool_rpd:
      m.pool_rpd_capacity > 0 ? Number(((m.calls / m.pool_rpd_capacity) * 100).toFixed(2)) : 0,
    role_label: m.role_label,
    duties: m.duties,
    calls: m.calls,
    avg_calls_per_hour: Number((m.calls / hoursSpan).toFixed(2)),
    ok_calls: m.ok_calls,
    error_calls: m.error_calls,
    primary_calls: m.primary_calls,
    fallback_calls: m.fallback_calls,
    prompt_tokens: m.prompt_tokens,
    output_tokens: m.output_tokens,
    total_tokens: m.total_tokens,
    token_share_pct: totalTokens > 0 ? Number(((m.total_tokens / totalTokens) * 100).toFixed(1)) : 0,
    avg_tokens_per_call: m.ok_calls > 0 ? Math.round(m.total_tokens / m.ok_calls) : 0,
    scopes: Array.from(m.scopes),
  }))

  const slotOrder = new Map<string, number>(PIPELINE_CORE_KEY_SLOTS.map((s, i) => [s, i]))
  const keysList = Array.from(keyStatsMap.values())
    .sort((a, b) => {
      if (a.slot === 'WORKER_GEMINI_API_KEY') return 1
      if (b.slot === 'WORKER_GEMINI_API_KEY') return -1
      const oa = slotOrder.get(a.slot) ?? 99
      const ob = slotOrder.get(b.slot) ?? 99
      if (oa !== ob) return oa - ob
      return a.slot.localeCompare(b.slot)
    })
    .map((k) => ({
      ...k,
      rotation_share_pct: totalCalls > 0 ? Number(((k.window_calls / totalCalls) * 100).toFixed(1)) : 0,
      tier1_rpd_limit: k.slot === 'WORKER_GEMINI_API_KEY' ? 20 : 120,
      total_rpd_limit: k.slot === 'WORKER_GEMINI_API_KEY' ? 20 : 1120,
    }))

  const healthyPipelineKeys = keysList.filter(
    (k) => k.slot !== 'WORKER_GEMINI_API_KEY' && k.status === 'healthy',
  ).length
  const cooledPipelineKeys = keysList.filter(
    (k) => k.slot !== 'WORKER_GEMINI_API_KEY' && k.status === 'cooldown',
  ).length
  const exhaustedPipelineKeys = keysList.filter(
    (k) => k.slot !== 'WORKER_GEMINI_API_KEY' && k.status === 'exhausted',
  ).length

  const tier1PoolRpd = configuredPipelineKeys * 120
  const totalPoolRpd = configuredPipelineKeys * 1120
  const tier1CallsWindow = modelsList
    .filter((m) => m.tier === 'tier1')
    .reduce((acc, m) => acc + m.calls, 0)
  const tier1UtilPct = tier1PoolRpd > 0 ? Number(((tier1CallsWindow / tier1PoolRpd) * 100).toFixed(2)) : 0
  const totalPoolUtilPct = totalPoolRpd > 0 ? Number(((pipelineCalls / totalPoolRpd) * 100).toFixed(2)) : 0
  const fallbackRatePct = totalCalls > 0 ? Number(((fallbackCalls / totalCalls) * 100).toFixed(1)) : 0

  let adviceLevel: 'ok' | 'watch' | 'expand' = 'ok'
  let adviceHeadline = '13-Key 额度充裕，暂无需额外扩充 Key'
  const adviceReasons: string[] = []
  if (exhaustedPipelineKeys >= 4 || totalPoolUtilPct >= 75 || (tier1UtilPct >= 80 && fallbackRatePct >= 35)) {
    adviceLevel = 'expand'
    adviceHeadline = '建议适时补充额外 Gemini API Key（深度队列或耗尽 Key 偏高）'
  } else if (exhaustedPipelineKeys >= 2 || cooledPipelineKeys >= 4 || tier1UtilPct >= 50 || fallbackRatePct >= 25) {
    adviceLevel = 'watch'
    adviceHeadline = '部分时段存在轮换降级或冷却，建议持续观察高并发期水位'
  }
  if (totalCalls > 0) {
    adviceReasons.push(
      `本周期 24h 累计调用 ${totalCalls} 次，占总密钥池 ${totalPoolRpd.toLocaleString()} 次/日理论上限的 ${totalPoolUtilPct}%；Tier1 深度推理链占用 ${tier1CallsWindow}/${tier1PoolRpd}（${tier1UtilPct}%）。`,
    )
    if (fallbackCalls > 0) {
      adviceReasons.push(`触发模型自动替补/降级 ${fallbackCalls} 次（占比 ${fallbackRatePct}%），均已通过备用模型完成无感续跑。`)
    }
    if (rateLimitCalls > 0) {
      adviceReasons.push(`出现 ${rateLimitCalls} 次 429/配额限流，若频繁在高峰时段发生可优先增加 2–4 个免费项目 Key 摊薄 RPM 压力。`)
    }
  } else {
    adviceReasons.push('当前 24h 窗口暂无 AI 调用事件记录；下一次整点跑批或前台 AI 问答后将自动入库展示。')
  }

  return {
    summary: {
      total_tokens: totalTokens,
      prompt_tokens: promptTokens,
      output_tokens: outputTokens,
      exact_token_calls: exactTokenCalls,
      estimated_token_calls: estimatedTokenCalls,
      total_calls: totalCalls,
      ok_calls: okCalls,
      error_calls: errorCalls,
      fallback_calls: fallbackCalls,
      fallback_rate_pct: fallbackRatePct,
      rate_limit_calls: rateLimitCalls,
      pipeline_calls: pipelineCalls,
      worker_calls: workerCalls,
      avg_calls_per_hour: Number((totalCalls / 24).toFixed(2)),
      avg_tokens_per_call: okCalls > 0 ? Math.round(totalTokens / okCalls) : 0,
      configured_pipeline_keys: configuredPipelineKeys,
      healthy_pipeline_keys: healthyPipelineKeys,
      cooled_pipeline_keys: cooledPipelineKeys,
      exhausted_pipeline_keys: exhaustedPipelineKeys,
      tier1_pool_rpd: tier1PoolRpd,
      total_pool_rpd: totalPoolRpd,
      tier1_util_pct: tier1UtilPct,
      total_pool_util_pct: totalPoolUtilPct,
    },
    capacity_advice: {
      level: adviceLevel,
      headline: adviceHeadline,
      reasons: adviceReasons,
    },
    hourly: computeHourlyBuckets(win, events, nowMs),
    models: modelsList,
    keys: keysList,
    recent_events: events.slice(0, 30),
    telemetry_status: {
      has_r2_telemetry: Boolean(r2Doc && Array.isArray(r2Doc.events) && r2Doc.events.length > 0),
      r2_updated_at: r2Doc?.updated_at || null,
      quota_state_updated_at: quotaDoc?.updated_at || null,
      bootstrap_from_quota_ledger: bootstrapFromQuota,
      worker_key_configured: Boolean((env.GEMINI_API_KEY || '').trim()),
    },
  }
}

export async function ensureLatest21hAiSnapshot(
  env: Env,
  nowMs = Date.now(),
  force = false,
): Promise<{ settlement_day: string; updated: boolean }> {
  const latestWin = resolve21hSettlementWindow('settled_21h', undefined, nowMs)
  const existing = await env.DB.prepare(
    'SELECT settlement_day, source_r2_updated_at, frozen_at_cst FROM ai_daily_21h_snapshots WHERE settlement_day = ?1',
  )
    .bind(latestWin.settlement_day)
    .first<{ settlement_day: string; source_r2_updated_at: string; frozen_at_cst: string }>()

  const { events, quotaDoc, r2Doc } = await loadWindowEvents(env, latestWin)
  const r2UpdatedAt = String(r2Doc?.updated_at || quotaDoc?.updated_at || '')

  if (!force && existing && (!r2UpdatedAt || r2UpdatedAt <= existing.source_r2_updated_at)) {
    return { settlement_day: latestWin.settlement_day, updated: false }
  }

  const core = buildCoreAggregates(env, latestWin, events, quotaDoc, r2Doc, nowMs)
  const frozenAt = nowShanghaiIso()
  const payloadToStore = {
    window: {
      ...latestWin,
      is_frozen: true,
      frozen_at_cst: frozenAt,
    },
    ...core,
  }

  await env.DB.prepare(
    `INSERT OR REPLACE INTO ai_daily_21h_snapshots (
       settlement_day, window_start_cst, window_end_cst, frozen_at_cst, source_r2_updated_at,
       total_tokens, prompt_tokens, output_tokens, total_calls, ok_calls, error_calls, fallback_calls, snapshot_json
     ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13)`,
  )
    .bind(
      latestWin.settlement_day,
      latestWin.start_cst,
      latestWin.end_cst,
      frozenAt,
      r2UpdatedAt,
      core.summary.total_tokens,
      core.summary.prompt_tokens,
      core.summary.output_tokens,
      core.summary.total_calls,
      core.summary.ok_calls,
      core.summary.error_calls,
      core.summary.fallback_calls,
      JSON.stringify(payloadToStore),
    )
    .run()

  return { settlement_day: latestWin.settlement_day, updated: true }
}

export async function getAdminAiUsageReport(
  env: Env,
  opts: { mode?: string; day?: string; nowMs?: number } = {},
): Promise<Record<string, unknown>> {
  const nowMs = opts.nowMs ?? Date.now()
  try {
    await ensureLatest21hAiSnapshot(env, nowMs, false)
  } catch {
    // Non-fatal if snapshot table hasn't rolled or R2 empty
  }

  const win = resolve21hSettlementWindow(opts.mode, opts.day, nowMs)
  const [snapListRes, liveQuotaDoc] = await Promise.all([
    env.DB.prepare(
      `SELECT settlement_day, window_start_cst, window_end_cst, frozen_at_cst,
              total_tokens, total_calls, fallback_calls
       FROM ai_daily_21h_snapshots
       ORDER BY settlement_day DESC
       LIMIT 14`,
    ).all<{
      settlement_day: string
      window_start_cst: string
      window_end_cst: string
      frozen_at_cst: string
      total_tokens: number
      total_calls: number
      fallback_calls: number
    }>(),
    readR2JsonSafe<QuotaStateDoc>(env, 'data/gemini_quota_state.json'),
  ])

  const availableDays = Array.from(
    new Set([
      win.latest_settled_day,
      ...(snapListRes.results || []).map((r) => r.settlement_day),
    ]),
  )
    .filter(Boolean)
    .sort((a, b) => b.localeCompare(a))

  if (win.mode === 'settled_21h') {
    const snapRow = await env.DB.prepare(
      'SELECT frozen_at_cst, source_r2_updated_at, snapshot_json FROM ai_daily_21h_snapshots WHERE settlement_day = ?1',
    )
      .bind(win.settlement_day)
      .first<{ frozen_at_cst: string; source_r2_updated_at: string; snapshot_json: string }>()
    if (snapRow?.snapshot_json) {
      try {
        const parsed = JSON.parse(snapRow.snapshot_json) as Record<string, unknown>
        // Overlay live key health status so admin always sees current Key cooldowns alongside frozen 24h stats
        if (Array.isArray(parsed.keys) && liveQuotaDoc?.keys) {
          parsed.keys = (parsed.keys as Array<Record<string, unknown>>).map((k) => {
            const slot = String(k.slot || '')
            const qRec = liveQuotaDoc.keys?.[slot]
            return {
              ...k,
              status: resolveKeyLiveStatus(slot, qRec, nowMs),
              last_error_code: qRec?.last_error_code ?? k.last_error_code ?? null,
              last_error: qRec?.last_error ?? k.last_error ?? null,
              last_success_at: qRec?.last_success_at ?? k.last_success_at ?? null,
            }
          })
        }
        return {
          ...parsed,
          window: {
            ...win,
            is_frozen: true,
            frozen_at_cst: snapRow.frozen_at_cst,
          },
          available_settlement_days: availableDays,
          recent_snapshots: snapListRes.results || [],
          model_routing_guide: MODEL_ROUTING_GUIDE,
        }
      } catch {
        // Fall through to live calculation
      }
    }
  }

  const { events, quotaDoc, r2Doc } = await loadWindowEvents(env, win)
  const core = buildCoreAggregates(env, win, events, quotaDoc, r2Doc, nowMs)
  return {
    window: {
      ...win,
      is_frozen: false,
      frozen_at_cst: null,
    },
    available_settlement_days: availableDays,
    recent_snapshots: snapListRes.results || [],
    ...core,
    model_routing_guide: MODEL_ROUTING_GUIDE,
  }
}
