<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import QRCode from 'qrcode'
import { Check, Copy, Download, Maximize2, MessageSquareShare, Share2, Sparkles, X } from 'lucide-vue-next'
import { t } from '../core/i18n'
import { formatShanghaiDateOnly } from '../core/time'

export type ShareCardPayload =
  | {
      kind: 'prediction_pk'
      predictionId: string
      title?: string
      question: string
      userProbPct: number
      aiProbPct?: number
      winRule?: string
      deadlineLabel: string
      voteCount: number
      minVotes: number
      crowdAvgPct: number | null
      rankTier?: string | null
      hitRatePct?: number | null
      shareUrl: string
    }
  | {
      kind: 'portfolio_radar'
      matchedCount: number
      bullishCount: number
      bearishCount: number
      neutralCount: number
      isRedUp?: boolean
      sectors?: string[]
      tickers?: string[]
      symbolsLabel: string
      takeaways: {
        title: string
        polarity: 'positive' | 'negative' | 'neutral'
        summary: string
        tags?: string[]
      }[]
      shareUrl: string
    }
  | {
      kind: 'echo_chamber'
      diversityScore: number
      statusLabel: string
      personaLabel?: string
      totalReads: number
      distribution: { label: string; pct: number; color: string }[]
      blindspotLabel?: string
      blindspotPct?: number
      blindspotTeaserTitle?: string
      recommendation: string
      shareUrl: string
    }
  | {
      kind: 'event_brief'
      eventId: string
      title: string
      categoryLabel: string
      sourceName: string
      sourceCount: number
      officialPoints: string[]
      bullishPoints: string[]
      bearishPoints: string[]
      shareUrl: string
    }
  | {
      kind: 'weekly_digest'
      weekId: string
      dateRangeLabel: string
      weekTheme: string
      totalItems: number
      p0Count: number
      streakWeeks?: number
      readCount?: number
      nextWeekCallout?: string
      sectorHighlights: {
        sectorLabel: string
        accentHex: string
        headline: string
      }[]
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
const copiedImageState = ref<'idle' | 'copied' | 'fallback'>('idle')
const copiedCopywriting = ref(false)
const downloaded = ref(false)
const lightboxUrl = ref<string | null>(null)

const modalTitle = computed(() => {
  if (!props.payload) return t('生成分享海报', 'Share Poster')
  if (props.payload.kind === 'prediction_pk') return t('前瞻预测对赌 PK 海报', 'Prediction PK Poster')
  if (props.payload.kind === 'portfolio_radar') return t('今日持仓传导雷达卡（已脱敏）', 'Portfolio Radar Poster')
  if (props.payload.kind === 'event_brief') return t('重大事件三视角核验简报卡', 'Event Brief Poster')
  if (props.payload.kind === 'weekly_digest') return t('一周大事盘点周刊海报', 'Weekly Digest Poster')
  return t('信息茧房盲区诊断报告卡', 'Echo-Chamber Diagnosis Poster')
})

const scanHintLabel = computed(() => {
  if (!props.payload) return '扫码查看'
  if (props.payload.kind === 'prediction_pk') return '长按扫码接招 PK'
  if (props.payload.kind === 'portfolio_radar') return '扫码测你的持仓'
  if (props.payload.kind === 'event_brief') return '扫码看完整三视角'
  if (props.payload.kind === 'weekly_digest') return '扫码 3 分钟速览一周大事'
  return '扫码测你的信息茧房'
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
        let trimmed = line
        while (trimmed.length > 1 && ctx.measureText(`${trimmed}…`).width > maxWidth) {
          trimmed = trimmed.slice(0, -1)
        }
        ctx.fillText(`${trimmed}…`, x, curY)
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

function drawCanvasQrCode(
  ctx: CanvasRenderingContext2D,
  url: string,
  boxX: number,
  boxY: number,
  boxSize = 124,
) {
  drawRoundRect(ctx, boxX, boxY, boxSize, boxSize, 14)
  ctx.fillStyle = '#FFFFFF'
  ctx.fill()
  ctx.lineWidth = 1
  ctx.strokeStyle = 'rgba(255,255,255,0.4)'
  ctx.stroke()

  try {
    const qr = QRCode.create(url || 'https://mirrorinfo.xyz', {
      errorCorrectionLevel: 'M',
    })
    const count = qr.modules.size
    const quiet = 10
    const cell = (boxSize - quiet * 2) / count
    ctx.fillStyle = '#0B1220'
    for (let r = 0; r < count; r += 1) {
      for (let c = 0; c < count; c += 1) {
        if (qr.modules.get(r, c)) {
          ctx.fillRect(
            boxX + quiet + c * cell,
            boxY + quiet + r * cell,
            Math.ceil(cell + 0.35),
            Math.ceil(cell + 0.35),
          )
        }
      }
    }
  } catch {
    ctx.fillStyle = '#0B1220'
    ctx.font = 'bold 13px sans-serif'
    ctx.fillText('mirrorinfo.xyz', boxX + 14, boxY + boxSize / 2)
  }
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
  ctx.textAlign = 'left'

  const grad = ctx.createLinearGradient(0, 0, W, H)
  grad.addColorStop(0, '#09111F')
  grad.addColorStop(0.55, '#111D35')
  grad.addColorStop(1, '#0A0F1A')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, W, H)

  const glow = ctx.createRadialGradient(620, 120, 20, 620, 120, 340)
  glow.addColorStop(0, 'rgba(37, 99, 235, 0.28)')
  glow.addColorStop(1, 'rgba(37, 99, 235, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, W, H)

  drawRoundRect(ctx, 36, 36, W - 72, H - 72, 28)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.04)'
  ctx.fill()
  ctx.lineWidth = 1.5
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)'
  ctx.stroke()

  // Brand Header with strict Asia/Shanghai date
  ctx.fillStyle = '#60A5FA'
  ctx.font = 'bold 20px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('镜信 MIRRORBRIEF', 68, 88)

  const todayStr = formatShanghaiDateOnly(new Date().toISOString())
  ctx.fillStyle = 'rgba(255, 255, 255, 0.56)'
  ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.textAlign = 'right'
  ctx.fillText(`${todayStr} · 北京时间`, W - 68, 88)
  ctx.textAlign = 'left'

  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)'
  ctx.beginPath()
  ctx.moveTo(68, 112)
  ctx.lineTo(W - 68, 112)
  ctx.stroke()

  if (data.kind === 'prediction_pk') {
    ctx.fillStyle = '#F59E0B'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('前瞻预测对赌 PK', 68, 156)

    if (data.rankTier) {
      const tierText =
        data.hitRatePct !== null && data.hitRatePct !== undefined
          ? `${data.rankTier} · 胜率 ${data.hitRatePct}%`
          : data.rankTier
      ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      const tw = ctx.measureText(tierText).width + 24
      drawRoundRect(ctx, W - 68 - tw, 134, tw, 30, 15)
      ctx.fillStyle = 'rgba(245, 158, 11, 0.16)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.45)'
      ctx.stroke()
      ctx.fillStyle = '#FCD34D'
      ctx.fillText(tierText, W - 68 - tw + 12, 154)
    }

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 27px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const headline = data.title || data.question
    const afterTitleY = drawWrappedText(ctx, headline, 68, 200, W - 136, 39, 3)

    // Hero VS Confrontation Block: My Forecast VS MirrorBrief AI
    const boxY = Math.max(292, Math.min(338, afterTitleY + 12))
    const boxH = 248
    drawRoundRect(ctx, 68, boxY, W - 136, boxH, 22)
    ctx.fillStyle = 'rgba(0, 122, 255, 0.13)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(96, 165, 250, 0.42)'
    ctx.stroke()

    const myPct = Math.round(data.userProbPct)
    const aiPct = Math.round(data.aiProbPct ?? 50)
    const diff = myPct - aiPct
    const diffText = diff === 0 ? '判断一致' : `分歧 ${diff > 0 ? `+${diff}` : diff}%`

    ctx.fillStyle = '#93C5FD'
    ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('我的概率预判', 96, boxY + 40)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 74px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`${myPct}%`, 96, boxY + 122)

    // Center VS badge
    drawRoundRect(ctx, W / 2 - 44, boxY + 52, 88, 34, 17)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)'
    ctx.fill()
    ctx.fillStyle = '#F8FAFC'
    ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('VS', W / 2, boxY + 75)

    ctx.fillStyle = diff === 0 ? '#94A3B8' : Math.abs(diff) >= 15 ? '#FBBF24' : '#60A5FA'
    ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(diffText, W / 2, boxY + 114)

    ctx.textAlign = 'right'
    ctx.fillStyle = '#FCD34D'
    ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('镜信 AI 基准', W - 96, boxY + 40)

    ctx.fillStyle = '#FDE68A'
    ctx.font = 'bold 62px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`${aiPct}%`, W - 96, boxY + 120)
    ctx.textAlign = 'left'

    // Dual bar comparison
    const barW = W - 192
    const barY = boxY + 150
    drawRoundRect(ctx, 96, barY, barW, 12, 6)
    ctx.fillStyle = 'rgba(255,255,255,0.12)'
    ctx.fill()
    drawRoundRect(ctx, 96, barY, Math.max(16, (barW * myPct) / 100), 12, 6)
    ctx.fillStyle = '#3B82F6'
    ctx.fill()
    // AI marker tick
    const aiMarkX = 96 + (barW * aiPct) / 100
    ctx.fillStyle = '#F59E0B'
    ctx.fillRect(Math.min(96 + barW - 4, aiMarkX - 2), barY - 4, 4, 20)

    ctx.fillStyle = 'rgba(255, 255, 255, 0.78)'
    ctx.font = '16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`客观结算时间：${data.deadlineLabel || '到期自动验证'}`, 96, boxY + 212)

    // Win rule panel
    const ruleY = boxY + boxH + 16
    drawRoundRect(ctx, 68, ruleY, W - 136, 94, 16)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
    ctx.fill()
    ctx.fillStyle = '#6EE7B7'
    ctx.font = 'bold 15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('客观判定条件', 90, ruleY + 30)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.84)'
    ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    drawWrappedText(
      ctx,
      data.winRule || data.question || '到期依据公开官方一手公告或收盘价客观核验',
      90,
      ruleY + 56,
      W - 180,
      22,
      2,
    )

    // Crowd Progress Bar cleanly placed before footer
    const progY = ruleY + 114
    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)'
    ctx.font = '16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const progLabel =
      data.voteCount >= data.minVotes && data.crowdAvgPct !== null
        ? `全站已收 ${data.voteCount} 份预判 · 人类共识均值 ${Math.round(data.crowdAvgPct)}%`
        : `全站已收 ${data.voteCount}/${data.minVotes} 份预判 · 再邀 ${Math.max(1, data.minVotes - data.voteCount)} 位好友投票解锁群众均值`
    ctx.fillText(progLabel, 68, progY)

    drawRoundRect(ctx, 68, progY + 16, W - 136, 12, 6)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)'
    ctx.fill()
    const pct = Math.min(1, data.voteCount / Math.max(1, data.minVotes))
    drawRoundRect(ctx, 68, progY + 16, Math.max(24, (W - 136) * pct), 12, 6)
    ctx.fillStyle = '#3B82F6'
    ctx.fill()
  } else if (data.kind === 'portfolio_radar') {
    const posHex = data.isRedUp !== false ? '#F87171' : '#34D399'
    const negHex = data.isRedUp !== false ? '#34D399' : '#F87171'
    const posTint = data.isRedUp !== false ? '#FCA5A5' : '#6EE7B7'
    const negTint = data.isRedUp !== false ? '#6EE7B7' : '#FCA5A5'

    ctx.fillStyle = '#34D399'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('今日持仓宏观传导雷达（已脱敏 · 零资产暴露）', 68, 156)

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 25px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    drawWrappedText(ctx, data.symbolsLabel || 'A股 / 美股 / 宏观板块监控', 68, 198, W - 136, 34, 2)

    // Consistent 4 Stat Boxes
    const statY = 268
    const colW = (W - 136 - 36) / 4
    const totalMatched = data.bullishCount + data.bearishCount + data.neutralCount
    const stats = [
      { label: '命中总计', value: String(totalMatched), color: '#60A5FA' },
      { label: '利好催化', value: String(data.bullishCount), color: posHex },
      { label: '承压防线', value: String(data.bearishCount), color: negHex },
      { label: '分化中性', value: String(data.neutralCount), color: '#FBBF24' },
    ]
    stats.forEach((st, idx) => {
      const bx = 68 + idx * (colW + 12)
      drawRoundRect(ctx, bx, statY, colW, 102, 16)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.06)'
      ctx.fill()
      ctx.fillStyle = st.color
      ctx.font = 'bold 38px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(st.value, bx + 18, statY + 56)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.72)'
      ctx.font = '14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(st.label, bx + 18, statY + 86)
    })

    ctx.fillStyle = 'rgba(148, 163, 184, 0.88)'
    ctx.font = '13px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('（按所选持仓板块映射方向统计，与单条快讯全市场情绪标签可能存在视角差异）', 68, statY + 124)

    let curY = 418
    ctx.fillStyle = 'rgba(255, 255, 255, 0.58)'
    ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('今日核心传导结论（扫码对照自选股灵敏度）', 68, curY)
    curY += 16

    data.takeaways.slice(0, 3).forEach((item, idx) => {
      drawRoundRect(ctx, 68, curY, W - 136, 98, 16)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
      ctx.fill()
      ctx.fillStyle =
        item.polarity === 'positive' ? posTint : item.polarity === 'negative' ? negTint : '#93C5FD'
      ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      const tag = item.polarity === 'positive' ? '[利好]' : item.polarity === 'negative' ? '[承压]' : '[分化]'
      const tagNote = item.tags && item.tags.length > 0 ? ` · ${item.tags.slice(0, 2).join('/')}` : ''
      drawWrappedText(ctx, `${idx + 1}. ${tag} ${item.title}${tagNote}`, 86, curY + 28, W - 172, 22, 1)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'
      ctx.font = '14.5px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, item.summary, 86, curY + 54, W - 172, 21, 2)
      curY += 108
    })
  } else if (data.kind === 'echo_chamber') {
    ctx.fillStyle = '#A78BFA'
    ctx.font = 'bold 18px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText('我的信息茧房盲区诊断报告', 68, 156)

    if (data.personaLabel) {
      ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      const pw = ctx.measureText(data.personaLabel).width + 24
      drawRoundRect(ctx, W - 68 - pw, 134, pw, 30, 15)
      ctx.fillStyle = 'rgba(167, 139, 250, 0.18)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(167, 139, 250, 0.45)'
      ctx.stroke()
      ctx.fillStyle = '#DDD6FE'
      ctx.fillText(data.personaLabel, W - 68 - pw + 12, 154)
    }

    drawRoundRect(ctx, 68, 184, W - 136, 136, 20)
    ctx.fillStyle = 'rgba(139, 92, 246, 0.14)'
    ctx.fill()
    ctx.strokeStyle = 'rgba(167, 139, 250, 0.35)'
    ctx.stroke()

    ctx.fillStyle = '#DDD6FE'
    ctx.font = '16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`阅读多样性指数（近 7 日已读 ${data.totalReads} 篇核验事件）`, 94, 224)

    // Dynamic ctx.measureText avoids 100 overlapping "/ 100"
    const scoreText = `${Math.round(data.diversityScore)}`
    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 62px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(scoreText, 94, 294)
    const scoreWidth = ctx.measureText(scoreText).width
    ctx.fillStyle = '#C4B5FD'
    ctx.font = 'bold 21px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`/ 100 · ${data.statusLabel}`, 94 + scoreWidth + 14, 290)

    // 4-domain bars with strict right-aligned percentages
    let barY = 360
    data.distribution.slice(0, 4).forEach((d) => {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.92)'
      ctx.font = 'bold 17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(d.label, 68, barY)
      ctx.textAlign = 'right'
      ctx.fillText(`${Math.round(d.pct)}%`, W - 68, barY)
      ctx.textAlign = 'left'

      drawRoundRect(ctx, 68, barY + 12, W - 136, 14, 7)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.1)'
      ctx.fill()
      if (d.pct > 0) {
        drawRoundRect(ctx, 68, barY + 12, Math.max(12, ((W - 136) * Math.min(100, d.pct)) / 100), 14, 7)
        ctx.fillStyle = d.color
        ctx.fill()
      }
      barY += 56
    })

    // Dynamic blindspot recommendation + semi-masked S-tier teaser
    const recBoxY = 592
    drawRoundRect(ctx, 68, recBoxY, W - 136, 166, 18)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
    ctx.fill()
    ctx.fillStyle = '#FCD34D'
    ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const blindTitle = data.blindspotLabel
      ? `破茧补盲建议 · 当前盲区「${data.blindspotLabel}」(${data.blindspotPct ?? 0}%)`
      : '破茧补盲建议'
    ctx.fillText(blindTitle, 90, recBoxY + 32)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.86)'
    ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    drawWrappedText(ctx, data.recommendation, 90, recBoxY + 62, W - 180, 22, 2)

    if (data.blindspotTeaserTitle) {
      drawRoundRect(ctx, 90, recBoxY + 110, W - 180, 42, 10)
      ctx.fillStyle = 'rgba(139, 92, 246, 0.14)'
      ctx.fill()
      ctx.fillStyle = '#E9D5FF'
      ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, `今日盲区要闻：${data.blindspotTeaserTitle}`, 104, recBoxY + 136, W - 280, 20, 1)

      // Semi-masked suspense overlay on right tail
      const maskGrad = ctx.createLinearGradient(W - 240, 0, W - 96, 0)
      maskGrad.addColorStop(0, 'rgba(17, 29, 53, 0)')
      maskGrad.addColorStop(0.65, 'rgba(17, 29, 53, 0.92)')
      maskGrad.addColorStop(1, 'rgba(17, 29, 53, 0.98)')
      ctx.fillStyle = maskGrad
      ctx.fillRect(W - 240, recBoxY + 112, 146, 38)
      ctx.fillStyle = '#C4B5FD'
      ctx.font = 'bold 12px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.textAlign = 'right'
      ctx.fillText('扫码解锁', W - 102, recBoxY + 136)
      ctx.textAlign = 'left'
    }
  } else if (data.kind === 'weekly_digest') {
    ctx.fillStyle = '#FBBF24'
    ctx.font = 'bold 17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(`每周盘点 · ${data.weekId} (${data.dateRangeLabel})`, 68, 154)

    if (data.streakWeeks && data.streakWeeks > 0) {
      const badgeText = `连续追更 ${data.streakWeeks} 周 · 补课 ${data.readCount ?? 0}/${data.totalItems}`
      ctx.font = 'bold 13px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      const bw = ctx.measureText(badgeText).width + 22
      drawRoundRect(ctx, W - 68 - bw, 134, bw, 28, 14)
      ctx.fillStyle = 'rgba(245, 158, 11, 0.16)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(245, 158, 11, 0.45)'
      ctx.stroke()
      ctx.fillStyle = '#FDE68A'
      ctx.fillText(badgeText, W - 68 - bw + 11, 153)
    }

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 25px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const afterThemeY = drawWrappedText(ctx, data.weekTheme, 68, 198, W - 136, 34, 2)

    const barY = Math.max(250, afterThemeY + 8)
    drawRoundRect(ctx, 68, barY, W - 136, 40, 12)
    ctx.fillStyle = 'rgba(59, 130, 246, 0.14)'
    ctx.fill()
    ctx.fillStyle = '#93C5FD'
    ctx.font = 'bold 14.5px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(
      `本周精选 ${data.totalItems} 项大事（0 重复） · P0 战略要闻 ${data.p0Count} 条 · 四大板块严格分栏`,
      86,
      barY + 25,
    )

    let sy = barY + 52
    const itemsList = data.sectorHighlights.slice(0, 4)
    const availH = data.nextWeekCallout ? Math.max(270, 706 - sy) : Math.max(320, 762 - sy)
    const cardGap = 9
    const cardH = Math.floor((availH - cardGap * Math.max(0, itemsList.length - 1)) / Math.max(1, itemsList.length))

    for (const sec of itemsList) {
      drawRoundRect(ctx, 68, sy, W - 136, cardH, 14)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.05)'
      ctx.fill()
      ctx.fillStyle = sec.accentHex || '#60A5FA'
      ctx.fillRect(68, sy + 12, 4, Math.max(22, cardH - 24))

      ctx.fillStyle = sec.accentHex || '#60A5FA'
      ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(sec.sectorLabel, 86, sy + 26)

      ctx.fillStyle = 'rgba(255, 255, 255, 0.92)'
      ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, sec.headline, 86, sy + 50, W - 172, 21, cardH >= 96 ? 2 : 1)
      sy += cardH + cardGap
    }

    if (data.nextWeekCallout) {
      drawRoundRect(ctx, 68, 720, W - 136, 42, 12)
      ctx.fillStyle = 'rgba(16, 185, 129, 0.14)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.35)'
      ctx.stroke()
      ctx.fillStyle = '#6EE7B7'
      ctx.font = 'bold 14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, `下周先看：${data.nextWeekCallout}`, 86, 746, W - 172, 20, 1)
    }
  } else {
    // Poster 4: Single Heavy Event 3-Perspective Briefing Card
    ctx.fillStyle = '#38BDF8'
    ctx.font = 'bold 17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(
      `${data.categoryLabel} · ${data.sourceCount} 路一手信源交叉核验`,
      68,
      154,
    )

    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)'
    ctx.font = '14px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'right'
    ctx.fillText(data.sourceName || '官方信源', W - 68, 154)
    ctx.textAlign = 'left'

    ctx.fillStyle = '#FFFFFF'
    ctx.font = 'bold 26px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
    const afterHeadlineY = drawWrappedText(ctx, data.title, 68, 198, W - 136, 36, 3)

    const cards = [
      {
        title: '官方 / 一手定调',
        color: '#60A5FA',
        bg: 'rgba(59, 130, 246, 0.12)',
        body: data.officialPoints.slice(0, 2).join('；') || '依据一手官网通稿与法定披露交叉核验。',
      },
      {
        title: '顺风 / 乐观逻辑',
        color: '#34D399',
        bg: 'rgba(16, 185, 129, 0.12)',
        body: data.bullishPoints.slice(0, 2).join('；') || '关注景气兑现与业绩催化延续性。',
      },
      {
        title: '风险 / 看空质疑',
        color: '#FB7185',
        bg: 'rgba(244, 63, 94, 0.12)',
        body: data.bearishPoints.slice(0, 2).join('；') || '需持续追踪后续披露口径变化与证伪边界。',
      },
    ]

    let cy = Math.max(296, afterHeadlineY + 14)
    const availH = Math.max(330, 760 - cy)
    const cardGap = 12
    const cardH = Math.floor((availH - cardGap * 2) / 3)

    for (const c of cards) {
      drawRoundRect(ctx, 68, cy, W - 136, cardH, 16)
      ctx.fillStyle = c.bg
      ctx.fill()
      ctx.fillStyle = c.color
      ctx.font = 'bold 16px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText(c.title, 88, cy + 30)
      ctx.fillStyle = 'rgba(255, 255, 255, 0.88)'
      ctx.font = '15px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
      drawWrappedText(ctx, c.body, 88, cy + 58, W - 176, 22, cardH >= 130 ? 3 : 2)
      cy += cardH + cardGap
    }
  }

  // Footer CTA + Built-in High-Contrast Canvas QR Code
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)'
  ctx.beginPath()
  ctx.moveTo(68, 778)
  ctx.lineTo(W - 68, 778)
  ctx.stroke()

  ctx.fillStyle = '#FFFFFF'
  ctx.font = 'bold 21px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('镜信 mirrorinfo.xyz · 3 分钟看透全球大事', 68, 822)

  ctx.fillStyle = '#60A5FA'
  ctx.font = 'bold 17px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText(scanHintLabel.value, 68, 858)

  ctx.fillStyle = 'rgba(255, 255, 255, 0.56)'
  ctx.font = '14.5px "Inter", "PingFang SC", "Microsoft YaHei", sans-serif'
  ctx.fillText('75+ 一手信源交叉核验 · 免费 AI 证据问答 · 零水评噪音', 68, 892)

  drawCanvasQrCode(ctx, data.shareUrl, W - 68 - 124, 796, 124)
}

watch(
  () => [props.isOpen, props.payload],
  async ([open]) => {
    copiedImageState.value = 'idle'
    copiedCopywriting.value = false
    downloaded.value = false
    lightboxUrl.value = null
    if (!open || !props.payload) return
    await nextTick()
    renderCard()
  },
  { immediate: true, deep: true },
)

function buildGroupShareText(): string {
  const data = props.payload
  if (!data) return ''
  if (data.kind === 'prediction_pk') {
    const title = data.title || data.question
    const aiPct = Math.round(data.aiProbPct ?? 50)
    return `我给「${title}」押了 ${Math.round(data.userProbPct)}%（镜信 AI 基准 ${aiPct}%），来测测你的判断并和我 PK：\n${data.shareUrl}`
  }
  if (data.kind === 'portfolio_radar') {
    const total = data.bullishCount + data.bearishCount + data.neutralCount
    return `我用镜信扫了一遍今日宏观传导（已脱敏）：聚焦 ${data.symbolsLabel}，共命中 ${total} 条传导线，点这里换成你的自选股测一测：\n${data.shareUrl}`
  }
  if (data.kind === 'event_brief') {
    return `【镜信 ${data.sourceCount} 路信源核验简报】${data.title}\n查看官方定调 / 顺风逻辑 / 风险质疑三视角拆解：\n${data.shareUrl}`
  }
  if (data.kind === 'weekly_digest') {
    return `【镜信每周盘点 · ${data.weekId} (${data.dateRangeLabel})】本周总基调：${data.weekTheme}\n全周去重精选 ${data.totalItems} 项大事（P0 战略级 ${data.p0Count} 项），四大板块分栏，支持 3 分钟大概看与深度细看：\n${data.shareUrl}`
  }
  return `我的近 7 日跨领域阅读多样性得分 ${Math.round(data.diversityScore)}/100（${data.personaLabel || data.statusLabel}），扫码或点链接测测你的信息茧房：\n${data.shareUrl}`
}

async function copyGroupShareCopywriting() {
  const txt = buildGroupShareText()
  if (!txt) return
  try {
    await navigator.clipboard.writeText(txt)
    copiedCopywriting.value = true
    setTimeout(() => {
      copiedCopywriting.value = false
    }, 2400)
  } catch {
    // ignore clipboard errors
  }
}

function downloadPng() {
  const canvas = canvasRef.value
  if (!canvas || !props.payload) return
  const link = document.createElement('a')
  const stamp = formatShanghaiDateOnly(new Date().toISOString())
  link.download = `mirrorbrief-${props.payload.kind}-${stamp}.png`
  link.href = canvas.toDataURL('image/png')
  link.click()
  downloaded.value = true
  setTimeout(() => {
    downloaded.value = false
  }, 2400)
}

async function copyPosterImage() {
  const canvas = canvasRef.value
  if (!canvas || !props.payload) return
  try {
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (
      blob &&
      typeof ClipboardItem !== 'undefined' &&
      navigator.clipboard &&
      typeof navigator.clipboard.write === 'function'
    ) {
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      copiedImageState.value = 'copied'
      setTimeout(() => {
        copiedImageState.value = 'idle'
      }, 2400)
      return
    }
  } catch {
    // Fall back gracefully to PNG download below
  }
  downloadPng()
  copiedImageState.value = 'fallback'
  setTimeout(() => {
    copiedImageState.value = 'idle'
  }, 2600)
}

function openZoomLightbox() {
  const canvas = canvasRef.value
  if (!canvas) return
  lightboxUrl.value = canvas.toDataURL('image/png')
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen && payload"
      class="fixed inset-0 z-[59] flex items-center justify-center p-3 sm:p-5 bg-black/65 backdrop-blur-xs"
      @click.self="emit('close')"
      @keydown.esc.prevent="lightboxUrl ? (lightboxUrl = null) : emit('close')"
    >
      <div
        role="dialog"
        aria-modal="true"
        class="w-full max-w-xl rounded-3xl bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] shadow-2xl p-4 sm:p-5 space-y-3.5 max-h-[94vh] flex flex-col"
      >
        <div class="flex items-center justify-between gap-2 shrink-0">
          <div class="flex items-center gap-2 min-w-0">
            <Share2 class="w-4 h-4 text-[#007AFF] shrink-0" :stroke-width="1.75" />
            <h3 class="text-[15px] sm:text-base font-bold text-zinc-950 dark:text-white truncate">{{ modalTitle }}</h3>
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

        <div class="relative overflow-y-auto rounded-2xl bg-[#09111F] p-2.5 flex items-center justify-center">
          <canvas
            ref="canvasRef"
            @click="openZoomLightbox"
            class="w-full max-w-[440px] h-auto rounded-xl shadow-xl cursor-zoom-in"
            :title="t('点击放大预览高清海报', 'Click to zoom poster')"
          />
          <button
            type="button"
            @click="openZoomLightbox"
            class="absolute bottom-4 right-4 inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-black/65 hover:bg-black/80 text-white text-[11px] font-medium backdrop-blur-xs"
          >
            <Maximize2 class="w-3 h-3" />
            <span>{{ t('放大查看', 'Zoom') }}</span>
          </button>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs shrink-0">
          <button
            type="button"
            @click="copyPosterImage"
            class="ios-tap inline-flex items-center justify-center gap-1.5 min-h-[42px] px-3 py-2 rounded-2xl bg-[#007AFF] hover:bg-[#0066D6] text-white font-semibold"
            data-testid="copy-poster-image-btn"
          >
            <Check v-if="copiedImageState !== 'idle'" class="w-4 h-4 shrink-0" :stroke-width="1.75" />
            <Copy v-else class="w-4 h-4 shrink-0" :stroke-width="1.75" />
            <span class="truncate">
              {{
                copiedImageState === 'copied'
                  ? t('图片已复制', 'Copied Image')
                  : copiedImageState === 'fallback'
                    ? t('已自动保存图片', 'Saved Fallback')
                    : t('复制海报图片', 'Copy Image')
              }}
            </span>
          </button>

          <button
            type="button"
            @click="downloadPng"
            class="ios-tap inline-flex items-center justify-center gap-1.5 min-h-[42px] px-3 py-2 rounded-2xl bg-[#F2F2F7] dark:bg-[#2C2C2E] text-zinc-900 dark:text-zinc-100 font-semibold hover:bg-black/[0.08] dark:hover:bg-white/[0.12]"
            data-testid="download-poster-png-btn"
          >
            <Check v-if="downloaded" class="w-4 h-4 text-emerald-500 shrink-0" :stroke-width="1.75" />
            <Download v-else class="w-4 h-4 shrink-0" :stroke-width="1.75" />
            <span class="truncate">{{ downloaded ? t('已保存 PNG', 'Saved PNG') : t('下载高清 PNG', 'Download PNG') }}</span>
          </button>

          <button
            type="button"
            @click="copyGroupShareCopywriting"
            class="ios-tap inline-flex items-center justify-center gap-1.5 min-h-[42px] px-3 py-2 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
            data-testid="copy-group-text-btn"
          >
            <Check v-if="copiedCopywriting" class="w-4 h-4 shrink-0" :stroke-width="1.75" />
            <MessageSquareShare v-else class="w-4 h-4 shrink-0" :stroke-width="1.75" />
            <span class="truncate">{{ copiedCopywriting ? t('已复制群聊文案', 'Copied Post') : t('复制群聊文案', 'Copy Post Text') }}</span>
          </button>
        </div>

        <p class="text-[11px] text-zinc-400 text-center flex items-center justify-center gap-1">
          <Sparkles class="w-3 h-3 text-[#007AFF] shrink-0" :stroke-width="1.5" />
          <span>{{ t('海报内置实时可扫二维码（本地零隐私绘制），复制图片后可直接粘贴到微信群聊', 'Built-in scannable QR rendered locally with zero private amounts exposed') }}</span>
        </p>
      </div>
    </div>

    <!-- High-Res Lightbox Zoom Modal -->
    <div
      v-if="lightboxUrl"
      class="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-black/88 backdrop-blur-sm"
      @click.self="lightboxUrl = null"
    >
      <button
        type="button"
        @click="lightboxUrl = null"
        class="fixed top-4 right-4 w-10 h-10 rounded-full bg-white/15 hover:bg-white/25 text-white flex items-center justify-center"
        :aria-label="t('关闭放大预览', 'Close zoom')"
      >
        <X class="w-5 h-5" />
      </button>
      <img
        :src="lightboxUrl"
        alt="镜信分享海报高清大图"
        class="max-h-[92vh] max-w-[94vw] w-auto h-auto rounded-2xl shadow-2xl"
      />
    </div>
  </Teleport>
</template>
