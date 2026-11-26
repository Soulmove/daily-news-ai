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
  const schemaPath1 = resolve(__dirname, '../migrations/0001_init.sql')
  const schemaPath2 = resolve(__dirname, '../migrations/0002_growth_and_interactions.sql')
  const schemaPath3 = resolve(__dirname, '../migrations/0003_prediction_arena.sql')
  const schemaSql = `${readFileSync(schemaPath1, 'utf-8')}\n${readFileSync(schemaPath2, 'utf-8')}\n${readFileSync(schemaPath3, 'utf-8')}`
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

  it('falls back to env.SITE_ACCESS_MODE (and invite_only default) when D1 site_settings.access_mode is unset', async () => {
    const publicSetup = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    const appPublic = createWorkerApp()

    const pubSettings = await appPublic.request('https://mirrorinfo.xyz/api/public/settings', {}, publicSetup.env)
    expect(pubSettings.status).toBe(200)
    expect(pubSettings.headers.get('cache-control')).toBe('no-store')
    expect(await pubSettings.json()).toMatchObject({
      access_mode: 'public',
      invite_required: false,
      login_required: false,
    })

    const pubAccess = await appPublic.request('https://mirrorinfo.xyz/api/public/access-config', {}, publicSetup.env)
    expect(pubAccess.status).toBe(200)
    expect(pubAccess.headers.get('cache-control')).toBe('no-store')
    expect(await pubAccess.json()).toMatchObject({
      access_mode: 'public',
      invite_required: false,
      login_required: false,
    })

    const defaultSetup = createTestEnv({ SITE_ACCESS_MODE: undefined })
    const appDefault = createWorkerApp()
    const defSettings = await appDefault.request('https://mirrorinfo.xyz/api/public/settings', {}, defaultSetup.env)
    expect(defSettings.status).toBe(200)
    expect(await defSettings.json()).toMatchObject({
      access_mode: 'invite_only',
      invite_required: true,
      login_required: false,
    })

    const defAccess = await appDefault.request('https://mirrorinfo.xyz/api/public/access-config', {}, defaultSetup.env)
    expect(defAccess.status).toBe(200)
    expect(await defAccess.json()).toMatchObject({
      access_mode: 'invite_only',
      invite_required: true,
      login_required: false,
    })
  })

  it('allows super_admin to dynamically switch access_mode in D1 with live enforcement, RBAC/validation guards, and audit logs', async () => {
    const { env, r2, db } = createTestEnv({ SITE_ACCESS_MODE: 'invite_only' })
    await r2.put('data/live_wire.json', { status: 'ok', items: [{ id: 'w1', title: 'Live wire item' }] })
    const app = createWorkerApp()

    // 1. Login as super_admin
    const superLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPass123!' }),
      },
      env,
    )
    expect(superLogin.status).toBe(200)
    const superSess = (await superLogin.json()) as { token: string }

    // 2. Create Level-2 admin and login
    const createOps = await app.request(
      'https://mirrorinfo.xyz/api/admin/users',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ username: 'opsadmin', password: 'OpsPass123!', role: 'admin' }),
      },
      env,
    )
    expect(createOps.status).toBe(200)

    const opsLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'opsadmin', password: 'OpsPass123!' }),
      },
      env,
    )
    expect(opsLogin.status).toBe(200)
    const opsSess = (await opsLogin.json()) as { token: string }

    // 3. Level-2 admin cannot change access_mode -> 403
    const opsForbidden = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${opsSess.token}`,
        },
        body: JSON.stringify({ access_mode: 'public' }),
      },
      env,
    )
    expect(opsForbidden.status).toBe(403)
    const opsErr = (await opsForbidden.json()) as { detail: string }
    expect(opsErr.detail).toContain('仅一级最高管理员可修改全站访问门禁模式')

    // 4. Invalid mode or empty mode returns 400
    for (const badVal of ['invalid_mode', '']) {
      const badResp = await app.request(
        'https://mirrorinfo.xyz/api/admin/site-settings',
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${superSess.token}`,
          },
          body: JSON.stringify({ access_mode: badVal }),
        },
        env,
      )
      expect(badResp.status).toBe(400)
    }

    // 5. Initial mode (invite_only): register without invite code returns 422
    const initRegNoInv = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '198.51.100.1',
          'X-Device-ID': 'mode-test-dev-1',
        },
        body: JSON.stringify({ username: 'guest_inv_1', password: 'Password123' }),
      },
      env,
    )
    expect(initRegNoInv.status).toBe(422)

    // 6. Switch to 'public' -> live immediately without rebuilding Worker
    const toPublic = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ access_mode: 'public' }),
      },
      env,
    )
    expect(toPublic.status).toBe(200)
    expect(await toPublic.json()).toMatchObject({
      ok: true,
      access_mode: 'public',
      invite_required: false,
      login_required: false,
    })

    for (const path of ['/api/public/settings', '/api/public/access-config']) {
      const r = await app.request(`https://mirrorinfo.xyz${path}`, {}, env)
      expect(r.status).toBe(200)
      expect(await r.json()).toMatchObject({
        access_mode: 'public',
        invite_required: false,
        login_required: false,
      })
    }
    const adminCheckPub = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      { headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(adminCheckPub.status).toBe(200)
    expect(await adminCheckPub.json()).toMatchObject({
      access_mode: 'public',
      invite_required: false,
      login_required: false,
    })

    // Register without invite code succeeds immediately under 'public'
    const pubReg = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '198.51.100.2',
          'X-Device-ID': 'mode-test-dev-2',
        },
        body: JSON.stringify({ username: 'open_user_1', password: 'Password123' }),
      },
      env,
    )
    expect(pubReg.status).toBe(200)

    // 7. Switch to 'private_gate' -> live immediately
    const toPrivate = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ access_mode: 'private_gate' }),
      },
      env,
    )
    expect(toPrivate.status).toBe(200)
    expect(await toPrivate.json()).toMatchObject({
      ok: true,
      access_mode: 'private_gate',
      invite_required: true,
      login_required: true,
    })

    for (const path of ['/api/public/settings', '/api/public/access-config']) {
      const r = await app.request(`https://mirrorinfo.xyz${path}`, {}, env)
      expect(r.status).toBe(200)
      expect(await r.json()).toMatchObject({
        access_mode: 'private_gate',
        invite_required: true,
        login_required: true,
      })
    }

    const gatedWire = await app.request('https://mirrorinfo.xyz/api/wire/latest', {}, env)
    expect(gatedWire.status).toBe(401)
    const authedWire = await app.request(
      'https://mirrorinfo.xyz/api/wire/latest',
      { headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(authedWire.status).toBe(200)

    const privRegNoInv = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '198.51.100.3',
          'X-Device-ID': 'mode-test-dev-3',
        },
        body: JSON.stringify({ username: 'guest_priv_1', password: 'Password123' }),
      },
      env,
    )
    expect(privRegNoInv.status).toBe(422)

    // 8. Updating another setting preserves D1 access_mode and never stores derived keys
    const patchOther = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ monitor_public: true }),
      },
      env,
    )
    expect(patchOther.status).toBe(200)
    expect(await patchOther.json()).toMatchObject({
      monitor_public: true,
      access_mode: 'private_gate',
      invite_required: true,
      login_required: true,
    })
    const derivedRows = db.sqlite
      .prepare("SELECT key FROM site_settings WHERE key IN ('invite_required', 'login_required')")
      .all() as Array<{ key: string }>
    expect(derivedRows).toHaveLength(0)

    // 9. Switch back to 'invite_only' -> unauthenticated wire opens again, register requires invite
    const toInvite = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ access_mode: 'invite_only' }),
      },
      env,
    )
    expect(toInvite.status).toBe(200)

    const openWire = await app.request('https://mirrorinfo.xyz/api/wire/latest', {}, env)
    expect(openWire.status).toBe(200)
    const invRegNoCode = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '198.51.100.4',
          'X-Device-ID': 'mode-test-dev-4',
        },
        body: JSON.stringify({ username: 'guest_inv_2', password: 'Password123' }),
      },
      env,
    )
    expect(invRegNoCode.status).toBe(422)

    // 10. Audit logs contain clear access_mode transition records
    const auditResp = await app.request(
      'https://mirrorinfo.xyz/api/admin/audit-logs?limit=50',
      { headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(auditResp.status).toBe(200)
    const { logs } = (await auditResp.json()) as { logs: Array<{ action: string; detail: string }> }
    const modeLogs = logs.filter((l) => l.action === 'admin_change_access_mode').map((l) => l.detail)
    expect(modeLogs.some((d) => d.includes('invite_only -> public'))).toBe(true)
    expect(modeLogs.some((d) => d.includes('public -> private_gate'))).toBe(true)
    expect(modeLogs.some((d) => d.includes('private_gate -> invite_only'))).toBe(true)
  })

  it('supports 4-stage growth presets, RBAC 403, dynamic QA & crowd thresholds, referrals, waitlist & reactions', async () => {
    const { env, r2 } = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    const app = createWorkerApp()

    await r2.put(
      'data/manifest.json',
      JSON.stringify({
        generated_at: '2026-11-25T10:00:00+08:00',
        smart: { generated_at: '2026-11-25T10:00:00+08:00' },
      }),
    )
    await r2.put(
      'analysis_finance.json',
      JSON.stringify({
        events: [
          {
            event_id: 'ev_fomc_1',
            title: '美联储维持基准利率不变并释放年内降息信号',
            fact_summary: 'FOMC 声明称通胀继续朝 2% 回落。',
            sources: [{ source_name: '路透社', url: 'https://example.com/fomc' }],
            latest_reported_at: '2026-11-25T09:00:00+08:00',
          },
        ],
      }),
    )

    // Seed super_admin & sub-admin ('admin')
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
    const superSess = (await adminLogin.json()) as { token: string }

    const createSub = await app.request(
      'https://mirrorinfo.xyz/api/admin/users',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({ username: 'ops_mgr', password: 'OpsPassword123', role: 'admin' }),
      },
      env,
    )
    expect(createSub.status).toBe(200)

    const opsLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'ops_mgr', password: 'OpsPassword123' }),
      },
      env,
    )
    const opsSess = (await opsLogin.json()) as { token: string }

    // 1. Sub-admin gets 403 when touching growth settings; super_admin succeeds & public/settings updates live
    const subDenied = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${opsSess.token}`,
        },
        body: JSON.stringify({ guest_qa_daily_limit: 9 }),
      },
      env,
    )
    expect(subDenied.status).toBe(403)

    // Configure Stage 1 with tight QA limit = 2 and crowd unlock = 2
    const saveStage1 = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({
          growth_stage: 'stage_1_cold_start',
          access_mode: 'public',
          welcome_hero_enabled: true,
          soft_auth_prompts_enabled: true,
          guest_qa_daily_limit: 2,
          crowd_vote_min_unlock: 2,
          user_referral_enabled: false,
          invite_waitlist_enabled: false,
        }),
      },
      env,
    )
    expect(saveStage1.status).toBe(200)
    const pubSettingsRes = await app.request('https://mirrorinfo.xyz/api/public/settings', {}, env)
    expect(pubSettingsRes.status).toBe(200)
    expect(await pubSettingsRes.json()).toMatchObject({
      growth_stage: 'stage_1_cold_start',
      guest_qa_daily_limit: 2,
      crowd_vote_min_unlock: 2,
      user_referral_enabled: false,
    })

    // 2. Dynamic guest_qa_daily_limit = 2 -> 2 succeed with decreasing remaining_quota, 3rd returns 429 quota_exhausted
    for (const expectedRemaining of [1, 0]) {
      const qaOk = await app.request(
        'https://mirrorinfo.xyz/api/qa/ask',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'cf-connecting-ip': '203.0.113.10',
            'X-Device-ID': 'guest-qa-dev-1',
          },
          body: JSON.stringify({ question: '美联储最新利率与通胀判断是什么？', lang: 'zh' }),
        },
        env,
      )
      expect(qaOk.status).toBe(200)
      expect(await qaOk.json()).toMatchObject({
        remaining_quota: expectedRemaining,
        daily_limit: 2,
      })
    }

    const qaBlocked = await app.request(
      'https://mirrorinfo.xyz/api/qa/ask',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '203.0.113.10',
          'X-Device-ID': 'guest-qa-dev-1',
        },
        body: JSON.stringify({ question: '第三次追问超限测试', lang: 'zh' }),
      },
      env,
    )
    expect(qaBlocked.status).toBe(429)
    expect(await qaBlocked.json()).toMatchObject({
      quota_exhausted: true,
      remaining_quota: 0,
      daily_limit: 2,
    })

    // 3. Stage 2 Soft Invite + Dual Quota Bonus + No-code registration still open + dynamic crowd_vote_min_unlock=2
    const saveStage2 = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({
          growth_stage: 'stage_2_soft_invite',
          access_mode: 'public',
          crowd_vote_min_unlock: 2,
          user_referral_enabled: true,
          user_invite_quota: 1,
          referral_bonus_qa_quota: 15,
        }),
      },
      env,
    )
    expect(saveStage2.status).toBe(200)

    // Register User A without code (public mode allows optional)
    const regUserA = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '203.0.113.21',
          'X-Device-ID': 'ref-dev-a',
        },
        body: JSON.stringify({ username: 'alpha_user', password: 'Password123' }),
      },
      env,
    )
    expect(regUserA.status).toBe(200)
    const sessA = (await regUserA.json()) as { token: string; user: { id: number; member_number: number } }
    expect(sessA.user.member_number).toBe(sessA.user.id)

    // User A creates 1 referral invite code (quota=1); 2nd attempt hits quota error
    const mkInv1 = await app.request(
      'https://mirrorinfo.xyz/api/auth/my-invites',
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${sessA.token}` },
      },
      env,
    )
    expect(mkInv1.status).toBe(200)
    const inv1Body = (await mkInv1.json()) as { item: { code: string }; remaining_quota: number }
    expect(inv1Body.remaining_quota).toBe(0)
    const refCode = inv1Body.item.code

    const mkInv2 = await app.request(
      'https://mirrorinfo.xyz/api/auth/my-invites',
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${sessA.token}` },
      },
      env,
    )
    expect(mkInv2.status).toBe(400)

    // User B registers in Stage 2 WITH optional referral code -> BOTH A & B gain +15 extra_qa_quota
    const regUserB = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '203.0.113.22',
          'X-Device-ID': 'ref-dev-b',
        },
        body: JSON.stringify({ username: 'beta_user', password: 'Password123', invite_code: refCode }),
      },
      env,
    )
    expect(regUserB.status).toBe(200)
    const sessB = (await regUserB.json()) as {
      token: string
      referral_bonus_granted: number
      user: { extra_qa_quota: number; invited_by_code: string }
    }
    expect(sessB.referral_bonus_granted).toBe(15)
    expect(sessB.user.extra_qa_quota).toBe(15)
    expect(sessB.user.invited_by_code).toBe(refCode)

    const meA = await app.request(
      'https://mirrorinfo.xyz/api/auth/me',
      { headers: { Authorization: `Bearer ${sessA.token}` } },
      env,
    )
    const meABody = (await meA.json()) as { user: { extra_qa_quota: number } }
    expect(meABody.user.extra_qa_quota).toBe(15)

    // Test crowd consensus threshold = 2: 1st vote keeps locked, 2nd vote unlocks crowd_avg_pct
    const voteA = await app.request(
      'https://mirrorinfo.xyz/api/predictions/pred_test_1/vote',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessA.token}`,
        },
        body: JSON.stringify({ prob_pct: 70 }),
      },
      env,
    )
    expect(voteA.status).toBe(200)
    expect(((await voteA.json()) as { item: { unlocked: boolean; crowd_avg_pct: number | null } }).item).toMatchObject({
      unlocked: false,
      crowd_avg_pct: null,
    })

    const voteB = await app.request(
      'https://mirrorinfo.xyz/api/predictions/pred_test_1/vote',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessB.token}`,
        },
        body: JSON.stringify({ prob_pct: 80 }),
      },
      env,
    )
    expect(voteB.status).toBe(200)
    expect(((await voteB.json()) as { item: { unlocked: boolean; crowd_avg_pct: number } }).item).toMatchObject({
      unlocked: true,
      crowd_avg_pct: 75,
    })

    // 4. Stage 3 invite_only + waitlist submit -> admin approve -> applicant registers with assigned code
    const saveStage3 = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${superSess.token}`,
        },
        body: JSON.stringify({
          growth_stage: 'stage_3_scarcity_invite',
          access_mode: 'invite_only',
          invite_waitlist_enabled: true,
        }),
      },
      env,
    )
    expect(saveStage3.status).toBe(200)

    const submitWl = await app.request(
      'https://mirrorinfo.xyz/api/public/waitlist',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '203.0.113.30',
        },
        body: JSON.stringify({
          contact: 'gamma@mirrorinfo.xyz',
          focus_areas: ['宏观央行', 'AI前沿'],
          note: '关注利率与半导体传导',
        }),
      },
      env,
    )
    expect(submitWl.status).toBe(200)
    const wlBody = (await submitWl.json()) as { ok: boolean; id: number }

    const approveWl = await app.request(
      `https://mirrorinfo.xyz/api/admin/waitlist/${wlBody.id}/approve`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${superSess.token}` },
      },
      env,
    )
    expect(approveWl.status).toBe(200)
    const approvedData = (await approveWl.json()) as { code: string }
    expect(approvedData.code).toMatch(/^MB-/)

    const regFromWaitlist = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'cf-connecting-ip': '203.0.113.31',
          'X-Device-ID': 'ref-dev-gamma',
        },
        body: JSON.stringify({
          username: 'gamma_user',
          password: 'Password123',
          invite_code: approvedData.code,
        }),
      },
      env,
    )
    expect(regFromWaitlist.status).toBe(200)

    // 5. Reactions: guest dedup/switch, user dedup, invalid key -> 400
    const badReact = await app.request(
      'https://mirrorinfo.xyz/api/reactions',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'react-dev-1' },
        body: JSON.stringify({ target_type: 'event', target_id: 'ev_fomc_1', reaction_key: 'invalid_key' }),
      },
      env,
    )
    expect(badReact.status).toBe(400)

    const r1 = await app.request(
      'https://mirrorinfo.xyz/api/reactions',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'react-dev-1' },
        body: JSON.stringify({ target_type: 'event', target_id: 'ev_fomc_1', reaction_key: 'heavy' }),
      },
      env,
    )
    expect(r1.status).toBe(200)
    expect(((await r1.json()) as { item: { counts: Record<string, number>; my_reaction: string } }).item).toMatchObject({
      counts: { heavy: 1, track: 0, noise: 0 },
      my_reaction: 'heavy',
    })

    // Same guest switches from 'heavy' to 'track' -> heavy decrements to 0, track becomes 1
    const rSwitch = await app.request(
      'https://mirrorinfo.xyz/api/reactions',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Device-ID': 'react-dev-1' },
        body: JSON.stringify({ target_type: 'event', target_id: 'ev_fomc_1', reaction_key: 'track' }),
      },
      env,
    )
    expect(((await rSwitch.json()) as { item: { counts: Record<string, number>; total: number } }).item).toMatchObject({
      counts: { heavy: 0, track: 1, noise: 0 },
      total: 1,
    })

    // Authenticated user A votes 'heavy', then batch fetch sees both
    const rUserA = await app.request(
      'https://mirrorinfo.xyz/api/reactions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sessA.token}`,
        },
        body: JSON.stringify({ target_type: 'event', target_id: 'ev_fomc_1', reaction_key: 'heavy' }),
      },
      env,
    )
    expect(rUserA.status).toBe(200)

    const rBatch = await app.request(
      'https://mirrorinfo.xyz/api/reactions/batch?target_type=event&ids=ev_fomc_1',
      {
        headers: { Authorization: `Bearer ${sessA.token}` },
      },
      env,
    )
    expect(rBatch.status).toBe(200)
    expect(((await rBatch.json()) as { items: Record<string, { counts: Record<string, number>; total: number; my_reaction: string }> }).items.ev_fomc_1).toMatchObject({
      counts: { heavy: 1, track: 1, noise: 0 },
      total: 2,
      my_reaction: 'heavy',
    })
  })

  it('runs Prediction Arena lifecycle: daily market gen, 30-min lock, proposals, objective auto-settlement & stacked perks', async () => {
    const { env, r2 } = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    const app = createWorkerApp()
    await r2.put(
      'data/market_quotes.json',
      JSON.stringify({
        generated_at: new Date().toISOString(),
        quotes: {
          '000001.SH': { ticker: '000001.SH', name: '上证指数', price: 3350.0, pct_change: 0.6 },
          NVDA: { ticker: 'NVDA', name: '英伟达', price: 145.0, pct_change: 1.1 },
          XAUUSD: { ticker: 'XAUUSD', name: '伦敦金现', price: 2742.0, pct_change: 0.4 },
        },
      }),
    )

    // Bootstrap super_admin and sub_admin
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
    const superSess = (await adminLogin.json()) as { token: string }

    await app.request(
      'https://mirrorinfo.xyz/api/admin/users',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({ username: 'sub_ops', password: 'SubPassword123', role: 'admin' }),
      },
      env,
    )
    const subLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'sub_ops', password: 'SubPassword123' }),
      },
      env,
    )
    const subSess = (await subLogin.json()) as { token: string }

    // Hot toggle check: sub_admin gets 403, super_admin succeeds
    const subBlocked = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${subSess.token}` },
        body: JSON.stringify({ prediction_rewards_enabled: false }),
      },
      env,
    )
    expect(subBlocked.status).toBe(403)

    const superSettingsRes = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({
          access_mode: 'public',
          auth_qa_daily_limit: 1,
          user_referral_enabled: true,
          user_invite_quota: 2,
          prediction_daily_market_enabled: true,
          prediction_rewards_enabled: true,
          prediction_proposals_enabled: true,
        }),
      },
      env,
    )
    expect(superSettingsRes.status).toBe(200)

    // Register normal user alice
    const regAlice = await app.request(
      'https://mirrorinfo.xyz/api/auth/register',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'cf-connecting-ip': '198.51.100.31', 'X-Device-ID': 'arena-dev-a' },
        body: JSON.stringify({ username: 'alice_arena', password: 'AlicePassword123' }),
      },
      env,
    )
    expect(regAlice.status).toBe(200)
    const aliceSess = (await regAlice.json()) as { token: string }

    // Trigger daily cron twice -> idempotent 3 created on first run, 0 on second
    const cron1 = await app.request(
      'https://mirrorinfo.xyz/api/admin/predictions/run-daily-cron',
      { method: 'POST', headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(cron1.status).toBe(200)
    const cron1Json = (await cron1.json()) as { ok: boolean; generated: number }
    expect(cron1Json.generated).toBe(3)

    const cron2 = await app.request(
      'https://mirrorinfo.xyz/api/admin/predictions/run-daily-cron',
      { method: 'POST', headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(((await cron2.json()) as { generated: number }).generated).toBe(0)

    const arenaRes1 = await app.request('https://mirrorinfo.xyz/api/predictions/arena', {}, env)
    expect(arenaRes1.status).toBe(200)
    const arenaData1 = (await arenaRes1.json()) as {
      daily_predictions: Array<{ id: string; due_at: string; lock_at: string; source_type: string }>
      allowed_reason_tags: string[]
    }
    expect(arenaData1.daily_predictions).toHaveLength(3)
    expect(arenaData1.allowed_reason_tags).toContain('流动性驱动')

    const sseItem = arenaData1.daily_predictions.find((d) => d.id.endsWith('_sse'))!
    const nvdaItem = arenaData1.daily_predictions.find((d) => d.id.endsWith('_nvda'))!
    const goldItem = arenaData1.daily_predictions.find((d) => d.id.endsWith('_gold'))!
    expect(sseItem).toBeTruthy()
    expect(nvdaItem).toBeTruthy()
    expect(goldItem).toBeTruthy()

    // Test 30-min lock guard on nvdaItem temporarily, then restore nvdaItem to open for voting
    const origLock = nvdaItem.lock_at
    const pastLock = new Date(Date.now() - 5 * 60_000).toISOString()
    await env.DB.prepare('UPDATE daily_predictions SET lock_at = ?1 WHERE id = ?2').bind(pastLock, nvdaItem.id).run()

    const lockedVoteRes = await app.request(
      `https://mirrorinfo.xyz/api/predictions/${nvdaItem.id}/vote`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${aliceSess.token}` },
        body: JSON.stringify({ prob_pct: 75, reason_tag: '流动性驱动' }),
      },
      env,
    )
    expect(lockedVoteRes.status).toBe(400)
    expect(await lockedVoteRes.json()).toMatchObject({ locked: true })

    await env.DB.prepare('UPDATE daily_predictions SET lock_at = ?1 WHERE id = ?2').bind(origLock, nvdaItem.id).run()

    // Alice votes >= 55% with reason_tag on all 3 daily predictions
    for (const pid of [sseItem.id, nvdaItem.id, goldItem.id]) {
      const voteRes = await app.request(
        `https://mirrorinfo.xyz/api/predictions/${pid}/vote`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${aliceSess.token}` },
          body: JSON.stringify({ prob_pct: 80, reason_tag: '流动性驱动' }),
        },
        env,
      )
      expect(voteRes.status).toBe(200)
    }

    // Objective auto-settlement: move sseItem due_at to past and set higher 000001.SH in R2, then run cron
    const pastDue = new Date(Date.now() - 2 * 60_000).toISOString()
    await env.DB.prepare('UPDATE daily_predictions SET due_at = ?1, lock_at = ?2 WHERE id = ?3').bind(pastDue, pastDue, sseItem.id).run()
    await r2.put(
      'data/market_quotes.json',
      JSON.stringify({
        generated_at: new Date().toISOString(),
        quotes: {
          '000001.SH': { ticker: '000001.SH', name: '上证指数', price: 3388.5, pct_change: 1.15 },
          NVDA: { ticker: 'NVDA', name: '英伟达', price: 148.2, pct_change: 2.2 },
          XAUUSD: { ticker: 'XAUUSD', name: '伦敦金现', price: 2760.0, pct_change: 0.7 },
        },
      }),
    )
    const cronAutoSettle = await app.request(
      'https://mirrorinfo.xyz/api/admin/predictions/run-daily-cron',
      { method: 'POST', headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(((await cronAutoSettle.json()) as { settled: number }).settled).toBe(1)

    // Manually settle remaining 2 items as 'yes' to build a 3-hit streak
    for (const pid of [nvdaItem.id, goldItem.id]) {
      const sRes = await app.request(
        `https://mirrorinfo.xyz/api/admin/predictions/${pid}/settle`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
          body: JSON.stringify({ outcome: 'yes', settled_value: 999 }),
        },
        env,
      )
      expect(sRes.status).toBe(200)
    }

    // Alice submits a user prediction proposal & admin approves (+100 pts, +1 invite bonus)
    const propFutureDue = new Date(Date.now() + 72 * 3600_000).toISOString()
    const propCreate = await app.request(
      'https://mirrorinfo.xyz/api/predictions/proposals',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${aliceSess.token}` },
        body: JSON.stringify({
          category: 'macro',
          title: 'FOMC 纪要鹰派措辞预测',
          question: '下周公布的 FOMC 会议纪要是否提及暂缓降息路径？',
          win_rule: '美联储官网全文出现暂缓降息相关表态',
          lose_rule: '纪要仅重申按期降息路线',
          due_at: propFutureDue,
        }),
      },
      env,
    )
    expect(propCreate.status).toBe(200)
    const propJson = (await propCreate.json()) as { proposal: { id: number } }

    const propApprove = await app.request(
      `https://mirrorinfo.xyz/api/admin/predictions/proposals/${propJson.proposal.id}/approve`,
      { method: 'POST', headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    expect(propApprove.status).toBe(200)

    // Verify rewards profile, rank tier, bonus QA quota, and unlocked invite quota
    const arenaAfter = await app.request(
      'https://mirrorinfo.xyz/api/predictions/arena',
      { headers: { Authorization: `Bearer ${aliceSess.token}` } },
      env,
    )
    expect(arenaAfter.status).toBe(200)
    const arenaAfterData = (await arenaAfter.json()) as {
      my_profile: {
        settled_count: number
        hit_count: number
        current_streak: number
        insight_points: number
        rank_tier: string
        bonus_qa_quota: number
        unlocked_referral_bonus: number
      }
      leaderboard: Array<{ username: string; rank: number }>
    }
    expect(arenaAfterData.my_profile.settled_count).toBe(3)
    expect(arenaAfterData.my_profile.hit_count).toBe(3)
    expect(arenaAfterData.my_profile.current_streak).toBe(3)
    expect(arenaAfterData.my_profile.insight_points).toBeGreaterThanOrEqual(200)
    expect(arenaAfterData.my_profile.rank_tier).toBe('趋势捕手')
    expect(arenaAfterData.my_profile.bonus_qa_quota).toBe(10)
    expect(arenaAfterData.my_profile.unlocked_referral_bonus).toBe(3) // +2 streak +1 approved proposal
    expect(arenaAfterData.leaderboard[0]?.username).toBe('alice_arena')

    const meRes = await app.request(
      'https://mirrorinfo.xyz/api/auth/me',
      { headers: { Authorization: `Bearer ${aliceSess.token}` } },
      env,
    )
    expect(((await meRes.json()) as { prediction_bonus_qa_quota: number }).prediction_bonus_qa_quota).toBe(10)

    const invRes = await app.request(
      'https://mirrorinfo.xyz/api/auth/my-invites',
      { headers: { Authorization: `Bearer ${aliceSess.token}` } },
      env,
    )
    expect(((await invRes.json()) as { quota: number }).quota).toBe(5) // base 2 + unlocked 3

    // auth_qa_daily_limit was set to 1, but bonus_qa_quota=10 stacks -> 2nd QA call STILL succeeds!
    for (const qText of ['第一问验证配额', '第二问验证连胜加赠叠加上限']) {
      const qaRes = await app.request(
        'https://mirrorinfo.xyz/api/qa/ask',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${aliceSess.token}` },
          body: JSON.stringify({ question: qText, lang: 'zh' }),
        },
        env,
      )
      expect(qaRes.status).toBe(200)
    }

    // Disabling proposals blocks new proposal submission with 403
    await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({ prediction_proposals_enabled: false }),
      },
      env,
    )
    const propBlocked = await app.request(
      'https://mirrorinfo.xyz/api/predictions/proposals',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${aliceSess.token}` },
        body: JSON.stringify({
          category: 'macro',
          title: '关闭投稿拦截测试',
          question: '测试关闭开关是否实时拦截？',
          due_at: propFutureDue,
        }),
      },
      env,
    )
    expect(propBlocked.status).toBe(403)
  })

  it('serves dynamic OG HTML to crawlers and 302 deep-link redirects to browsers on /s/pred/* and /s/event/*', async () => {
    const { env, r2 } = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    const app = createWorkerApp()
    await r2.put(
      'data/market_quotes.json',
      JSON.stringify({
        generated_at: new Date().toISOString(),
        quotes: {
          '000001.SH': { ticker: '000001.SH', name: '上证指数', price: 3350.0, pct_change: 0.6 },
        },
      }),
    )
    await r2.put(
      'analysis_finance.json',
      JSON.stringify({
        events: [
          {
            event_id: 'ev_share_og_1',
            title: '央行宣布降准 25 个基点',
            fact_summary: '释放长期流动性约 5000 亿元。',
            sources: [{ source_name: '中国人民银行' }, { source_name: '新华社' }],
          },
        ],
      }),
    )
    await r2.put(
      'data/weekly_digests/2026-W48.json',
      JSON.stringify({
        week_id: '2026-W48',
        date_range_label: '11.23 - 11.29',
        week_theme: '大资金稳字当头，AI 开始拼真成本落地',
        executive_thesis: ['央行放水稳住年末资金。', 'AI 龙头估值进入实测检验期。'],
        stats: { selected_items: 24, p0_count: 6 },
      }),
    )

    const adminLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPass123!' }),
      },
      env,
    )
    const superSess = (await adminLogin.json()) as { token: string }
    await app.request(
      'https://mirrorinfo.xyz/api/admin/predictions/run-daily-cron',
      { method: 'POST', headers: { Authorization: `Bearer ${superSess.token}` } },
      env,
    )
    const arenaData = (await (
      await app.request('https://mirrorinfo.xyz/api/predictions/arena', {}, env)
    ).json()) as { daily_predictions: Array<{ id: string; title: string }> }
    const predId = arenaData.daily_predictions[0].id

    // Bot UA gets HTTP 200 HTML with dynamic og:title
    const predBot = await app.request(
      `https://mirrorinfo.xyz/s/pred/${encodeURIComponent(predId)}?p=78&ref=ALICE`,
      { headers: { 'User-Agent': 'TelegramBot (like TwitterBot)' } },
      env,
    )
    expect(predBot.status).toBe(200)
    const predHtml = await predBot.text()
    expect(predHtml).toContain('og:title')
    expect(predHtml).toContain('我押 78%')
    expect(predHtml).toContain('上证指数')

    // Regular browser gets 302 redirect preserving tab/pred/p/ref
    const predBrowser = await app.request(
      `https://mirrorinfo.xyz/s/pred/${encodeURIComponent(predId)}?p=78&ref=ALICE`,
      { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' } },
      env,
    )
    expect(predBrowser.status).toBe(302)
    const locPred = predBrowser.headers.get('location') || ''
    expect(locPred).toContain('tab=calendar')
    expect(locPred).toContain(`pred=${predId}`)
    expect(locPred).toContain('p=78')
    expect(locPred).toContain('ref=ALICE')

    // Event OG HTML & redirect
    const evBot = await app.request(
      'https://mirrorinfo.xyz/s/event/ev_share_og_1',
      { headers: { 'User-Agent': 'MicroMessenger/8.0' } },
      env,
    )
    expect(evBot.status).toBe(200)
    expect(await evBot.text()).toContain('央行宣布降准 25 个基点')

    const evBrowser = await app.request(
      'https://mirrorinfo.xyz/s/event/ev_share_og_1',
      { headers: { 'User-Agent': 'Mozilla/5.0' } },
      env,
    )
    expect(evBrowser.status).toBe(302)
    expect(evBrowser.headers.get('location')).toBe('https://mirrorinfo.xyz/?event=ev_share_og_1')

    // Weekly digest OG HTML & deep-link redirect
    const wkBot = await app.request(
      'https://mirrorinfo.xyz/s/weekly/2026-W48',
      { headers: { 'User-Agent': 'MicroMessenger/8.0' } },
      env,
    )
    expect(wkBot.status).toBe(200)
    const wkHtml = await wkBot.text()
    expect(wkHtml).toContain('2026-W48 一周大事：大资金稳字当头')
    expect(wkHtml).toContain('精选 24 件本周真大事')

    const wkBrowser = await app.request(
      'https://mirrorinfo.xyz/s/weekly/2026-W48',
      { headers: { 'User-Agent': 'Mozilla/5.0' } },
      env,
    )
    expect(wkBrowser.status).toBe(302)
    expect(wkBrowser.headers.get('location')).toBe('https://mirrorinfo.xyz/?tab=weekly&week=2026-W48')

    // Under private_gate, OG HTML must NOT expose internal titles
    await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({ access_mode: 'private_gate' }),
      },
      env,
    )
    const privateBot = await app.request(
      'https://mirrorinfo.xyz/s/event/ev_share_og_1?preview=1',
      {},
      env,
    )
    expect(privateBot.status).toBe(200)
    const privHtml = await privateBot.text()
    expect(privHtml).toContain('镜信 MirrorBrief')
    expect(privHtml).not.toContain('释放长期流动性')
  })

  it('exposes and persists dynamic weekly_digest schedule settings with super_admin RBAC protection', async () => {
    const { env } = createTestEnv({ SITE_ACCESS_MODE: 'public' })
    const app = createWorkerApp()

    const pubDefault = await app.request('https://mirrorinfo.xyz/api/public/settings', {}, env)
    expect(pubDefault.status).toBe(200)
    expect(await pubDefault.json()).toMatchObject({
      weekly_digest_enabled: true,
      weekly_digest_day: 0,
      weekly_digest_hour: 18,
      weekly_digest_minute: 0,
    })

    const superLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'admin', password: 'AdminPass123!' }),
      },
      env,
    )
    const superSess = (await superLogin.json()) as { token: string }

    await app.request(
      'https://mirrorinfo.xyz/api/admin/users',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({ username: 'weekly_sub_ops', password: 'SubPassword123', role: 'admin' }),
      },
      env,
    )
    const subLogin = await app.request(
      'https://mirrorinfo.xyz/api/auth/login',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'weekly_sub_ops', password: 'SubPassword123' }),
      },
      env,
    )
    const subSess = (await subLogin.json()) as { token: string }

    const subAttempt = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${subSess.token}` },
        body: JSON.stringify({ weekly_digest_hour: 21 }),
      },
      env,
    )
    expect(subAttempt.status).toBe(403)

    const superSave = await app.request(
      'https://mirrorinfo.xyz/api/admin/site-settings',
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${superSess.token}` },
        body: JSON.stringify({
          weekly_digest_enabled: false,
          weekly_digest_day: 5,
          weekly_digest_hour: 21,
          weekly_digest_minute: 30,
        }),
      },
      env,
    )
    expect(superSave.status).toBe(200)

    const pubUpdated = await app.request('https://mirrorinfo.xyz/api/public/settings', {}, env)
    expect(await pubUpdated.json()).toMatchObject({
      weekly_digest_enabled: false,
      weekly_digest_day: 5,
      weekly_digest_hour: 21,
      weekly_digest_minute: 30,
    })
  })
})
