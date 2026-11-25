/**
 * MirrorBrief (镜信) High-Craft Vector Avatar System + 12 Presets + Local Canvas Crop/Compress (<15KB).
 */

export interface AvatarVectorSpec {
  id: string
  nameZh: string
  nameEn: string
  c1: string
  c2: string
  c3: string
  glowColor: string
  strokeColor: string
  isGoldAccent?: boolean
  kind:
    | 'obsidian_shield'
    | 'star_compass'
    | 'quant_bull'
    | 'compute_wafer'
    | 'deep_radar'
    | 'macro_scale'
    | 'geek_terminal'
    | 'cyber_owl'
    | 'alpha_hunter'
    | 'pulse_bolt'
    | 'quantum_cube'
    | 'global_meridian'
    | 'obsidian_crown'
    | 'guest_orbit'
}

export const AVATAR_PRESETS: AvatarVectorSpec[] = [
  {
    id: 'preset:star_compass',
    nameZh: '星轨罗盘',
    nameEn: 'Star Compass',
    c1: '#0F172A',
    c2: '#1D4ED8',
    c3: '#06B6D4',
    glowColor: '#38BDF8',
    strokeColor: '#FFFFFF',
    kind: 'star_compass',
  },
  {
    id: 'preset:quant_bull',
    nameZh: '量化金牛',
    nameEn: 'Quant Bull',
    c1: '#18181B',
    c2: '#B45309',
    c3: '#F59E0B',
    glowColor: '#FBBF24',
    strokeColor: '#FEF3C7',
    isGoldAccent: true,
    kind: 'quant_bull',
  },
  {
    id: 'preset:compute_wafer',
    nameZh: '算力晶圆',
    nameEn: 'Compute Wafer',
    c1: '#0F172A',
    c2: '#4F46E5',
    c3: '#A855F7',
    glowColor: '#C084FC',
    strokeColor: '#F5F3FF',
    kind: 'compute_wafer',
  },
  {
    id: 'preset:deep_radar',
    nameZh: '深海雷达',
    nameEn: 'Deep Radar',
    c1: '#042F2E',
    c2: '#0D9488',
    c3: '#10B981',
    glowColor: '#34D399',
    strokeColor: '#ECFDF5',
    kind: 'deep_radar',
  },
  {
    id: 'preset:macro_scale',
    nameZh: '宏观天平',
    nameEn: 'Macro Scale',
    c1: '#1E1B4B',
    c2: '#2563EB',
    c3: '#EC4899',
    glowColor: '#F472B6',
    strokeColor: '#FFFFFF',
    kind: 'macro_scale',
  },
  {
    id: 'preset:geek_terminal',
    nameZh: '极客终端',
    nameEn: 'Geek Terminal',
    c1: '#09090B',
    c2: '#059669',
    c3: '#22D3EE',
    glowColor: '#6EE7B7',
    strokeColor: '#FFFFFF',
    kind: 'geek_terminal',
  },
  {
    id: 'preset:cyber_owl',
    nameZh: '赛博猫头鹰',
    nameEn: 'Cyber Owl',
    c1: '#1E1B4B',
    c2: '#7C3AED',
    c3: '#F43F5E',
    glowColor: '#FB7185',
    strokeColor: '#FFF1F2',
    kind: 'cyber_owl',
  },
  {
    id: 'preset:alpha_hunter',
    nameZh: '阿尔法猎手',
    nameEn: 'Alpha Hunter',
    c1: '#450A0A',
    c2: '#DC2626',
    c3: '#F97316',
    glowColor: '#FDBA74',
    strokeColor: '#FFFFFF',
    kind: 'alpha_hunter',
  },
  {
    id: 'preset:pulse_bolt',
    nameZh: '闪电脉冲',
    nameEn: 'Pulse Bolt',
    c1: '#0C4A6E',
    c2: '#0284C7',
    c3: '#38BDF8',
    glowColor: '#7DD3FC',
    strokeColor: '#FFFFFF',
    kind: 'pulse_bolt',
  },
  {
    id: 'preset:quantum_cube',
    nameZh: '量子魔方',
    nameEn: 'Quantum Cube',
    c1: '#311042',
    c2: '#9333EA',
    c3: '#3B82F6',
    glowColor: '#93C5FD',
    strokeColor: '#FFFFFF',
    kind: 'quantum_cube',
  },
  {
    id: 'preset:global_meridian',
    nameZh: '全球经纬',
    nameEn: 'Global Meridian',
    c1: '#064E3B',
    c2: '#0284C7',
    c3: '#6366F1',
    glowColor: '#67E8F9',
    strokeColor: '#FFFFFF',
    kind: 'global_meridian',
  },
  {
    id: 'preset:obsidian_crown',
    nameZh: '曜石王冠',
    nameEn: 'Obsidian Crown',
    c1: '#09090B',
    c2: '#27272A',
    c3: '#78350F',
    glowColor: '#FBBF24',
    strokeColor: '#FDE68A',
    isGoldAccent: true,
    kind: 'obsidian_crown',
  },
]

export const ADMIN_DEFAULT_AVATAR_SPEC: AvatarVectorSpec = {
  id: 'default:obsidian_shield',
  nameZh: '曜石黑金·星轨护盾',
  nameEn: 'Obsidian Gold Star Shield',
  c1: '#09090B',
  c2: '#1C1917',
  c3: '#78350F',
  glowColor: '#F59E0B',
  strokeColor: '#FCD34D',
  isGoldAccent: true,
  kind: 'obsidian_shield',
}

export const GUEST_DEFAULT_AVATAR_SPEC: AvatarVectorSpec = {
  id: 'default:guest_orbit',
  nameZh: '镜信访客星轨',
  nameEn: 'Guest Orbit',
  c1: '#1E293B',
  c2: '#334155',
  c3: '#475569',
  glowColor: '#94A3B8',
  strokeColor: '#F1F5F9',
  kind: 'guest_orbit',
}

const REGULAR_USER_DEFAULT_SPECS: AvatarVectorSpec[] = [
  AVATAR_PRESETS[0], // star_compass
  AVATAR_PRESETS[2], // compute_wafer
  AVATAR_PRESETS[3], // deep_radar
  AVATAR_PRESETS[4], // macro_scale
  AVATAR_PRESETS[8], // pulse_bolt
  AVATAR_PRESETS[10], // global_meridian
]

const PRESET_MAP: Record<string, AvatarVectorSpec> = Object.fromEntries(
  AVATAR_PRESETS.map((p) => [p.id, p]),
)

export function hashUsernameIndex(username: string, modulo: number): number {
  let h = 2166136261
  const clean = username.trim().toLowerCase()
  for (let i = 0; i < clean.length; i++) {
    h ^= clean.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) % Math.max(1, modulo)
}

export function resolveDefaultAvatarSpec(
  username?: string | null,
  role?: string | null,
): AvatarVectorSpec {
  const uname = (username || '').trim().toLowerCase()
  if (role === 'super_admin' || role === 'admin' || uname === 'admin') {
    return ADMIN_DEFAULT_AVATAR_SPEC
  }
  if (!uname) {
    return GUEST_DEFAULT_AVATAR_SPEC
  }
  const idx = hashUsernameIndex(uname, REGULAR_USER_DEFAULT_SPECS.length)
  return REGULAR_USER_DEFAULT_SPECS[idx]
}

export function resolveAvatarSpec(
  avatarValue?: string | null,
  username?: string | null,
  role?: string | null,
): { mode: 'image'; src: string } | { mode: 'vector'; spec: AvatarVectorSpec } {
  const val = (avatarValue || '').trim()
  if (val.startsWith('data:image/') && isValidAvatarValue(val)) {
    return { mode: 'image', src: val }
  }
  if (val && PRESET_MAP[val]) {
    return { mode: 'vector', spec: PRESET_MAP[val] }
  }
  return { mode: 'vector', spec: resolveDefaultAvatarSpec(username, role) }
}

const VALID_PRESET_RE = /^preset:[a-z0-9_-]{1,32}$/
const VALID_DATA_URL_RE = /^data:image\/(?:webp|jpeg|png);base64,[A-Za-z0-9+/=]+$/

export function isValidAvatarValue(raw: unknown): raw is string {
  if (typeof raw !== 'string') return false
  const val = raw.trim()
  if (!val) return true
  if (VALID_PRESET_RE.test(val)) return Boolean(PRESET_MAP[val])
  return val.length <= 28_000 && VALID_DATA_URL_RE.test(val)
}

export function estimateDataUrlBytes(dataUrl: string): number {
  const commaIdx = dataUrl.indexOf(',')
  if (commaIdx === -1) return 0
  const b64 = dataUrl.slice(commaIdx + 1)
  const pad = b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0
  return Math.max(0, Math.floor((b64.length * 3) / 4) - pad)
}

export async function compressAvatarFileToDataUrl(
  file: File,
  maxBytes = 15 * 1024,
): Promise<{
  dataUrl: string
  byteSize: number
  format: 'webp' | 'jpeg'
  width: number
  height: number
}> {
  if (!file || !file.type.startsWith('image/')) {
    throw new Error('请选择 PNG、JPEG 或 WebP 格式的图片')
  }
  const img = await loadImageFromFile(file)
  const naturalW = img.naturalWidth || img.width || 160
  const naturalH = img.naturalHeight || img.height || 160
  const side = Math.max(1, Math.min(naturalW, naturalH))
  const sx = Math.max(0, Math.floor((naturalW - side) / 2))
  const sy = Math.max(0, Math.floor((naturalH - side) / 2))

  const sizes = [160, 128]
  const mimes: Array<{ mime: 'image/webp' | 'image/jpeg'; format: 'webp' | 'jpeg'; qualities: number[] }> = [
    { mime: 'image/webp', format: 'webp', qualities: [0.82, 0.72, 0.62, 0.5, 0.38] },
    { mime: 'image/jpeg', format: 'jpeg', qualities: [0.82, 0.7, 0.56, 0.42] },
  ]

  let bestFallback: {
    dataUrl: string
    byteSize: number
    format: 'webp' | 'jpeg'
    width: number
    height: number
  } | null = null

  for (const targetSize of sizes) {
    const canvas = document.createElement('canvas')
    canvas.width = targetSize
    canvas.height = targetSize
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      throw new Error('浏览器不支持画布裁剪')
    }
    ctx.imageSmoothingEnabled = true
    ctx.imageSmoothingQuality = 'high'
    ctx.clearRect(0, 0, targetSize, targetSize)
    ctx.drawImage(img, sx, sy, side, side, 0, 0, targetSize, targetSize)

    for (const cfg of mimes) {
      for (const q of cfg.qualities) {
        const dataUrl = canvas.toDataURL(cfg.mime, q)
        if (!dataUrl.startsWith(`data:${cfg.mime}`)) continue
        const byteSize = estimateDataUrlBytes(dataUrl)
        const candidate = {
          dataUrl,
          byteSize,
          format: cfg.format,
          width: targetSize,
          height: targetSize,
        }
        if (!bestFallback || byteSize < bestFallback.byteSize) {
          bestFallback = candidate
        }
        if (byteSize <= maxBytes && byteSize >= 400) {
          return candidate
        }
      }
    }
  }

  if (bestFallback && bestFallback.byteSize <= 20 * 1024) {
    return bestFallback
  }
  throw new Error('图片体积过大，请选择更简单的图片或截图后重试')
}

function loadImageFromFile(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('无法读取该图片文件'))
      img.src = String(reader.result || '')
    }
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })
}
