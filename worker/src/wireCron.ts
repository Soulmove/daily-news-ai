import { nowShanghaiIso, sha256Hex } from './crypto'
import { getDefaultEdgeCache } from './quotes'
import type { Env } from './types'

export const WIRE_CACHE_KEY = 'https://mirrorinfo.xyz/__edge_cache/wire_latest_v1'
export const AI_PROGRESS_CACHE_KEY = 'https://mirrorinfo.xyz/__edge_cache/ai_progress_latest_v1'

const HTML_RE = /<[^>]+>/g
const URL_TAIL_RE = /https?:\/\/\S+/gi

const AI_KW_RE =
  /(?:(?<![A-Za-z])ai(?![A-Za-z])|大模型|gemini|openai|gpt-\d|chatgpt|claude|anthropic|qwen|千问|kimi|混元|workbuddy|元宝|豆包|deepseek|算力|英伟达|nvidia|芯片|gpu|开源模型|智能体|具身智能|人形机器人)/i
const GEO_RE =
  /(?:导弹|空袭|无人机|击落|战机|航母|油轮|海峡|霍尔木兹|红海|国防|南海|军演|停火|和平协议|俄乌|美伊|以色列|加沙|北约|外交|元首|白宫|峰会|联合国)/i
const FIN_RE =
  /(?:a股|美股|港股|美联储|央行|降息|加息|黄金|原油|汇率|人民币|美元|纳指|标普|沪指|创业板|涨停|跌停|财报|ipo|关税|国债|cpi|非农|回购|比特币|以太坊|\bBTC\b|\bETH\b)/i
const GLOBAL_KW_RE =
  /(?:特朗普|拜登|白宫|欧盟|联合国|apec|峰会|外交|中东|俄乌|停火|制裁|总统|首相|外交部|美国商务部|美商务部|访华|日央行|欧洲央行)/i
const PROMO_FLUFF_RE =
  /(?:剧场版|动画电影|斗破苍穹|首支单曲|主题曲|演唱会|节气|天气预报|刑拘|逮捕|派出所|优惠券|拼多多|大促|首发价|促销|史低)/i

const HEAVY_GEO_RE =
  /(?:宣布停火|达成停火|停火协议|签署(?:和平|停火|安保|防务|贸易|关税|核)协议|开战|正式宣战|击落|遇袭|空袭|导弹袭击|关闭海峡|封锁航道|全面制裁|紧急状态|核武|军演|战机|航母)/i
const LOCAL_GOV_ROUTINE_RE =
  /(?:省委书记|省委常委|省长|副省长|市委书记|市长|副市长|区委书记|区长|县委书记|县长|省政协|市政协).{0,24}(?:会见|调研|考察|座谈|签约|致辞|出席|强调)|(?:会见|接待).{0,20}(?:董事长|总裁|CEO|一行|代表团)/i
const HEAVY_GOV_RE =
  /(?:中美元首|习近平|国务院总理|国务院常务会议|国常会|国务院(?:印发|发布|公布|批准|决定|出台)|证监会(?:发布|出台|宣布|印发)|发改委(?:发布|印发|宣布)|财政部(?:印发|宣布|发行|下达)|商务部(?:发布|宣布|决定|裁定|出台)|中国人民银行|中国央行|央行(?:宣布|决定|下调|上调|降息|降准)|美联储(?:宣布|决定|维持|加息|降息)|FOMC|鲍威尔|欧央行|欧洲央行|日本央行|特朗普(?:宣布|签署|下令)|白宫(?:宣布|发表声明))/i
const HEAVY_MKT_RE =
  /(?:纳指|标普|道指|沪指|恒生|英伟达|台积电|原油|布伦特|黄金).*(?:\d+(?:\.\d+)?%|\d+美元|历史新高|熔断|暴涨|暴跌|重挫|飙升)/i

function decodeBasicEntities(s: string): string {
  return s
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
}

function dedupRepeatedSentences(raw: string): string {
  let txt = String(raw || '').trim()
  if (!txt) return ''
  const half = Math.floor(txt.length / 2)
  if (half >= 10) {
    const h1 = txt.slice(0, half).trim().replace(/[\s。！!?.，,]+$/g, '')
    const h2 = txt.slice(half).trim().replace(/[\s。！!?.，,]+$/g, '')
    if (h1 && (h1 === h2 || h2.startsWith(h1.slice(0, Math.max(8, h1.length - 2))))) {
      txt = txt.slice(0, half).trim()
    }
  }
  const parts = txt.split(/(?<=[。！？!?;；])/g)
  const out: string[] = []
  let prevNorm = ''
  for (const rawPart of parts) {
    const p = rawPart.trim()
    if (!p) continue
    const norm = p.toLowerCase().replace(/[\s\-_·:：,，.。!！?？;；()（）[\]【】'"]+/g, '')
    if (!norm) continue
    if (prevNorm && (norm === prevNorm || (norm.length >= 8 && prevNorm.includes(norm)))) continue
    out.push(p)
    prevNorm = norm
  }
  return out.length > 0 ? out.join('') : txt
}

function cleanWireText(raw: unknown, maxLen = 240): string {
  if (!raw) return ''
  let s = decodeBasicEntities(String(raw).replace(HTML_RE, ' '))
  s = s.replace(URL_TAIL_RE, ' ').replace(/\s+/g, ' ').trim()
  s = dedupRepeatedSentences(s)
  return s.length > maxLen ? `${s.slice(0, maxLen - 1).trim()}…` : s
}

function isEmptyClockWire(title: string, excerpt = ''): boolean {
  const blob = !excerpt || excerpt === title ? title : `${title} ${excerpt}`
  const core = blob.replace(/[\s《》【】「」『』()（）[\],，.。!！?？:：;；\-—·'"]+/g, '')
  if (!core) return true
  if (!/\d/.test(blob)) {
    if (core.length <= 8) return true
    if (
      /(?:商品期货|股指期货|国债期货|国内期货|期市|欧股|美股|A股|港股)(?:早盘|午盘|夜盘)?(?:开盘|收盘|休市)/.test(core) &&
      core.length <= 18
    ) {
      return true
    }
    if (
      core.length < 14 &&
      !/(?:美联储|央行|降息|加息|通胀|证监会|交易所|发布|宣布|签署|批准|起诉|收购|裁员|停火|袭击|发射|上市|关税|制裁|总统|财长|英伟达|OpenAI|谷歌|华为|腾讯)/i.test(
        core,
      )
    ) {
      return true
    }
  }
  return false
}

function classifyWireItem(title: string, content: string, defaultCat: string): string {
  const text = `${title} ${content}`
  if (AI_KW_RE.test(text)) return 'tech'
  if (GEO_RE.test(text)) return 'global'
  if (FIN_RE.test(text)) return 'finance'
  if (GLOBAL_KW_RE.test(text)) return 'global'
  return defaultCat
}

export function inferSeverityAndTag(
  title: string,
  content: string,
  baseImportant: boolean,
): { tier: 'S' | 'A' | 'B'; reasonTag: string | null } {
  const text = `${title} ${content}`
  const isLocalRoutine = LOCAL_GOV_ROUTINE_RE.test(text)
  if (HEAVY_GEO_RE.test(text)) {
    return { tier: 'S', reasonTag: '地缘与军事突发' }
  }
  if (
    !isLocalRoutine &&
    HEAVY_GOV_RE.test(text) &&
    (baseImportant || /\d|宣布|决定|签署|批准|印发|出台|下调|关税|降息|加息/.test(text))
  ) {
    return { tier: 'A', reasonTag: '元首/央行表态' }
  }
  if (!isLocalRoutine && HEAVY_MKT_RE.test(text)) {
    return { tier: 'A', reasonTag: '大宗与市场剧震' }
  }
  if (!isLocalRoutine && baseImportant) {
    return { tier: 'A', reasonTag: '重磅' }
  }
  return { tier: 'B', reasonTag: null }
}

function epochToShanghaiIso(tsVal: unknown, fallbackIso: string): string {
  let num = Number(tsVal)
  if (!Number.isFinite(num) || num <= 0) return fallbackIso
  if (num > 1e12) num /= 1000
  if (num < 1_500_000_000) return fallbackIso
  const d = new Date(num * 1000 + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}+08:00`
}

function normalizeDedupKey(title: string): string {
  return title
    .toLowerCase()
    .replace(/【[^】]+】/g, '')
    .replace(/[\s\-_·:：,，.。!！?？()（）[\]【】'"%％0-9]+/g, '')
    .slice(0, 28)
}

export interface RawWireCandidate {
  id: string
  dedupKey: string
  sourceId: string
  sourceName: string
  category: string
  title: string
  excerpt: string
  url: string
  publishedAt: string
  fetchedAt: string
  importance: 'high' | 'normal'
  severityTier: 'S' | 'A' | 'B'
  heavyReasonTag: string | null
  metricLabel: string | null
  thumbnailUrl: string | null
}

async function fetchJsonWithTimeout(url: string, headers: Record<string, string>, timeoutMs = 3500): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const resp = await fetch(url, { headers, signal: controller.signal })
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

async function fetchWallstreetcnWireChannel(
  channel: 'global-channel' | 'tech-channel' | 'us-stock-channel',
  defaultCategory: 'finance' | 'tech' | 'global',
  sourceId: string,
  sourceName: string,
  fetchedIso: string,
): Promise<RawWireCandidate[]> {
  const urls = [
    `https://api-one.wallstcn.com/apiv1/content/lives?channel=${channel}&limit=20`,
    `https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=${channel}&limit=20`,
  ]
  let data: Record<string, unknown> | null = null
  for (const u of urls) {
    const res = await fetchJsonWithTimeout(u, {
      'User-Agent': 'Mozilla/5.0 MirrorBrief/5.2',
      Referer: 'https://wallstreetcn.com/',
    })
    if (res && typeof res === 'object') {
      data = res as Record<string, unknown>
      break
    }
  }
  const rows = ((data?.data as Record<string, unknown> | undefined)?.items as Array<Record<string, unknown>>) || []
  const out: RawWireCandidate[] = []
  for (const row of rows) {
    const content = cleanWireText(row.content_text || row.content, 260)
    let title = cleanWireText(row.title, 150)
    if (!title && content) {
      const m = content.match(/【([^】]{4,80})】/)
      title = m ? m[1] : cleanWireText(content, 88)
    }
    if (!title || title.length < 4 || PROMO_FLUFF_RE.test(title) || isEmptyClockWire(title, content)) continue
    const url = String(row.uri || `https://wallstreetcn.com/livenews/${row.id || ''}`).trim()
    const pubIso = epochToShanghaiIso(row.display_time, fetchedIso)
    const high = Number(row.score || 1) >= 2
    const sev = inferSeverityAndTag(title, content, high)
    const id = `wscn_${await sha256Hex(`${url}|${title}`)}`.slice(0, 32)
    out.push({
      id,
      dedupKey: normalizeDedupKey(title) || id,
      sourceId,
      sourceName,
      category: classifyWireItem(title, content, defaultCategory),
      title,
      excerpt: content && content !== title ? content : '',
      url,
      publishedAt: pubIso,
      fetchedAt: fetchedIso,
      importance: high || sev.tier !== 'B' ? 'high' : 'normal',
      severityTier: sev.tier,
      heavyReasonTag: sev.reasonTag,
      metricLabel: high ? '重要快讯' : null,
      thumbnailUrl: null,
    })
  }
  return out
}

async function fetchSinaWire(fetchedIso: string): Promise<RawWireCandidate[]> {
  const data = (await fetchJsonWithTimeout(
    'https://zhibo.sina.com.cn/api/zhibo/feed?zhibo_id=152&tag_id=0&page=1&page_size=20&type=0',
    { 'User-Agent': 'Mozilla/5.0 MirrorBrief/5.2', Referer: 'https://finance.sina.com.cn/7x24/' },
  )) as Record<string, unknown> | null
  const result = data?.result as Record<string, unknown> | undefined
  const dataObj = result?.data as Record<string, unknown> | undefined
  const feedObj = dataObj?.feed as Record<string, unknown> | undefined
  const rows = (feedObj?.list as Array<Record<string, unknown>>) || []
  const out: RawWireCandidate[] = []
  for (const row of rows) {
    if (!row || Number(row.is_delete || 0) === 1) continue
    const content = cleanWireText(row.rich_text, 260)
    if (!content || content.length < 6 || PROMO_FLUFF_RE.test(content)) continue
    const m = content.match(/【([^】]{4,80})】/)
    const title = m ? m[1] : cleanWireText(content, 88)
    if (!title || title.length < 4 || PROMO_FLUFF_RE.test(title) || isEmptyClockWire(title, content)) continue
    const url = String(row.docurl || `https://finance.sina.com.cn/7x24/?id=${row.id || ''}`).trim()
    const rawTime = String(row.create_time || '').trim()
    const pubIso = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(rawTime)
      ? `${rawTime.slice(0, 10)}T${rawTime.slice(11, 19)}+08:00`
      : fetchedIso
    const high = Number(row.is_focus || 0) === 1
    const sev = inferSeverityAndTag(title, content, high)
    const id = `sina_${await sha256Hex(`${url}|${title}`)}`.slice(0, 32)
    out.push({
      id,
      dedupKey: normalizeDedupKey(title) || id,
      sourceId: 'sina-7x24',
      sourceName: '新浪财经 7×24',
      category: classifyWireItem(title, content, 'finance'),
      title,
      excerpt: content && content !== title ? content : '',
      url,
      publishedAt: pubIso,
      fetchedAt: fetchedIso,
      importance: high || sev.tier !== 'B' ? 'high' : 'normal',
      severityTier: sev.tier,
      heavyReasonTag: sev.reasonTag,
      metricLabel: high ? '焦点快讯' : null,
      thumbnailUrl: null,
    })
  }
  return out
}

export async function runWireCron(env: Env): Promise<{ inserted: number; total_fetched: number; updated_at: string }> {
  const fetchedIso = nowShanghaiIso()
  const [wscnGlobal, wscnTech, sina] = await Promise.all([
    fetchWallstreetcnWireChannel('global-channel', 'finance', 'wscn-global-channel', '华尔街见闻 7×24', fetchedIso),
    fetchWallstreetcnWireChannel('tech-channel', 'tech', 'wscn-tech-channel', '华尔街见闻 科技AI', fetchedIso),
    fetchSinaWire(fetchedIso),
  ])

  const combined = [...wscnGlobal, ...wscnTech, ...sina].sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))
  const seenDedup = new Set<string>()
  const unique: RawWireCandidate[] = []
  for (const item of combined) {
    if (seenDedup.has(item.dedupKey)) continue
    seenDedup.add(item.dedupKey)
    unique.push(item)
  }

  if (unique.length > 0) {
    const stmts = unique.slice(0, 50).map((it) =>
      env.DB.prepare(
        `INSERT INTO live_wire_items (
           id, dedup_key, source_id, source_name, category, title, excerpt, url,
           published_at, fetched_at, importance, severity_tier, heavy_reason_tag, metric_label, thumbnail_url
         ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15)
         ON CONFLICT(id) DO UPDATE SET
           fetched_at = excluded.fetched_at,
           importance = excluded.importance,
           severity_tier = excluded.severity_tier,
           heavy_reason_tag = excluded.heavy_reason_tag`,
      ).bind(
        it.id,
        it.dedupKey,
        it.sourceId,
        it.sourceName,
        it.category,
        it.title,
        it.excerpt,
        it.url,
        it.publishedAt,
        it.fetchedAt,
        it.importance,
        it.severityTier,
        it.heavyReasonTag,
        it.metricLabel,
        it.thumbnailUrl,
      ),
    )
    await env.DB.batch(stmts)
    const staleCutoff = nowShanghaiIso(-72 * 3600_000)
    await env.DB.prepare('DELETE FROM live_wire_items WHERE published_at < ?1').bind(staleCutoff).run()
  }

  const cache = getDefaultEdgeCache()
  if (cache) {
    try {
      await cache.delete(new Request(WIRE_CACHE_KEY))
    } catch {
      // Ignore cache delete failures
    }
  }

  return { inserted: unique.length, total_fetched: combined.length, updated_at: fetchedIso }
}

const CAT_TAG_MAP: Record<string, string> = {
  finance: '金融市场',
  global: '全球动态',
  tech: 'AI与科技',
  general: '要闻速递',
}

export async function getWireLatestDoc(env: Env): Promise<Record<string, unknown>> {
  const rows = await env.DB.prepare(
    'SELECT * FROM live_wire_items ORDER BY published_at DESC LIMIT 80',
  ).all<{
    id: string
    dedup_key: string
    source_id: string
    source_name: string
    category: string
    title: string
    excerpt: string
    url: string
    published_at: string
    fetched_at: string
    importance: string
    severity_tier: string
    heavy_reason_tag: string | null
    metric_label: string | null
  }>()

  const results = rows.results || []
  if (results.length > 0) {
    const items = results.map((r) => ({
      id: r.id,
      title: r.title,
      excerpt: r.excerpt || r.title,
      category: r.category || 'finance',
      source_name: r.source_name,
      url: r.url,
      published_at: r.published_at,
      severity_tier: r.severity_tier || 'B',
      heavy_reason_tag: r.heavy_reason_tag,
      importance: r.importance || 'normal',
      tag: r.metric_label || CAT_TAG_MAP[r.category] || '实时快讯',
    }))

    const breaking = items
      .filter((it) => it.severity_tier === 'S' || it.severity_tier === 'A' || it.importance === 'high')
      .slice(0, 6)
      .map((it) => ({
        id: it.id,
        title: it.title,
        excerpt: it.excerpt,
        category: it.category,
        severity_tier: it.severity_tier,
        breaking_label: it.heavy_reason_tag || '重要快讯',
        source_name: it.source_name,
        url: it.url,
        published_at: it.published_at,
      }))

    const sourceNames = Array.from(new Set(items.map((it) => it.source_name))).join(' · ')
    const updatedAt = results[0].fetched_at || nowShanghaiIso()

    return {
      schema_version: '5.0',
      updated_at: updatedAt,
      generated_at: updatedAt,
      status: 'ok',
      sources_online: sourceNames || '华尔街见闻 · 财联社 · 新浪7×24',
      total: items.length,
      breaking_highlights: breaking,
      items,
    }
  }

  // Fallback gracefully to R2 live_wire.json synced by GitHub Actions
  try {
    const r2Obj = await env.R2_DATA.get('data/live_wire.json')
    if (r2Obj) {
      const parsed = (await r2Obj.json()) as Record<string, unknown>
      if (parsed && typeof parsed === 'object') return parsed
    }
  } catch {
    // Proceed to empty doc
  }

  return {
    schema_version: '5.0',
    updated_at: nowShanghaiIso(),
    generated_at: nowShanghaiIso(),
    status: 'empty',
    sources_online: 'Edge Cron Warming',
    total: 0,
    breaking_highlights: [],
    items: [],
  }
}
