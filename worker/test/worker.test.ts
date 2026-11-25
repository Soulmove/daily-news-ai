import { readFileSync } from 'node:fs'
import { DatabaseSync } from 'node:sqlite'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { decryptJson, encryptJson, hashPassword, signJwt, verifyJwt, verifyPassword } from '../src/crypto'
import { resetBootstrapCacheForTests } from '../src/db'
import { createWorkerApp } from '../src/index'
import type { Env } from '../src/types'

class MockD1PreparedStatement {
  private bound: unknown[] = []
  constructor(
    private readonly sqlite: DatabaseSync,
    private readonly sql: string,
  ) {}

  bind(...values: unknown[]) {
    this.bound = values
    return this
  }

  private execArgs() {
    // Convert SQLite `?N` numbered placeholders with possible sparse/reused indices if needed;
    // node:sqlite supports `?1`, `?2` natively, just normalize undefined -> null.
    return this.bound.map((v) => (v === undefined ? null : v)) as Array<string | number | bigint | Uint8Array | null>
  }

  async first<T = Record<string, unknown>>(colName?: string): Promise<T | null> {
    const stmt = this.sqlite.prepare(this.sql)
    const row = stmt.get(...this.execArgs()) as Record<string, unknown> | undefined
    if (!row) return null
    if (colName) return (row[colName] as T) ?? null
    return { ...row } as T
  }

  async all<T = Record<string, unknown>>(): Promise<{ results: T[]; success: boolean; meta: Record<string, unknown> }> {
    const stmt = this.sqlite.prepare(this.sql)
    const rows = stmt.all(...this.execArgs()) as Array<Record<string, unknown>>
    return {
      results: rows.map((r) => ({ ...r }) as T),
      success: true,
      meta: {},
    }
  }

  async run(): Promise<{ success: boolean; meta: { changes: number; last_row_id: number } }> {
    const stmt = this.sqlite.prepare(this.sql)
    const res = stmt.run(...this.execArgs())
    return {
      success: true,
      meta: {
        changes: Number(res.changes ?? 0),
        last_row_id: Number(res.lastInsertRowid ?? 0),
      },
    }
  }
}

class MockD1Database {
  public sqlite: DatabaseSync
  constructor(schemaSql: string) {
    this.sqlite = new DatabaseSync(':memory:')
    this.sqlite.exec('PRAGMA foreign_keys = ON;')
    this.sqlite.exec(schemaSql)
  }

  prepare(sql: string) {
    return new MockD1PreparedStatement(this.sqlite, sql)
  }

  async batch(stmts: Array<MockD1PreparedStatement>) {
    const results = []
    for (const st of stmts) {
      if (/\bSELECT\b|\bRETURNING\b/i.test((st as unknown as { sql: string }).sql)) {
        results.push(await st.all())
      } else {
        const r = await st.run()
        results.push({ results: [], ...r })
      }
    }
    return results
  }
}

class MockR2Bucket {
  public store = new Map<string, string>()

  put(key: string, val: unknown) {
    this.store.set(key, typeof val === 'string' ? val : JSON.stringify(val))
    return Promise.resolve({ key })
  }

  async get(key: string) {
    const raw = this.store.get(key)
    if (raw === undefined) return null
    return {
      text: async () => raw,
      json: async () => JSON.parse(raw),
      body: raw,
    }
  }
}

function createTestEnv(overrides: Partial<Env> = {}): { env: Env; r2: MockR2Bucket; db: MockD1Database } {
  const schemaPath = resolve(__dirname, '../migrations/0001_init.sql')
  const schemaSql = readFileSync(schemaPath, 'utf-8')
  const db = new MockD1Database(schemaSql)
  const r2 = new MockR2Bucket()
  const env: Env = {
    DB: db as unknown as D1Database,
    R2_DATA: r2 as unknown as R2Bucket,
    SITE_ACCESS_MODE: 'invite_only',
    SITE_PUBLIC_URL: 'https://mirrorinfo.xyz',
    DATA_PUBLIC_BASE_URL: 'https://data.mirrorinfo.xyz',
    ALLOWED_ORIGINS: 'https://mirrorinfo.xyz,https://www.mirrorinfo.xyz',
    GEMINI_MODEL: 'gemini-2.5-flash',
    JWT_SECRET: 'test-jwt-secret-key-for-mirrorbrief-2026-ci',
    DATA_ENCRYPTION_KEY: 'test-data-encryption-key-for-mirrorbrief-2026-ci',
    ADMIN_BOOTSTRAP_USER: 'admin',
    ADMIN_BOOTSTRAP_PASS: 'AdminPass123!',
    ...overrides,
  }
  return { env, r2, db }
}

describe('MirrorBrief Worker Crypto & API Suite', () => {
  beforeEach(() => {
    resetBootstrapCacheForTests()
    vi.restoreAllMocks()
  })

  it('uses native Web Crypto PBKDF2-SHA256, AES-256-GCM, and HS256 JWT cleanly within CPU budget', async () => {
    const t0 = performance.now()
    const hash = await hashPassword('MirrorPass99!')
    expect(hash.startsWith('pbkdf2_sha256$65000$')).toBe(true)
    expect(await verifyPassword('MirrorPass99!', hash)).toBe(true)
    expect(await verifyPassword('WrongPass99!', hash)).toBe(false)
    // Legacy pure-JS scrypt hashes must be rejected instantaneously without burning CPU
    expect(await verifyPassword('anything', 'scrypt$salt$hash')).toBe(false)

    const enc = await encryptJson({ notes: ['测试笔记'], muted: ['ev_1', 'ev_2'] }, 'secret-key-abc')
    expect(enc.startsWith('aes256gcm$')).toBe(true)
    const dec = await decryptJson<{ notes: string[]; muted: string[] }>(enc, 'secret-key-abc', {
      notes: [],
      muted: [],
    })
    expect(dec).toEqual({ notes: ['测试笔记'], muted: ['ev_1', 'ev_2'] })

    const token = await signJwt({ sub: 7, username: 'alice', role: 'user', ver: 1 }, 'jwt-secret-xyz')
    const claims = await verifyJwt(token, 'jwt-secret-xyz')
    expect(claims?.username).toBe('alice')
    expect(await verifyJwt(`${token}x`, 'jwt-secret-xyz')).toBeNull()
    const elapsedMs = performance.now() - t0
    expect(elapsedMs).toBeLessThan(1500)
  })

  it('enforces invite_only one-time invite codes, admin creation/revocation, and user state sync with counts.muted', async () => {
    const { env } = createTestEnv({ SITE_ACCESS_MODE: 'invite_only' })
    const app = createWorkerApp()

    // 1. Register without invite code -> rejected (422)
    const noInvResp = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'test-device-1001' },
        body: JSON.stringify({ username: 'alice01', password: 'Password123' }),
      },
      env,
    )
    expect(noInvResp.status).toBe(422)

    // 2. Admin login (auto-bootstrapped super_admin)
    const adminLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPass123!' }),
      },
      env,
    )
    expect(adminLogin.status).toBe(200)
    const adminSess = (await adminLogin.json()) as { token: string; user: { role: string } }
    expect(adminSess.user.role).toBe('super_admin')

    // 3. Create 2 invite codes, revoke 1
    const invCreate = await app.request(
      'https://mirrorinfo.xyz/api/admin/invite-codes',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminSess.token}`,
        },
        body: JSON.stringify({ count: 2, note: 'vip-batch', expires_days: 7 }),
      },
      env,
    )
    expect(invCreate.status).toBe(200)
    const { items: invs } = (await invCreate.json()) as { items: Array<{ code: string }> }
    expect(invs.length).toBe(2)

    const revokeResp = await app.request(
      `https://mirrorinfo.xyz/api/admin/invite-codes/${encodeURIComponent(invs[1].code)}`,
      {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${adminSess.token}` },
      },
      env,
    )
    expect(revokeResp.status).toBe(200)

    // 4. Register using valid invite code[0]
    const regOk = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'test-device-1002' },
        body: JSON.stringify({
          username: 'alice01',
          password: 'Password123',
          invite_code: invs[0].code,
        }),
      },
      env,
    )
    expect(regOk.status).toBe(200)
    const aliceSess = (await regOk.json()) as { token: string; user: { username: string } }
    expect(aliceSess.user.username).toBe('alice01')

    // 5. Reusing same code[0] or revoked code[1] must fail (403)
    const reuseResp = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'test-device-1003' },
        body: JSON.stringify({
          username: 'bob0001',
          password: 'Password123',
          invite_code: invs[0].code,
        }),
      },
      env,
    )
    expect(reuseResp.status).toBe(403)

    // 6. Cloud sync preserves counts.muted & strips ai_client_config
    const putState = await app.request(
      'https://mirrorinfo.xyz/api/user/state',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${aliceSess.token}`,
        },
        body: JSON.stringify({
          state: {
            watchlist: [{ id: 'nvda', label: '英伟达' }],
            muted: ['ev_spam_1', 'ev_spam_2'],
            ai_client_config: { apiKey: 'should-not-persist' },
          },
        }),
      },
      env,
    )
    expect(putState.status).toBe(200)
    const putData = (await putState.json()) as { ok: boolean; counts: { watchlist: number; muted: number } }
    expect(putData.counts.watchlist).toBe(1)
    expect(putData.counts.muted).toBe(2)

    const getState = await app.request(
      'https://mirrorinfo.xyz/api/user/state',
      { headers: { Authorization: `Bearer ${aliceSess.token}` } },
      env,
    )
    expect(getState.status).toBe(200)
    const got = (await getState.json()) as { has_state: boolean; state: Record<string, unknown>; counts: { muted: number } }
    expect(got.has_state).toBe(true)
    expect(got.counts.muted).toBe(2)
    expect(got.state.ai_client_config).toBeUndefined()
  })

  it('gates protected endpoints in private_gate mode until authenticated', async () => {
    const { env, r2 } = createTestEnv({ SITE_ACCESS_MODE: 'private_gate' })
    r2.put('data/live_wire.json', { status: 'ok', items: [{ id: 'w1', title: 'Test wire' }] })
    const app = createWorkerApp()

    const accessCfg = await app.request('https://mirrorinfo.xyz/api/public/access-config', {}, env)
    expect(accessCfg.status).toBe(200)
    const cfgJson = (await accessCfg.json()) as { access_mode: string; login_required: boolean }
    expect(cfgJson.access_mode).toBe('private_gate')
    expect(cfgJson.login_required).toBe(true)

    // Unauthenticated call to /api/wire/latest or /api/market/quotes must be gated (401)
    const gatedWire = await app.request('https://mirrorinfo.xyz/api/wire/latest', {}, env)
    expect(gatedWire.status).toBe(401)

    // Login as admin unlocks /api/wire/latest
    const loginResp = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPass123!' }),
      },
      env,
    )
    const { token } = (await loginResp.json()) as { token: string }
    const authedWire = await app.request(
      'https://mirrorinfo.xyz/api/wire/latest',
      { headers: { Authorization: `Bearer ${token}` } },
      env,
    )
    expect(authedWire.status).toBe(200)
  })

  it('never returns 500 on /api/market/quotes and falls back to R2 market_quotes.json when upstream fails', async () => {
    const { env, r2 } = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    r2.put('data/market_quotes.json', {
      schema_version: '5.2',
      updated_at: '2026-11-25T15:00:00+08:00',
      quote_time_hhmm: '15:00',
      session_status: 'closed',
      status: 'ok',
      indices: [{ ticker: '000001.SH', name: '上证指数', price: 3350.12, pct_change: 0.45, role: 'index' }],
      quotes: {
        '000001.SH': {
          symbol: 'sh000001',
          ticker: '000001.SH',
          name: '上证指数',
          market: 'A股',
          role: 'index',
          price: 3350.12,
          pct_change: 0.45,
          atr_20d_pct: 1.2,
        },
      },
    })
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Upstream timeout'))

    const app = createWorkerApp()
    const resp = await app.request('https://mirrorinfo.xyz/api/market/quotes', {}, env)
    expect(resp.status).toBe(200)
    const body = (await resp.json()) as { status: string; quotes: Record<string, { price: number }> }
    expect(body.quotes['000001.SH'].price).toBe(3350.12)
  })
})
