import type { Context, Next } from 'hono'
import { verifyJwt } from './crypto'
import { getUserById } from './db'
import type { AccessMode, Env, HonoVariables, UserRow } from './types'

export function resolveAccessMode(raw?: string): AccessMode {
  const clean = (raw || '').trim().toLowerCase()
  if (clean === 'private_gate' || clean === 'invite_only' || clean === 'public') {
    return clean
  }
  return 'invite_only'
}

export function getClientIp(c: Context<{ Bindings: Env; Variables: HonoVariables }>): string {
  const cfIp = c.req.header('cf-connecting-ip')
  if (cfIp) return cfIp.trim().slice(0, 64)
  const fwd = c.req.header('x-forwarded-for') || c.req.header('x-real-ip')
  if (fwd) return fwd.split(',')[0].trim().slice(0, 64)
  return 'unknown'
}

export async function resolveDeviceFingerprint(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
): Promise<string> {
  const raw = (c.req.header('x-device-id') || '').trim()
  if (raw.length >= 8 && raw.length <= 128 && /^[A-Za-z0-9_.:-]+$/.test(raw)) {
    return `dev:${raw}`
  }
  const ip = getClientIp(c)
  const ua = (c.req.header('user-agent') || '').slice(0, 180)
  const lang = (c.req.header('accept-language') || '').slice(0, 40)
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${ip}|${ua}|${lang}`))
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
  return `fp:${hex.slice(0, 32)}`
}

export async function resolveOptionalUser(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
): Promise<UserRow | null> {
  const authHeader = c.req.header('authorization') || ''
  if (!authHeader.toLowerCase().startsWith('bearer ')) return null
  const token = authHeader.slice(7).trim()
  if (!token) return null
  const claims = await verifyJwt(token, c.env.JWT_SECRET)
  if (!claims) return null
  const user = await getUserById(c.env.DB, Number(claims.sub))
  if (!user || !user.is_active || Number(user.token_version) !== Number(claims.ver)) {
    return null
  }
  return user
}

export async function attachContextMiddleware(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
  next: Next,
): Promise<Response | void> {
  const ip = getClientIp(c)
  const deviceId = await resolveDeviceFingerprint(c)
  const accessMode = resolveAccessMode(c.env.SITE_ACCESS_MODE)
  const user = await resolveOptionalUser(c)
  c.set('clientIp', ip)
  c.set('deviceId', deviceId)
  c.set('accessMode', accessMode)
  c.set('user', user)
  await next()
}

export async function requireUser(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
  next: Next,
): Promise<Response | void> {
  const user = c.get('user')
  if (!user) {
    return c.json({ detail: '请先登录账号' }, 401)
  }
  await next()
}

export async function requireAdmin(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
  next: Next,
): Promise<Response | void> {
  const user = c.get('user')
  if (!user) {
    return c.json({ detail: '请先登录账号' }, 401)
  }
  if (user.role !== 'admin' && user.role !== 'super_admin') {
    return c.json({ detail: '权限不足：仅管理员可访问此接口' }, 403)
  }
  await next()
}

export async function requireSuperAdmin(
  c: Context<{ Bindings: Env; Variables: HonoVariables }>,
  next: Next,
): Promise<Response | void> {
  const user = c.get('user')
  if (!user) {
    return c.json({ detail: '请先登录账号' }, 401)
  }
  if (user.role !== 'super_admin') {
    return c.json({ detail: '权限不足：仅一级最高管理员可执行此操作' }, 403)
  }
  await next()
}
