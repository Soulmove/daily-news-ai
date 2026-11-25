import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'

function serveRepoDataPlugin(): Plugin {
  const repoRoot = path.resolve(__dirname)
  const allowedTopDirs = new Set(['data', 'archives', 'history'])
  const allowedRootJson = /^(data|analysis|comments)_(finance|global|tech|general)\.json$/

  return {
    name: 'serve-repo-data',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const rawUrl = (req.url || '/').split('?')[0]
        const rel = rawUrl.replace(/^\/+/, '')
        const firstSeg = rel.split('/')[0]

        if (!allowedTopDirs.has(firstSeg) && !allowedRootJson.test(rel)) {
          return next()
        }

        const filePath = path.resolve(repoRoot, rel)
        if (!filePath.startsWith(repoRoot) || !fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
          return next()
        }

        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        fs.createReadStream(filePath).pipe(res)
      })
    },
  }
}

export default defineConfig({
  root: 'web',
  base: './',
  plugins: [vue(), serveRepoDataPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'web/src'),
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: path.resolve(__dirname, 'web/index.html'),
        monitor: path.resolve(__dirname, 'web/monitor.html'),
        about: path.resolve(__dirname, 'web/about.html'),
        admin: path.resolve(__dirname, 'web/admin.html'),
        androidDev: path.resolve(__dirname, 'web/android-dev.html'),
        privacy: path.resolve(__dirname, 'web/privacy.html'),
        terms: path.resolve(__dirname, 'web/terms.html'),
        help: path.resolve(__dirname, 'web/help.html'),
        notFound: path.resolve(__dirname, 'web/404.html'),
      },
    },
  },
  test: {
    root: '.',
    include: ['tests/frontend/**/*.test.ts'],
  },
})
