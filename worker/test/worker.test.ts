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
  const schemaSql = `${readFileSync(schemaPath1, 'utf-8')}\n${readFileSync(schemaPath2, 'utf-8')}`
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
})
