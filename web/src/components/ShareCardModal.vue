<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Copy, Download, Share2, Sparkles, X } from 'lucide-vue-next'
import { t } from '../core/i18n'

export type ShareCardPayload =
  | {
      kind: 'prediction_pk'
      predictionId: string
      question: string
      userProbPct: number
      deadlineLabel: string
      voteCount: number
      minVotes: number
      crowdAvgPct: number | null
      shareUrl: string
    }
  | {
      kind: 'portfolio_radar'
      matchedCount: number
      bullishCount: number
      bearishCount: number
      neutralCount: number
      symbolsLabel: string
      takeaways: { title: string; polarity: 'positive' | 'negative' | 'neutral'; summary: string }[]
      shareUrl: string
    }
  | {
      kind: 'echo_chamber'
      diversityScore: number
      statusLabel: string
      totalReads: number
      distribution: { label: string; pct: number; color: string }[]
      recommendation: string
      shareUrl: string
    }

const props = defineProps<{
  isOpen: boolean
  payload: ShareCardPayload | null
}>()

const emit = defineEmits<{
  close: []
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const copied = ref(false)
const downloaded = ref(false)

const modalTitle = computed(() => {
  if (!props.payload) return t('生成分享海报', 'Share Card')
  if (props.payload.kind === 'prediction_pk') return t('前瞻预测对赌 PK 卡', 'Prediction PK Card')
  if (props.payload.kind === 'portfolio_radar') return t('今日持仓传导雷达卡（脱敏）', 'Portfolio Radar Card')
  return t('我的信息茧房盲区诊断卡', 'Echo-Chamber Diagnosis Card')
})

function drawRoundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function drawWrappedText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines = 4,
): number {
  const chars = Array.from(String(text || '').trim())
  if (chars.length === 0) return y
  let line = ''
  let curY = y
  let lineIdx = 0
  for (let i = 0; i < chars.length; i++) {
    const ch = chars[i]
    const testLine = line + ch
    if (ctx.measureText(testLine).width > maxWidth && line.length > 0) {
      if (lineIdx >= maxLines - 1) {
        const trimmed = line.slice(0, Math.max(1, line.length - 1)) + '…'
        ctx.fillText(trimmed, x, curY)
        return curY + lineHeight
      }
      ctx.fillText(line, x, curY)
      line = ch
      curY += lineHeight
      lineIdx += 1
    } else {
      line = testLine
    }
  }
  if (line) {
    ctx.fillText(line, x, curY)
    curY += lineHeight
  }
  return curY
}

function renderCard() {
  const canvas = canvasRef.value
  const data = props.payload
  if (!canvas || !data) return

  const W = 750
  const H = 980
  const dpr = 2
  canvas.width = W * dpr
  canvas.height = H * dpr
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)

  // Deep slate-ink premium financial editorial background
  const grad = ctx.createLinearGradient(0, 0, W, H)
  grad.addColorStop(0, '#0B1220')
  grad.addColorStop(0.55, '#111C33')
  grad.addColorStop(1, '#0B101B')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, W, H)

  // Subtle decorative glow
  const glow = ctx.createRadialGradient(620, 120, 20, 620, 120, 340)
  glow.addColorStop(0, 'rgba(0, 122, 255, 0.28)')
  glow.addColorStop(1, 'rgba(0, 122, 255, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, W, H)

  // Outer Glass Panel
  drawRoundRect(ctx, 36, 36, W - 72, H - 72, 28)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.04)'
  ctx.fill()
  ctx.lineWidth = 1.5
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)'
  ctx.stroke()

  // Brand Header
  ctx.fillStyle = '#60A5FA'
  ctx.font = 'bold 20px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('镜信 MIRRORBRIEF', 68, 90)

  ctx.fillStyle = 'rgba(255, 255, 255, 0.52)'
  ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  const todayStr = new Date().toISOString().slice(0, 10)
  ctx.fillText(todayStr, W - 155, 90)

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)'
  ctx.beginPath()
  ctx.moveTo(68, 114)
  ctx.lineTo(W - 68, 114)
  ctx.stroke()

  if (data.kind === 'prediction_pk') {
    ctx.fillStyle = '#F59E0B'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('前瞻预测对赌 PK', 68, 162)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 30px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const afterTitleY = drawWrappedText(ctx, data.question, 68, 212, W - 136, 44, 4)

    // Big probability showcase card
    const boxY = Math.max(360, afterTitleY + 24)
    drawRoundRect(ctx, 68, boxY, W - 136, 220, 22)
    ctx.fillStyle = 'rgba(0, 122, 255, 0.14)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(96, 165, 250, 0.45)'
    ctx.stroke()

    ctx.fillStyle = '#93C5FD'
    ctx.font = '18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('我的概率预判', 100, boxY + 52)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 84px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`${Math.round(data.userProbPct)}%`, 100, boxY + 148)

    ctx.fillStyle = 'rgba(255, 255, 255, 0.7)'
    ctx.font = '17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`结算时间：${data.deadlineLabel || '到期自动验证'}`, 100, boxY + 190)

    // Crowd Consensus Progress
    const progY = boxY + 256
    ctx.fillStyle = 'rgba(255, 255, 255, 0.78)'
    ctx.font = '18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const progLabel =
      data.voteCount >= data.minVotes && data.crowdAvgPct !== null
        ? `全站已收 ${data.voteCount} 份预判 · 群众共识均值 ${Math.round(data.crowdAvgPct)}%`
        : `全站已收 ${data.voteCount}/${data.minVotes} 份预判，再邀 ${Math.max(1, data.minVotes - data.voteCount)} 位好友投票解锁均值`
    drawWrappedText(ctx, progLabel, 68, progY, W - 136, 28, 2)

    drawRoundRect(ctx, 68, progY + 46, W - 136, 14, 7)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)'
    ctx.fill()
    const pct = Math.min(1, data.voteCount / Math.max(1, data.minVotes))
    drawRoundRect(ctx, 68, progY + 46, Math.max(24, (W - 136) * pct), 14, 7)
    ctx.fillStyle = '#3B82F6'
    ctx.fill()
  } else if (data.kind === 'portfolio_radar') {
    ctx.fillStyle = '#34D399'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('今日持仓宏观传导雷达（已脱敏）', 68, 162)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 28px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    drawWrappedText(ctx, data.symbolsLabel || 'A股 / 美股 / 宏观板块监控', 68, 208, W - 136, 38, 2)

    // 3 Stat boxes
    const statY = 290
    const colW = (W - 136 - 24) / 3
    const stats = [
      { label: '命中传导线', value: String(data.matchedCount), color: '#60A5FA' },
      { label: '利好催化', value: String(data.bullishCount), color: '#F87171' },
      { label: '承压防线', value: String(data.bearishCount), color: '#34D399' },
    ]
    stats.forEach((st, idx) => {
      const bx = 68 + idx * (colW + 12)
      drawRoundRect(ctx, bx, statY, colW, 112, 18)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.06)'
      ctx.fill()
      ctx.fillStyle = st.color
      ctx.font = 'bold 42px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(st.value, bx + 22, statY + 62)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.68)'
      ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(st.label, bx + 22, statY + 94)
    })

    // Top 3 takeaways
    let curY = 442
    ctx.fillStyle = 'rgba(255, 255, 255, 0.55)'
    ctx.font = '16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('今日核心传导结论（零资金/仓位暴露）', 68, curY)
    curY += 22

    data.takeaways.slice(0, 3).forEach((item, idx) => {
      drawRoundRect(ctx, 68, curY, W - 136, 110, 16)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
      ctx.fill()
      ctx.fillStyle = item.polarity === 'positive' ? '#FCA5A5' : item.polarity === 'negative' ? '#6EE7B7' : '#93C5FD'
      ctx.font = 'bold 17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      const tag = item.polarity === 'positive' ? '[偏多]' : item.polarity === 'negative' ? '[承压]' : '[中性]'
      drawWrappedText(ctx, `${idx + 1}. ${tag} ${item.title}`, 86, curY + 34, W - 172, 24, 1)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'
      ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, item.summary, 86, curY + 66, W - 172, 22, 2)
      curY += 124
    })
  } else {
    ctx.fillStyle = '#A78BFA'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('我的信息茧房盲区诊断报告', 68, 162)

    drawRoundRect(ctx, 68, 196, W - 136, 150, 20)
    ctx.fillStyle = 'rgba(139, 92, 246, 0.14)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(167, 139, 250, 0.35)'
    ctx.stroke()

    ctx.fillStyle = '#DDD6FE'
    ctx.font = '17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`阅读多样性指数（已读 ${data.totalReads} 篇核验事件）`, 96, 242)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 64px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`${data.diversityScore}`, 96, 316)
    ctx.fillStyle = '#C4B5FD'
    ctx.font = 'bold 22px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`/ 100 · ${data.statusLabel}`, 205, 312)

    // 4-domain bars
    let barY = 392
    data.distribution.slice(0, 4).forEach((d) => {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
      ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(d.label, 68, barY)
      ctx.fillText(`${Math.round(d.pct)}%`, W - 120, barY)
      drawRoundRect(ctx, 68, barY + 14, W - 136, 16, 8)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.1)'
      ctx.fill()
      drawRoundRect(ctx, 68, barY + 14, Math.max(12, ((W - 136) * Math.min(100, d.pct)) / 100), 16, 8)
      ctx.fillStyle = d.color
      ctx.fill()
      barY += 66
    })

    // Recommendation box
    drawRoundRect(ctx, 68, 672, W - 136, 128, 18)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
    ctx.fill()
    ctx.fillStyle = '#FCD34D'
    ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('破茧补盲建议', 92, 708)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)'
    ctx.font = '16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    drawWrappedText(ctx, data.recommendation, 92, 740, W - 184, 26, 2)
  }

  // Footer CTA
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)'
  ctx.beginPath()
  ctx.moveTo(68, 845)
  ctx.lineTo(W - 68, 845)
  ctx.stroke()

  ctx.fillStyle = '#FFFFFF'
  ctx.font = 'bold 20px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('上镜信 mirrorinfo.xyz · 3 分钟看透全球大事与持仓传导', 68, 888)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.56)'
  ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('75+ 一手信源交叉核验 · 免费 AI 证据问答 · 无水评零噪音', 68, 916)
}

watch(
  () => [props.isOpen, props.payload],
  async ([open]) => {
    copied.value = false
    downloaded.value = false
    if (!open || !props.payload) return
    await nextTick()
    renderCard()
  },
  { immediate: true, deep: true },
)

async function copyShareLink() {
  if (!props.payload?.shareUrl) return
  try {
    await navigator.clipboard.writeText(props.payload.shareUrl)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2200)
  } catch {
    // ignore clipboard errors
  }
}

function downloadPng() {
  const canvas = canvasRef.value
  if (!canvas || !props.payload) return
  const link = document.createElement('a')
  const stamp = new Date().toISOString().slice(0, 10)
  link.download = `mirrorbrief-${props.payload.kind}-${stamp}.png`
  link.href = canvas.toDataURL('image/png')
  link.click()
  downloaded.value = true
  setTimeout(() => {
    downloaded.value = false
  }, 2200)
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen && payload"
      class="fixed inset-0 z-[59] flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-xs"
      @click.self="emit('close')"
      @keydown.esc.prevent="emit('close')"
    >
      <div
        role="dialog"
        aria-modal="true"
        class="w-full max-w-md rounded-3xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] shadow-2xl p-4 sm:p-5 space-y-3.5 max-h-[92vh] flex flex-col"
      >
        <div class="flex items-center justify-between gap-2 shrink-0">
          <div class="flex items-center gap-2 min-w-0">
            <Share2 class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
            <h3 class="text-[15px] font-bold text-zinc-950 dark:text-white truncate">{{ modalTitle }}</h3>
          </div>
          <button
            type="button"
            @click="emit('close')"
            class="w-8 h-8 inline-flex items-center justify-center rounded-full text-zinc-400 hover:bg-black/[0.05] dark:hover:bg-white/[0.08]"
            :aria-label="t('关闭', 'Close')"
          >
            <X class="w-4 h-4" :stroke-width="1.5" />
          </button>
        </div>

        <div class="overflow-y-auto rounded-2xl bg-[#0B1220] p-2 flex items-center justify-center">
          <canvas ref="canvasRef" class="w-full max-w-[340px] h-auto rounded-xl shadow-lg" />
        </div>

        <div class="flex items-center gap-2 text-xs shrink-0">
          <button
            type="button"
            @click="downloadPng"
            class="ios-tap flex-1 inline-flex items-center justify-center gap-1.5 min-h-[40px] px-3.5 py-2 rounded-2xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold"
          >
            <Check v-if="downloaded" class="w-4 h-4" :stroke-width="1.75" />
            <Download v-else class="w-4 h-4" :stroke-width="1.75" />
            <span>{{ downloaded ? t('已保存 PNG', 'Saved PNG') : t('下载高清海报 PNG', 'Download PNG') }}</span>
          </button>
          <button
            type="button"
            @click="copyShareLink"
            class="ios-tap flex-1 inline-flex items-center justify-center gap-1.5 min-h-[40px] px-3.5 py-2 rounded-2xl bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-800 dark:text-zinc-100 font-semibold"
          >
            <Check v-if="copied" class="w-4 h-4 text-emerald-500" :stroke-width="1.75" />
            <Copy v-else class="w-4 h-4" :stroke-width="1.75" />
            <span>{{ copied ? t('已复制链接', 'Copied') : t('一键复制链接', 'Copy Link') }}</span>
          </button>
        </div>
        <p class="text-[11px] text-zinc-400 text-center flex items-center justify-center gap-1">
          <Sparkles class="w-3 h-3 text-[#007AFF]" :stroke-width="1.5" />
          <span>{{ t('纯前端本地高清绘制，零资金隐私泄露', 'Rendered locally in-browser with zero private portfolio numbers') }}</span>
        </p>
      </div>
    </div>
  </Teleport>
</template>
