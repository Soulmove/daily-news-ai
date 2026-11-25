/**
 * Native Web Crypto primitives strictly tuned for Cloudflare Workers Free Tier (<10ms CPU budget).
 * - Password hashing: PBKDF2-SHA256 (65,000 iterations by default, 16-byte random salt)
 * - Encrypted cloud storage: AES-256-GCM (12-byte random IV, SHA-256 derived 256-bit key)
 * - Session tokens: HMAC-SHA256 (HS256) JWT
 */

import type { AuthClaims } from './types'

const encoder = new TextEncoder()
const decoder = new TextDecoder()

export const DEFAULT_PBKDF2_ITERATIONS = 65_000
const MAX_PBKDF2_ITERATIONS = 100_000

const aesKeyCache = new Map<string, Promise<CryptoKey>>()
const hmacKeyCache = new Map<string, Promise<CryptoKey>>()

export function b64UrlEncode(bytes: Uint8Array): string {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize))
  }
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
}

export function b64UrlDecode(str: string): Uint8Array {
  const clean = str.replace(/-/g, '+').replace(/_/g, '/')
  const pad = clean.length % 4 === 0 ? '' : '='.repeat(4 - (clean.length % 4))
  const binary = atob(clean + pad)
  const out = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    out[i] = binary.charCodeAt(i)
  }
  return out
}

export function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) {
    diff |= a[i] ^ b[i]
  }
  return diff === 0
}

export async function sha256Bytes(input: string): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest('SHA-256', encoder.encode(input))
  return new Uint8Array(digest)
}

export async function sha256Hex(input: string): Promise<string> {
  const bytes = await sha256Bytes(input)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function getAesKey(secretKey: string): Promise<CryptoKey> {
  let cached = aesKeyCache.get(secretKey)
  if (!cached) {
    cached = (async () => {
      const keyMaterial = await sha256Bytes(secretKey || 'mirrorbrief-dev-fallback-key')
      return crypto.subtle.importKey('raw', keyMaterial, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt'])
    })()
    if (aesKeyCache.size > 16) aesKeyCache.clear()
    aesKeyCache.set(secretKey, cached)
  }
  return cached
}

function getHmacKey(secret: string): Promise<CryptoKey> {
  let cached = hmacKeyCache.get(secret)
  if (!cached) {
    cached = crypto.subtle.importKey(
      'raw',
      encoder.encode(secret || 'mirrorbrief-dev-jwt-secret'),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign', 'verify'],
    )
    if (hmacKeyCache.size > 16) hmacKeyCache.clear()
    hmacKeyCache.set(secret, cached)
  }
  return cached
}

export async function hashPassword(password: string, iterations = DEFAULT_PBKDF2_ITERATIONS): Promise<string> {
  const safeIters = Math.max(60_000, Math.min(MAX_PBKDF2_ITERATIONS, Math.floor(iterations)))
  const salt = new Uint8Array(16)
  crypto.getRandomValues(salt)
  const key = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits'])
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', hash: 'SHA-256', salt, iterations: safeIters },
    key,
    256,
  )
  const derived = new Uint8Array(bits)
  return `pbkdf2_sha256$${safeIters}$${b64UrlEncode(salt)}$${b64UrlEncode(derived)}`
}

export async function verifyPassword(password: string, storedHash: string): Promise<boolean> {
  if (!password || !storedHash) return false
  const parts = storedHash.split('$')
  if (parts.length !== 4 || parts[0] !== 'pbkdf2_sha256') {
    // Reject legacy pure-JS scrypt hashes immediately without burning Worker CPU
    return false
  }
  const iters = Number(parts[1])
  if (!Number.isFinite(iters) || iters < 10_000 || iters > MAX_PBKDF2_ITERATIONS) {
    return false
  }
  try {
    const salt = b64UrlDecode(parts[2])
    const expected = b64UrlDecode(parts[3])
    const key = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits'])
    const bits = await crypto.subtle.deriveBits(
      { name: 'PBKDF2', hash: 'SHA-256', salt, iterations: iters },
      key,
      expected.length * 8,
    )
    return constantTimeEqual(new Uint8Array(bits), expected)
  } catch {
    return false
  }
}

export async function encryptJson(obj: unknown, secretKey: string): Promise<string> {
  const key = await getAesKey(secretKey)
  const iv = new Uint8Array(12)
  crypto.getRandomValues(iv)
  const plain = encoder.encode(JSON.stringify(obj))
  const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plain)
  return `aes256gcm$${b64UrlEncode(iv)}$${b64UrlEncode(new Uint8Array(cipher))}`
}

export async function decryptJson<T>(token: string, secretKey: string, fallback: T): Promise<T> {
  if (!token) return fallback
  const parts = token.split('$')
  if (parts.length !== 3 || parts[0] !== 'aes256gcm') {
    return fallback
  }
  try {
    const key = await getAesKey(secretKey)
    const iv = b64UrlDecode(parts[1])
    const cipher = b64UrlDecode(parts[2])
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipher)
    return JSON.parse(decoder.decode(plain)) as T
  } catch {
    return fallback
  }
}

export async function signJwt(
  claims: Omit<AuthClaims, 'iat' | 'exp'>,
  secret: string,
  ttlSeconds = 14 * 86_400,
): Promise<string> {
  const nowSec = Math.floor(Date.now() / 1000)
  const fullClaims: AuthClaims = {
    ...claims,
    iat: nowSec,
    exp: nowSec + ttlSeconds,
  }
  const headerB64 = b64UrlEncode(encoder.encode(JSON.stringify({ alg: 'HS256', typ: 'JWT' })))
  const payloadB64 = b64UrlEncode(encoder.encode(JSON.stringify(fullClaims)))
  const signingInput = `${headerB64}.${payloadB64}`
  const hmacKey = await getHmacKey(secret)
  const sig = await crypto.subtle.sign('HMAC', hmacKey, encoder.encode(signingInput))
  return `${signingInput}.${b64UrlEncode(new Uint8Array(sig))}`
}

export async function verifyJwt(token: string, secret: string): Promise<AuthClaims | null> {
  if (!token) return null
  const parts = token.split('.')
  if (parts.length !== 3) return null
  const [headerB64, payloadB64, sigB64] = parts
  try {
    const hmacKey = await getHmacKey(secret)
    const sigBytes = b64UrlDecode(sigB64)
    const ok = await crypto.subtle.verify(
      'HMAC',
      hmacKey,
      sigBytes,
      encoder.encode(`${headerB64}.${payloadB64}`),
    )
    if (!ok) return null
    const claims = JSON.parse(decoder.decode(b64UrlDecode(payloadB64))) as AuthClaims
    if (!claims || typeof claims.sub !== 'number' || typeof claims.exp !== 'number') {
      return null
    }
    if (claims.exp < Math.floor(Date.now() / 1000)) {
      return null
    }
    return claims
  } catch {
    return null
  }
}

const INVITE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'

export function generateInviteCode(): string {
  const rnd = new Uint8Array(8)
  crypto.getRandomValues(rnd)
  let out = ''
  for (let i = 0; i < 8; i++) {
    if (i === 4) out += '-'
    out += INVITE_ALPHABET[rnd[i] % INVITE_ALPHABET.length]
  }
  return `MB-${out}`
}

export function generateOtpCode(): string {
  const buf = new Uint32Array(1)
  crypto.getRandomValues(buf)
  const num = 100_000 + (buf[0] % 900_000)
  return String(num)
}

export function nowShanghaiIso(offsetMs = 0): string {
  const d = new Date(Date.now() + offsetMs + 8 * 3600_000)
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mi = String(d.getUTCMinutes()).padStart(2, '0')
  const ss = String(d.getUTCSeconds()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}+08:00`
}
