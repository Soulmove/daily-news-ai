const SHELL_CACHE = 'mirrorbrief-shell-v1'
const DATA_CACHE = 'mirrorbrief-data-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache
        .addAll(['./icon.svg', './manifest.webmanifest'])
        .catch(() => {}),
    ),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== DATA_CACHE)
          .map((k) => caches.delete(k)),
      ),
    ),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return

  const pathname = url.pathname
  // Never intercept backend API requests or cross-origin R2 assets
  if (pathname.includes('/api/')) {
    return
  }

  // Always fetch HTML navigations & pages fresh online so hashed ./assets/*.js references never go stale
  if (req.mode === 'navigate' || pathname.endsWith('.html') || pathname.endsWith('/')) {
    event.respondWith(
      fetch(req, { cache: 'no-store' })
        .then((res) => {
          if (res.ok) {
            const clone = res.clone()
            caches.open(DATA_CACHE).then((cache) => cache.put(req, clone)).catch(() => {})
          }
          return res
        })
        .catch(() => caches.match(req)),
    )
    return
  }

  const isDynamicData =
    pathname.endsWith('.json') ||
    pathname.endsWith('.xml') ||
    pathname.endsWith('.ics')

  if (isDynamicData) {
    event.respondWith(
      fetch(req, { cache: 'no-cache' })
        .then((res) => {
          if (res.ok) {
            const clone = res.clone()
            caches.open(DATA_CACHE).then((cache) => cache.put(req, clone)).catch(() => {})
          }
          return res
        })
        .catch(() => caches.match(req)),
    )
    return
  }

  // Immutable hashed assets: cache-first ONLY for valid 200 responses
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached
      return fetch(req).then((res) => {
        if (res.ok && pathname.includes('/assets/')) {
          const clone = res.clone()
          caches.open(SHELL_CACHE).then((cache) => cache.put(req, clone)).catch(() => {})
        }
        return res
      })
    }),
  )
})
