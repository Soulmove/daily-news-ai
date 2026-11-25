<script setup lang="ts">
import { computed } from 'vue'
import { Camera } from 'lucide-vue-next'
import { resolveAvatarSpec } from '../core/avatars'

const props = withDefaults(
  defineProps<{
    avatar?: string | null
    username?: string | null
    role?: string | null
    size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
    editable?: boolean
    alt?: string
  }>(),
  {
    avatar: '',
    username: '',
    role: 'user',
    size: 'sm',
    editable: false,
    alt: '用户头像',
  },
)

// Module-level monotonic ID prevents SVG <defs> gradient ID collisions across all mounted avatars
let seq = 0
function nextUid(): string {
  seq = (seq + 1) % 1_000_000
  return `jxav_${seq}_${Math.floor(Math.random() * 1000)}`
}

const uid = nextUid()
const gradId = `${uid}_mesh`
const glowId = `${uid}_glow`
const goldId = `${uid}_gold`

const resolved = computed(() => resolveAvatarSpec(props.avatar, props.username, props.role))

const sizeClass = computed(() => {
  switch (props.size) {
    case 'xs':
      return 'w-5 h-5'
    case 'sm':
      return 'w-6 h-6'
    case 'md':
      return 'w-8 h-8'
    case 'lg':
      return 'w-14 h-14'
    case 'xl':
      return 'w-16 h-16'
  }
})

const ringClass = computed(() =>
  props.size === 'lg' || props.size === 'xl'
    ? 'ring-2 ring-white/80 dark:ring-white/15 shadow-[0_6px_18px_-4px_rgba(15,23,42,0.28)]'
    : 'ring-1 ring-black/10 dark:ring-white/20 shadow-[0_1px_3px_rgba(0,0,0,0.16)]',
)
</script>

<template>
  <span
    class="relative inline-flex shrink-0 items-center justify-center rounded-full select-none"
    :class="sizeClass"
    data-testid="user-avatar"
  >
    <!-- Uploaded Custom Cropped Image (<15KB WebP/JPEG DataURL) -->
    <span
      v-if="resolved.mode === 'image'"
      class="relative w-full h-full rounded-full overflow-hidden block bg-zinc-900"
      :class="ringClass"
    >
      <img
        :src="resolved.src"
        :alt="alt"
        class="w-full h-full object-cover block"
      />
      <span
        class="pointer-events-none absolute inset-[1px] rounded-full border border-white/35"
        aria-hidden="true"
      />
    </span>

    <!-- Bespoke Mesh-Gradient Geometric SVG Vector Avatar -->
    <svg
      v-else
      viewBox="0 0 64 64"
      class="w-full h-full rounded-full block"
      :class="ringClass"
      role="img"
      :aria-label="resolved.spec.nameZh"
    >
      <defs>
        <linearGradient :id="gradId" x1="8%" y1="6%" x2="92%" y2="94%">
          <stop offset="0%" :stop-color="resolved.spec.c1" />
          <stop offset="52%" :stop-color="resolved.spec.c2" />
          <stop offset="100%" :stop-color="resolved.spec.c3" />
        </linearGradient>
        <radialGradient :id="glowId" cx="28%" cy="22%" r="70%">
          <stop offset="0%" :stop-color="resolved.spec.glowColor" stop-opacity="0.58" />
          <stop offset="55%" :stop-color="resolved.spec.glowColor" stop-opacity="0.12" />
          <stop offset="100%" :stop-color="resolved.spec.glowColor" stop-opacity="0" />
        </radialGradient>
        <linearGradient :id="goldId" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#FEF08A" />
          <stop offset="50%" stop-color="#F59E0B" />
          <stop offset="100%" stop-color="#D97706" />
        </linearGradient>
      </defs>

      <!-- Multi-stop fluid mesh base -->
      <rect width="64" height="64" rx="32" :fill="`url(#${gradId})`" />
      <circle cx="20" cy="18" r="30" :fill="`url(#${glowId})`" />
      <circle cx="48" cy="48" r="20" :fill="resolved.spec.c3" opacity="0.22" />

      <!-- 1px Translucent Specular Inner Highlight Ring -->
      <circle
        cx="32"
        cy="32"
        r="30.4"
        fill="none"
        stroke="rgba(255,255,255,0.34)"
        stroke-width="1.15"
      />

      <!-- Geometric Vector Emblem by Kind -->
      <g
        fill="none"
        :stroke="resolved.spec.isGoldAccent ? `url(#${goldId})` : resolved.spec.strokeColor"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <!-- Admin Exclusive Obsidian-Gold Orbital Shield -->
        <template v-if="resolved.spec.kind === 'obsidian_shield'">
          <ellipse cx="32" cy="32" rx="22" ry="11" transform="rotate(-24 32 32)" stroke-width="1.6" stroke-opacity="0.6" />
          <path d="M32 14 L46 20 V33 C46 42 39.5 48.2 32 51 C24.5 48.2 18 42 18 33 V20 Z" stroke-width="2.2" fill="rgba(251,191,36,0.12)" />
          <path d="M32 21 L35.2 28.8 L43 32 L35.2 35.2 L32 43 L28.8 35.2 L21 32 L28.8 28.8 Z" stroke-width="1.7" fill="#FDE68A" fill-opacity="0.9" />
        </template>

        <!-- Star Compass -->
        <template v-else-if="resolved.spec.kind === 'star_compass'">
          <circle cx="32" cy="32" r="18" stroke-width="1.6" stroke-opacity="0.7" />
          <ellipse cx="32" cy="32" rx="22" ry="8.5" transform="rotate(32 32 32)" stroke-width="1.4" stroke-opacity="0.55" />
          <path d="M32 15 L36.5 27.5 L49 32 L36.5 36.5 L32 49 L27.5 36.5 L15 32 L27.5 27.5 Z" stroke-width="2" fill="rgba(255,255,255,0.22)" />
          <circle cx="32" cy="32" r="2.8" fill="#FFFFFF" stroke="none" />
        </template>

        <!-- Quant Bull / Ascending Chart Orbit -->
        <template v-else-if="resolved.spec.kind === 'quant_bull'">
          <circle cx="32" cy="32" r="20" stroke-width="1.3" stroke-opacity="0.45" />
          <path d="M18 41 L26 32 L33 36 L45 21" stroke-width="2.6" />
          <path d="M38 21 H45 V28" stroke-width="2.4" />
          <path d="M19 25 C22 18 28 17 32 21 C36 17 42 18 45 25" stroke-width="1.7" stroke-opacity="0.75" />
          <circle cx="26" cy="32" r="2" fill="#FEF3C7" stroke="none" />
          <circle cx="33" cy="36" r="2" fill="#FEF3C7" stroke="none" />
        </template>

        <!-- Compute Wafer -->
        <template v-else-if="resolved.spec.kind === 'compute_wafer'">
          <rect x="20" y="20" width="24" height="24" rx="5" stroke-width="2.2" fill="rgba(255,255,255,0.12)" />
          <rect x="26" y="26" width="12" height="12" rx="2.5" stroke-width="1.8" />
          <path d="M26 14 V20 M38 14 V20 M26 44 V50 M38 44 V50 M14 26 H20 M14 38 H20 M44 26 H50 M44 38 H50" stroke-width="2" />
        </template>

        <!-- Deep Radar -->
        <template v-else-if="resolved.spec.kind === 'deep_radar'">
          <circle cx="32" cy="32" r="19" stroke-width="1.7" stroke-opacity="0.75" />
          <circle cx="32" cy="32" r="12" stroke-width="1.5" stroke-opacity="0.65" />
          <circle cx="32" cy="32" r="5" stroke-width="1.5" />
          <path d="M32 32 L45 19" stroke-width="2.2" />
          <circle cx="42" cy="22" r="2.6" fill="#FFFFFF" stroke="none" />
        </template>

        <!-- Macro Scale -->
        <template v-else-if="resolved.spec.kind === 'macro_scale'">
          <path d="M32 16 V47 M22 47 H42" stroke-width="2.2" />
          <path d="M17 24 H47" stroke-width="2" />
          <path d="M17 24 L13 35 H21 Z M47 24 L43 35 H51 Z" stroke-width="1.7" fill="rgba(255,255,255,0.16)" />
        </template>

        <!-- Geek Terminal -->
        <template v-else-if="resolved.spec.kind === 'geek_terminal'">
          <rect x="14" y="18" width="36" height="28" rx="6" stroke-width="2" fill="rgba(255,255,255,0.08)" />
          <path d="M22 27 L28 32 L22 37" stroke-width="2.4" />
          <path d="M32 37 H41" stroke-width="2.4" />
        </template>

        <!-- Cyber Owl -->
        <template v-else-if="resolved.spec.kind === 'cyber_owl'">
          <path d="M19 22 L25 26 H39 L45 22 L47 36 C47 43 40.5 48 32 48 C23.5 48 17 43 17 36 Z" stroke-width="2" fill="rgba(255,255,255,0.1)" />
          <circle cx="25.5" cy="33" r="4" stroke-width="2" />
          <circle cx="38.5" cy="33" r="4" stroke-width="2" />
          <path d="M32 36 L29.5 40 H34.5 Z" stroke-width="1.6" />
        </template>

        <!-- Alpha Hunter -->
        <template v-else-if="resolved.spec.kind === 'alpha_hunter'">
          <circle cx="32" cy="32" r="17" stroke-width="1.6" stroke-opacity="0.7" />
          <path d="M32 11 V19 M32 45 V53 M11 32 H19 M45 32 H53" stroke-width="2" />
          <path d="M32 23 L38.5 39 H25.5 Z" stroke-width="2" fill="rgba(255,255,255,0.18)" />
        </template>

        <!-- Pulse Bolt -->
        <template v-else-if="resolved.spec.kind === 'pulse_bolt'">
          <circle cx="32" cy="32" r="20" stroke-width="1.5" stroke-opacity="0.5" />
          <path d="M35 15 L21 34 H31 L29 49 L43 30 H33 Z" stroke-width="2.1" fill="rgba(255,255,255,0.22)" />
        </template>

        <!-- Quantum Cube -->
        <template v-else-if="resolved.spec.kind === 'quantum_cube'">
          <path d="M32 15 L47 23.5 V40.5 L32 49 L17 40.5 V23.5 Z" stroke-width="2.1" fill="rgba(255,255,255,0.1)" />
          <path d="M17 23.5 L32 32 L47 23.5 M32 32 V49" stroke-width="1.9" />
          <circle cx="32" cy="32" r="2.6" fill="#FFFFFF" stroke="none" />
        </template>

        <!-- Global Meridian -->
        <template v-else-if="resolved.spec.kind === 'global_meridian'">
          <circle cx="32" cy="32" r="18" stroke-width="2" />
          <ellipse cx="32" cy="32" rx="9" ry="18" stroke-width="1.6" />
          <path d="M14 32 H50 M17 23 H47 M17 41 H47" stroke-width="1.4" stroke-opacity="0.8" />
        </template>

        <!-- Obsidian Crown -->
        <template v-else-if="resolved.spec.kind === 'obsidian_crown'">
          <ellipse cx="32" cy="33" rx="22" ry="12" transform="rotate(-15 32 33)" stroke-width="1.4" stroke-opacity="0.5" />
          <path d="M17 41 L20 23 L27.5 31 L32 19 L36.5 31 L44 23 L47 41 Z" stroke-width="2.2" fill="rgba(251,191,36,0.2)" />
          <path d="M20 45 H44" stroke-width="2.2" />
        </template>

        <!-- Guest Orbit Silhouette -->
        <template v-else>
          <circle cx="32" cy="24" r="7.5" stroke-width="2" fill="rgba(255,255,255,0.14)" />
          <path d="M18 46 C19.5 38 25 35 32 35 C39 35 44.5 38 46 46" stroke-width="2" />
          <ellipse cx="32" cy="32" rx="22" ry="9" transform="rotate(-20 32 32)" stroke-width="1.2" stroke-opacity="0.4" />
        </template>
      </g>
    </svg>

    <!-- Camera / Edit Badge when interactive -->
    <span
      v-if="editable"
      class="absolute -bottom-0.5 -right-0.5 w-5 h-5 rounded-full bg-white dark:bg-zinc-900 border border-black/15 dark:border-white/25 text-zinc-800 dark:text-zinc-100 shadow-md inline-flex items-center justify-center"
      aria-hidden="true"
    >
      <Camera class="w-3 h-3" :stroke-width="2" />
    </span>
  </span>
</template>
