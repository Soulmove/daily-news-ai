import { nowShanghaiIso } from './crypto'
import type { Env } from './types'

interface QuoteSymbolMeta {
  symbol: string
  ticker: string
  name: string
  name_en: string
  market: string
  role: 'index' | 'index_extra' | 'stock' | 'etf' | 'commodity'
}

export interface MarketQuoteEntry {
  symbol: string
  ticker: string
  name: string
  name_en: string
  market: string
  role: string
  price: number
  change: number | null
  pct_change: number | null
  atr_20d_pct: number | null
  quote_time_hhmm: string
  source: string
}

export interface MarketQuotesDoc {
  schema_version?: string
  updated_at: string
  quote_time_hhmm: string
  session_status: string
  status: string
  source_note: string
  source_note_en: string
  indices: MarketQuoteEntry[]
  quotes: Record<string, MarketQuoteEntry>
}

export const DEFAULT_QUOTE_SYMBOLS: QuoteSymbolMeta[] = [
  { symbol: 'sh000001', ticker: '000001.SH', name: '上证指数', name_en: 'SSE Composite', market: 'A股', role: 'index' },
  { symbol: 'sz399001', ticker: '399001.SZ', name: '深证成指', name_en: 'SZSE Component', market: 'A股', role: 'index' },
  { symbol: 'hkHSI', ticker: 'HSI.HK', name: '恒生指数', name_en: 'Hang Seng Index', market: '港股', role: 'index' },
  { symbol: 'hkHSTECH', ticker: 'HSTECH.HK', name: '恒生科指', name_en: 'Hang Seng Tech', market: '港股', role: 'index' },
  { symbol: 'usIXIC', ticker: 'IXIC', name: '纳斯达克', name_en: 'NASDAQ Composite', market: '美股', role: 'index' },
  { symbol: 'usINX', ticker: 'SPX', name: '标普500', name_en: 'S&P 500', market: '美股', role: 'index' },
  { symbol: 'sz399006', ticker: '399006.SZ', name: '创业板指', name_en: 'ChiNext Index', market: 'A股', role: 'index_extra' },
  { symbol: 'usNVDA', ticker: 'NVDA', name: '英伟达', name_en: 'NVIDIA', market: '美股', role: 'stock' },
  { symbol: 'usTSM', ticker: 'TSM', name: '台积电', name_en: 'TSMC', market: '美股', role: 'stock' },
  { symbol: 'usAMD', ticker: 'AMD', name: 'AMD', name_en: 'AMD', market: '美股', role: 'stock' },
  { symbol: 'usINTC', ticker: 'INTC', name: '英特尔', name_en: 'Intel', market: '美股', role: 'stock' },
  { symbol: 'usQQQ', ticker: 'QQQ', name: '纳指100ETF', name_en: 'Invesco QQQ', market: '美股', role: 'etf' },
  { symbol: 'usKWEB', ticker: 'KWEB', name: '中概互联ETF', name_en: 'KraneShares KWEB', market: '美股', role: 'etf' },
  { symbol: 'usGLD', ticker: 'GLD', name: '黄金ETF(美)', name_en: 'SPDR Gold GLD', market: '美股', role: 'commodity' },
  { symbol: 'usUSO', ticker: 'USO', name: '原油ETF(美)', name_en: 'US Oil USO', market: '美股', role: 'commodity' },
  { symbol: 'usCRWD', ticker: 'CRWD', name: 'CrowdStrike', name_en: 'CrowdStrike', market: '美股', role: 'stock' },
  { symbol: 'hk00700', ticker: '00700.HK', name: '腾讯控股', name_en: 'Tencent', market: '港股', role: 'stock' },
  { symbol: 'hk00981', ticker: '00981.HK', name: '中芯国际', name_en: 'SMIC', market: '港股', role: 'stock' },
  { symbol: 'hk00883', ticker: '00883.HK', name: '中国海油', name_en: 'CNOOC', market: '港股', role: 'stock' },
  { symbol: 'hk02899', ticker: '02899.HK', name: '紫金矿业', name_en: 'Zijin Mining', market: '港股', role: 'stock' },
  { symbol: 'sh512480', ticker: '512480.SH', name: 'A股半导体ETF', name_en: 'CN Semi ETF', market: 'A股', role: 'etf' },
  { symbol: 'sh515880', ticker: '515880.SH', name: 'A股通信ETF', name_en: 'CN Telecom ETF', market: 'A股', role: 'etf' },
  { symbol: 'sh518880', ticker: '518880.SH', name: '黄金ETF(A股)', name_en: 'CN Gold ETF', market: 'A股', role: 'commodity' },
  { symbol: 'sh601398', ticker: '601398.SH', name: '工商银行', name_en: 'ICBC', market: 'A股', role: 'stock' },
]

const SYMBOL_META = new Map(DEFAULT_QUOTE_SYMBOLS.map((d) => [d.symbol, d]))

const GOLD_FUTURE_META: Record<string, QuoteSymbolMeta> = {
  hf_GC: { symbol: 'hf_GC', ticker: 'GC=F', name: 'COMEX黄金', name_en: 'COMEX Gold', market: '商品', role: 'commodity' },
  hf_XAU: { symbol: 'hf_XAU', ticker: 'XAUUSD', name: '现货黄金', name_en: 'Spot Gold', market: '商品', role: 'commodity' },
}

const QUOTE_PRICE_BOUNDS: Record<string, [number, number]> = {
  'GC=F': [1500, 10000],
  XAUUSD: [1500, 10000],
  XAU: [1500, 10000],
  GLD: [100, 1000],
  '518880.SH': [2, 30],
  '000001.SH': [1500, 10000],
  '399001.SZ': [4000, 30000],
  '399006.SZ': [1000, 6000],
  'HSI.HK': [10000, 40000],
  'HSTECH.HK': [2000, 15000],
  IXIC: [8000, 40000],
  SPX: [2500, 12000],
}

function safeFloat(val: unknown): number | null {
  const n = Number(val)
  return Number.isFinite(n) ? n : null
}

export function isSaneQuote(
  ticker: string,
  role: string,
  price: number | null,
  pctChange: number | null,
  fallbackQuote?: MarketQuoteEntry | null,
): boolean {
  if (price === null || price <= 0) return false
  const bounds = QUOTE_PRICE_BOUNDS[ticker.toUpperCase()]
  if (bounds && (price < bounds[0] || price > bounds[1])) return false
  const maxPct = role === 'index' || role === 'index_extra' || role === 'commodity' ? 25 : 65
  if (pctChange !== null && Math.abs(pctChange) > maxPct) return false
  if (fallbackQuote && typeof fallbackQuote.price === 'number' && fallbackQuote.price > 0) {
    if (price >= fallbackQuote.price * 3 || price <= fallbackQuote.price * 0.3) return false
  }
  return true
}

function getShanghaiNowParts(): { iso: string; hhmm: string; sessionStatus: string } {
  const iso = nowShanghaiIso()
  const hhmm = iso.slice(11, 16)
  const dt = new Date(Date.now() + 8 * 3600_000)
  const day = dt.getUTCDay()
  if (day === 0 || day === 6) return { iso, hhmm, sessionStatus: 'closed' }
  const hm = dt.getUTCHours() * 60 + dt.getUTCMinutes()
  let sessionStatus = 'closed'
  if ((hm >= 9 * 60 + 15 && hm <= 11 * 60 + 35) || (hm >= 13 * 60 && hm <= 16 * 60 + 15) || hm >= 21 * 60 || hm <= 5 * 60 + 15) {
    sessionStatus = 'trading'
  } else if (hm > 11 * 60 + 35 && hm < 13 * 60) {
    sessionStatus = 'lunch_break'
  }
  return { iso, hhmm, sessionStatus }
}

export function parseTencentQuotes(
  text: string,
  quoteHhmm: string,
  fallbackQuotes: Record<string, MarketQuoteEntry>,
): Record<string, MarketQuoteEntry> {
  const out: Record<string, MarketQuoteEntry> = {}
  for (const chunk of text.split(';')) {
    const line = chunk.trim()
    const eqIdx = line.indexOf('=')
    if (eqIdx <= 0) continue
    const lhs = line.slice(0, eqIdx).trim()
    const rhs = line.slice(eqIdx + 1).trim().replace(/^"|"$/g, '')
    const sym = lhs.replace(/^v_s_/, '').replace(/^v_/, '')
    const meta = SYMBOL_META.get(sym)
    if (!meta) continue
    const parts = rhs.split('~')
    if (parts.length < 6) continue
    const price = safeFloat(parts[3])
    const change = safeFloat(parts[4])
    const pct = safeFloat(parts[5])
    const fbQ = fallbackQuotes[meta.ticker]
    if (!isSaneQuote(meta.ticker, meta.role, price, pct, fbQ)) continue
    out[meta.ticker] = {
      symbol: sym,
      ticker: meta.ticker,
      name: meta.name,
      name_en: meta.name_en,
      market: meta.market,
      role: meta.role,
      price: Number(price!.toFixed(price! < 20 ? 3 : 2)),
      change: change !== null ? Number(change.toFixed(Math.abs(change) < 5 ? 3 : 2)) : null,
      pct_change: pct !== null ? Number(pct.toFixed(2)) : null,
      atr_20d_pct: fbQ?.atr_20d_pct ?? null,
      quote_time_hhmm: quoteHhmm,
      source: 'Tencent Finance (Edge Live)',
    }
  }
  return out
}

export function parseSinaGoldQuotes(
  text: string,
  quoteHhmm: string,
  fallbackQuotes: Record<string, MarketQuoteEntry>,
): Record<string, MarketQuoteEntry> {
  const out: Record<string, MarketQuoteEntry> = {}
  for (const line of text.split(/\r?\n/)) {
    const eqIdx = line.indexOf('=')
    if (eqIdx <= 0 || !line.includes('hq_str_')) continue
    const sym = line.slice(0, eqIdx).split('hq_str_').pop()?.trim() || ''
    const meta = GOLD_FUTURE_META[sym]
    if (!meta) continue
    const rawVal = line.slice(eqIdx + 1).trim().replace(/;+$/g, '').replace(/^"|"$/g, '')
    const parts = rawVal.split(',')
    if (parts.length < 8) continue
    const price = safeFloat(parts[0])
    const prevClose = safeFloat(parts[7]) ?? safeFloat(parts[8])
    if (price === null || price <= 0) continue
    const change = prevClose && prevClose > 0 ? Number((price - prevClose).toFixed(2)) : null
    const pct = prevClose && prevClose > 0 ? Number((((price - prevClose) / prevClose) * 100).toFixed(2)) : null
    const fbQ = fallbackQuotes[meta.ticker]
    if (!isSaneQuote(meta.ticker, meta.role, price, pct, fbQ)) continue
    const rawTime = (parts[6] || '').trim()
    const srcTime = rawTime.includes(':') ? rawTime.slice(0, 5) : quoteHhmm
    out[meta.ticker] = {
      symbol: sym,
      ticker: meta.ticker,
      name: meta.name,
      name_en: meta.name_en,
      market: meta.market,
      role: meta.role,
      price: Number(price.toFixed(2)),
      change,
      pct_change: pct,
      atr_20d_pct: fbQ?.atr_20d_pct ?? 1.8,
      quote_time_hhmm: srcTime || quoteHhmm,
      source: 'Sina Finance COMEX/Spot Gold',
    }
  }
  return out
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timer)
  }
}

async function readR2FallbackQuotes(env: Env): Promise<MarketQuotesDoc | null> {
  try {
    const obj = await env.R2_DATA.get('data/market_quotes.json')
    if (!obj) return null
    const parsed = (await obj.json()) as MarketQuotesDoc
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

export async function fetchAndBuildMarketQuotes(env: Env): Promise<MarketQuotesDoc> {
  const { iso, hhmm, sessionStatus } = getShanghaiNowParts()
  const fallbackDoc = await readR2FallbackQuotes(env)
  const fbQuotes = fallbackDoc?.quotes && typeof fallbackDoc.quotes === 'object' ? fallbackDoc.quotes : {}
  const syms = DEFAULT_QUOTE_SYMBOLS.map((d) => `s_${d.symbol}`).join(',')

  const [qtRes, sinaRes] = await Promise.allSettled([
    fetchWithTimeout(
      `https://qt.gtimg.cn/q=${syms}`,
      { headers: { 'User-Agent': 'Mozilla/5.0 MirrorBrief/5.2' } },
      2800,
    ),
    fetchWithTimeout(
      'https://hq.sinajs.cn/list=hf_GC,hf_XAU',
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 MirrorBrief/5.2',
          Referer: 'https://finance.sina.com.cn',
        },
      },
      2500,
    ),
  ])

  let quotes: Record<string, MarketQuoteEntry> = {}
  let status = 'ok'

  if (qtRes.status === 'fulfilled' && qtRes.value.ok) {
    try {
      quotes = parseTencentQuotes(await qtRes.value.text(), hhmm, fbQuotes)
    } catch {
      status = 'fallback'
    }
  } else {
    status = 'fallback'
  }

  if (sinaRes.status === 'fulfilled' && sinaRes.value.ok) {
    try {
      const gold = parseSinaGoldQuotes(await sinaRes.value.text(), hhmm, fbQuotes)
      quotes = { ...quotes, ...gold }
    } catch {
      // Keep non-gold quotes
    }
  }

  for (const [tkr, fbQ] of Object.entries(fbQuotes)) {
    if (
      !(tkr in quotes) &&
      fbQ &&
      isSaneQuote(tkr, String(fbQ.role || 'stock'), safeFloat(fbQ.price), safeFloat(fbQ.pct_change))
    ) {
      quotes[tkr] = { ...fbQ }
    }
  }

  if (Object.keys(quotes).length === 0) {
    if (fallbackDoc) {
      return { ...fallbackDoc, status: 'cached_fallback' }
    }
    return {
      schema_version: '5.2',
      updated_at: iso,
      quote_time_hhmm: hhmm,
      session_status: sessionStatus,
      status: 'unavailable',
      source_note: '行情暂不可用，请稍后刷新',
      source_note_en: 'Market quotes temporarily unavailable',
      indices: [],
      quotes: {},
    }
  }

  const indices = DEFAULT_QUOTE_SYMBOLS.filter((d) => d.role === 'index' && d.ticker in quotes).map(
    (d) => quotes[d.ticker],
  )

  return {
    schema_version: '5.2',
    updated_at: iso,
    quote_time_hhmm: hhmm,
    session_status: sessionStatus,
    status: Object.keys(quotes).length > 0 ? status : 'cached_fallback',
    source_note: '实时 / 延迟行情参考（Edge Cache 45s + R2 热备）',
    source_note_en: 'Live / delayed quotes (Edge Cache 45s + R2 fallback)',
    indices,
    quotes,
  }
}

export function getDefaultEdgeCache(): Cache | null {
  try {
    const cs = (globalThis as unknown as { caches?: { default?: Cache } }).caches
    return cs?.default ?? null
  } catch {
    return null
  }
}

export const QUOTES_CACHE_KEY = 'https://mirrorinfo.xyz/__edge_cache/market_quotes_v1'
