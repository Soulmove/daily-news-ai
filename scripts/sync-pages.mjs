import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(__dirname, '..')
const distDir = path.join(rootDir, 'dist')

if (!fs.existsSync(distDir)) {
  console.error('dist/ does not exist. Run vite build first.')
  process.exit(1)
}

// Sync built HTML pages + PWA files to repository root for GitHub Pages / Nginx publishing
const legacyAppHtml = path.join(rootDir, 'app.html')
if (fs.existsSync(legacyAppHtml)) {
  fs.rmSync(legacyAppHtml, { force: true })
}
for (const page of ['index.html', 'monitor.html', 'about.html', 'admin.html', 'android-dev.html', 'privacy.html', 'terms.html', 'help.html', '404.html', 'manifest.webmanifest', 'sw.js', 'robots.txt', 'icon.svg', 'icon-192.png', 'icon-512.png']) {
  const src = path.join(distDir, page)
  const dest = path.join(rootDir, page)
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest)
  }
}

// Replace root assets/ and thumbs/ cleanly without touching data/, archives/, history/, or root JSONs
for (const dirName of ['assets', 'thumbs']) {
  const distSub = path.join(distDir, dirName)
  const rootSub = path.join(rootDir, dirName)
  if (fs.existsSync(rootSub)) {
    fs.rmSync(rootSub, { recursive: true, force: true })
  }
  if (fs.existsSync(distSub)) {
    fs.cpSync(distSub, rootSub, { recursive: true })
  }
}

console.log('Synced dist/ HTML + assets/ to repository root for GitHub Pages deployment.')
