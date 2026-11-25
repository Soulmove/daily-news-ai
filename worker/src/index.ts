import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { attachContextMiddleware } from './authMiddleware'
import { ensureBootstrapAdmin } from './db'
import { runPredictionArenaCron } from './predictionArena'
import { adminRoutes } from './routes/admin'
import { publicAndCoreRoutes } from './routes/appRoutes'
import { authRoutes } from './routes/auth'
import { shareMetaRoutes } from './shareMeta'
import type { Env, HonoVariables } from './types'
import { runWireCron } from './wireCron'

const PRIVATE_GATE_PUBLIC_ALLOWLIST = new Set([
  '/api/health',
  '/api/public/settings',
  '/api/public/access-config',
  '/api/public/waitlist',
  '/api/share/meta',
  '/api/auth/login',
  '/api/auth/register',
  '/api/auth/send-code',
  '/api/auth/reset-password',
])

export function createWorkerApp() {
  const app = new Hono<{ Bindings: Env; Variables: HonoVariables }>()

  app.use(
    '/api/*',
    cors({
      origin: (origin, c) => {
        if (!origin) return '*'
        const allowedRaw = String(c.env?.ALLOWED_ORIGINS || 'https://mirrorinfo.xyz,https://www.mirrorinfo.xyz')
        const allowedList = allowedRaw
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean)
        if (
          allowedList.includes(origin) ||
          origin.startsWith('http://localhost:') ||
          origin.startsWith('http://127.0.0.1:')
        ) {
          return origin
        }
        return allowedList[0] || 'https://mirrorinfo.xyz'
      },
      allowMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
      allowHeaders: ['Authorization', 'Content-Type', 'X-Device-ID'],
      maxAge: 86400,
    }),
  )

  app.use('/api/*', async (c, next) => {
    await ensureBootstrapAdmin(c.env)
    await next()
  })

  app.use('/api/*', attachContextMiddleware)

  // Global SITE_ACCESS_MODE gate for protected content & APIs
  app.use('/api/*', async (c, next) => {
    if (c.req.method === 'OPTIONS') {
      await next()
      return
    }
    const mode = c.get('accessMode')
    if (mode === 'private_gate' && !c.get('user')) {
      const path = new URL(c.req.url).pathname
      if (!PRIVATE_GATE_PUBLIC_ALLOWLIST.has(path)) {
        return c.json(
          {
            detail: '私有访问模式：请先登录账号后再读取站内数据',
            access_mode: 'private_gate',
            login_required: true,
          },
          401,
        )
      }
    }
    await next()
  })

  app.route('/s', shareMetaRoutes)
  app.route('/api/auth', authRoutes)
  app.route('/api/admin', adminRoutes)
  app.route('/api', publicAndCoreRoutes)

  app.notFound((c) => c.json({ detail: 'API route not found' }, 404))

  app.onError((err, c) => {
    console.error('Worker error:', err)
    return c.json({ detail: '服务内部异常，请稍后重试' }, 500)
  })

  return app
}

const app = createWorkerApp()

export default {
  fetch: app.fetch,
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(
      (async () => {
        await ensureBootstrapAdmin(env)
        try {
          await runWireCron(env)
        } catch (err) {
          console.error('runWireCron failed:', err)
        }
        try {
          await runPredictionArenaCron(env)
        } catch (err) {
          console.error('runPredictionArenaCron failed:', err)
        }
      })(),
    )
  },
}
