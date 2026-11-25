<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDownUp, Archive, Building2, ChevronDown, ChevronUp, Clock, ExternalLink, FileText, MapPin, Sparkles } from 'lucide-vue-next'
import { formatShanghaiDateTime, parseTimestampMs } from '../../core/time'
import { pickBiText, t, translateSourceName, truncateAtSentence } from '../../core/i18n'
import { normalizeExternalUrl } from '../../core/legacyAdapter'
import { centerPillIntoView } from '../../core/dom'
import type { MajorTopicSpotlight, TopicLifecycleStatus } from '../../core/types'

const props = defineProps<{
  topics: MajorTopicSpotlight[]
  archivedTopics?: MajorTopicSpotlight[]
  initialTopicId?: string | null
  nowMs?: number
}>()

const emit = defineEmits<{
  (e: 'open-qa-topic', topic: MajorTopicSpotlight): void
  (e: 'jump-event-id', eventId: string, fallbackUrl?: string | null): void
}>()

const topicScope = ref<'active' | 'archive'>('active')
const regionFilter = ref<string>('all')
const orgFilter = ref<string>('all')
const timelineOrder = ref<'desc' | 'asc'>('desc')
const activeTopicId = ref<string>('')
const expandedAllNodes = ref(false)
const overviewExpanded = ref(false)
const mobileTopicsExpanded = ref(false)

const REGION_LABEL_MAP: Record<string, string> = {
  china: '中国',
  us: '美国',
  europe_ru_ua: '欧洲·俄乌',
  middle_east: '中东',
  apac: '亚太',
  global: '全球',
}

const baseScopeList = computed<MajorTopicSpotlight[]>(() =>
  topicScope.value === 'archive' ? props.archivedTopics || [] : props.topics || [],
)

const regionOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const tp of baseScopeList.value) {
    const rk = tp.region || 'global'
    counts.set(rk, (counts.get(rk) || 0) + 1)
  }
  const order = ['china', 'us', 'europe_ru_ua', 'middle_east', 'apac', 'global']
  return [
    { id: 'all', label: t('全部地区', 'All Regions'), count: baseScopeList.value.length },
    ...order
      .filter((k) => (counts.get(k) || 0) > 0)
      .map((k) => ({ id: k, label: REGION_LABEL_MAP[k] || k, count: counts.get(k) || 0 })),
  ]
})

const orgOptions = computed(() => {
  const counts = new Map<string, number>()
  const pool =
    regionFilter.value === 'all'
      ? baseScopeList.value
      : baseScopeList.value.filter((tp) => (tp.region || 'global') === regionFilter.value)
  for (const tp of pool) {
    for (const org of tp.primary_orgs || []) {
      counts.set(org, (counts.get(org) || 0) + 1)
    }
    if ((!tp.primary_orgs || tp.primary_orgs.length === 0) && tp.domain_tag) {
      counts.set(tp.domain_tag, (counts.get(tp.domain_tag) || 0) + 1)
    }
  }
  const top = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, cnt]) => ({ id: name, label: name, count: cnt }))
  return [{ id: 'all', label: t('全部主体/领域', 'All Entities & Domains'), count: pool.length }, ...top]
})

const currentTopicList = computed<MajorTopicSpotlight[]>(() => {
  return baseScopeList.value.filter((tp) => {
    if (regionFilter.value !== 'all' && (tp.region || 'global') !== regionFilter.value) return false
    if (orgFilter.value !== 'all') {
      const hitOrg = (tp.primary_orgs || []).includes(orgFilter.value) || tp.domain_tag === orgFilter.value
      if (!hitOrg) return false
    }
    return true
  })
})

watch(
  () => [props.topics.length, props.archivedTopics?.length ?? 0],
  () => {
    if (topicScope.value === 'active' && props.topics.length === 0 && (props.archivedTopics?.length || 0) > 0) {
      topicScope.value = 'archive'
    }
  },
  { immediate: true },
)

watch(
  () => props.initialTopicId,
  (tid) => {
    if (!tid) return
    if (props.topics.some((tp) => tp.topic_id === tid)) {
      topicScope.value = 'active'
      activeTopicId.value = tid
      expandedAllNodes.value = false
    } else if ((props.archivedTopics || []).some((tp) => tp.topic_id === tid)) {
      topicScope.value = 'archive'
      activeTopicId.value = tid
      expandedAllNodes.value = false
    }
  },
  { immediate: true },
)

function formatTopicSpan(tp: MajorTopicSpotlight): string {
  const s = tp.started_at ? formatShanghaiDateTime(tp.started_at, false) : ''
  const eIso = tp.ended_at || tp.updated_at
  const e = eIso ? formatShanghaiDateTime(eIso, false) : ''
  if (s && e && s !== e) return `${s} ~ ${e}`
  return e || s
}

function showSourceRepeatInSubtitle(sub?: string | null): boolean {
  return Boolean(sub && /(?:家信源|条.*脉络)/.test(sub))
}

const activeTopic = computed<MajorTopicSpotlight | null>(() => {
  const list = currentTopicList.value
  if (!list.length) return null
  return list.find((tp) => tp.topic_id === activeTopicId.value) ?? list[0]
})

const sortedNodes = computed(() => {
  if (!activeTopic.value) return []
  const tl = [...(activeTopic.value.timeline || [])]
  tl.sort((a, b) => {
    const ma = parseTimestampMs(a.time) ?? 0
    const mb = parseTimestampMs(b.time) ?? 0
    return timelineOrder.value === 'desc' ? mb - ma : ma - mb
  })
  return tl
})

const visibleNodes = computed(() => {
  const list = sortedNodes.value
  if (expandedAllNodes.value || list.length <= 6) return list
  return list.slice(0, 6)
})

function selectTopic(id: string) {
  activeTopicId.value = id
  expandedAllNodes.value = false
  overviewExpanded.value = false
}

function switchScope(scope: 'active' | 'archive') {
  topicScope.value = scope
  regionFilter.value = 'all'
  orgFilter.value = 'all'
  activeTopicId.value = ''
  expandedAllNodes.value = false
  overviewExpanded.value = false
  mobileTopicsExpanded.value = false
}

function lifecycleLabel(tp: MajorTopicSpotlight): string {
  if (tp.lifecycle_label) return tp.lifecycle_label
  switch (tp.lifecycle_status) {
    case 'starting':
      return t('刚开始', 'Starting')
    case 'ending_soon':
      return t('即将完结', 'Winding Down')
    case 'ended':
      return t('已完结', 'Ended')
    default:
      return t('进行中', 'Ongoing')
  }
}

function getTopicDeltaBadge(tp: MajorTopicSpotlight): { label: string; hot: boolean } | null {
  if (tp.lifecycle_status === 'ended' || tp.archived) return null
  const nowVal = props.nowMs ?? Date.now()
  let recent6h = typeof tp.recent_6h_count === 'number' ? tp.recent_6h_count : -1
  let todayCnt = typeof tp.today_count === 'number' ? tp.today_count : -1
  if (recent6h < 0 || todayCnt < 0) {
    recent6h = 0
    todayCnt = 0
    for (const nd of tp.timeline || []) {
      const ms = parseTimestampMs(nd.time)
      if (ms === null) continue
      const ageH = (nowVal - ms) / 3_600_000
      if (ageH >= -1 && ageH <= 6) recent6h += 1
      if (ageH >= -1 && ageH <= 24) todayCnt += 1
    }
  }
  if (recent6h > 0) return { label: t(`近6h +${recent6h}`, `6h +${recent6h}`), hot: true }
  if (todayCnt > 0) return { label: t(`今日 +${todayCnt}`, `Today +${todayCnt}`), hot: false }
  return null
}

function lifecycleBadgeClass(status?: TopicLifecycleStatus): string {
  switch (status) {
    case 'starting':
      return 'bg-emerald-500/12 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
    case 'ending_soon':
      return 'bg-amber-500/12 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
    case 'ended':
      return 'bg-zinc-500/12 text-zinc-600 dark:bg-zinc-400/15 dark:text-zinc-300'
    default:
      return 'bg-[#007AFF]/12 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]'
  }
}

function formatNodeClock(iso: string | null | undefined): string {
  const ms = parseTimestampMs(iso)
  if (ms === null) return t('时间待核', 'Recent')
  return formatShanghaiDateTime(iso, false)
}

function stageBadgeClass(tag: string): string {
  switch (tag) {
    case '抵访接待':
    case '阶段收束':
      return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200'
    case '高层会谈':
    case '高层互动':
      return 'bg-[#007AFF]/10 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF]'
    case '经贸与声明':
      return 'bg-emerald-500/10 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300'
    case '重大里程碑':
      return 'bg-amber-500/10 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300'
    default:
      return 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300'
  }
}
</script>

<template>
  <section
    v-if="topics.length > 0 || (archivedTopics && archivedTopics.length > 0)"
    class="ios-card p-3.5 sm:p-5 space-y-3"
    :aria-label="t('全网算法焦点专题与历史专题库', 'Auto-Clustered Topics & Historical Archive')"
  >
    <!-- Top Bar: Active vs Historical Topic Archive Switch + Q&A -->
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="ios-segmented">
        <button
          type="button"
          @click="switchScope('active')"
          class="ios-segmented-btn px-3 min-h-[32px] gap-1"
          :class="topicScope === 'active' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
        >
          <span>{{ t('活跃专题', 'Active Topics') }}</span>
          <span class="tabular-nums text-[11px] opacity-75">{{ topics.length }}</span>
        </button>
        <button
          type="button"
          @click="switchScope('archive')"
          class="ios-segmented-btn px-3 min-h-[32px] gap-1"
          :class="topicScope === 'archive' ? 'ios-segmented-btn-active' : 'text-zinc-600 dark:text-zinc-400'"
        >
          <Archive class="w-3.5 h-3.5 shrink-0" :stroke-width="1.5" />
          <span>{{ t('历史专题库', 'Topic Archive') }}</span>
          <span class="tabular-nums text-[11px] opacity-75">{{ archivedTopics?.length || 0 }}</span>
        </button>
      </div>

      <button
        v-if="activeTopic"
        type="button"
        @click="emit('open-qa-topic', activeTopic)"
        class="ios-tap inline-flex items-center gap-1 px-3 min-h-[32px] rounded-xl bg-[#007AFF]/10 text-[#007AFF] dark:bg-[#0A84FF]/15 dark:text-[#0A84FF] text-xs font-semibold hover:bg-[#007AFF]/15 shrink-0"
      >
        <Sparkles class="w-3.5 h-3.5" :stroke-width="1.5" />
        <span>{{ t('问专题脉络', 'Ask Topic Q&A') }}</span>
      </button>
    </div>

    <!-- Region & Primary Organization Categorized Filter Strips -->
    <div v-if="baseScopeList.length > 0" class="space-y-1.5 pt-1 border-t border-black/[0.05] dark:border-white/[0.07]">
      <div class="flex sm:flex-wrap items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x sm:overflow-visible text-[11px]">
        <button
          v-for="reg in regionOptions"
          :key="`tp-reg-${reg.id}`"
          type="button"
          @click="(e) => { regionFilter = reg.id; orgFilter = 'all'; activeTopicId = ''; centerPillIntoView(e) }"
          class="mobile-pressable inline-flex items-center gap-1 min-h-[28px] px-2.5 rounded-lg font-medium whitespace-nowrap shrink-0 transition-colors"
          :class="
            regionFilter === reg.id
              ? 'bg-[#007AFF] text-white font-semibold'
              : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200/70'
          "
        >
          <MapPin v-if="reg.id !== 'all'" class="w-3 h-3 shrink-0" :stroke-width="1.75" />
          <span>{{ reg.label }}</span>
          <span class="opacity-75 tabular-nums">{{ reg.count }}</span>
        </button>
      </div>
      <div v-if="orgOptions.length > 1" class="flex sm:flex-wrap items-center gap-1.5 overflow-x-auto no-scrollbar scroll-fade-x sm:overflow-visible text-[11px]">
        <button
          v-for="org in orgOptions"
          :key="`tp-org-${org.id}`"
          type="button"
          @click="(e) => { orgFilter = org.id; activeTopicId = ''; centerPillIntoView(e) }"
          class="mobile-pressable inline-flex items-center gap-1 min-h-[26px] px-2 rounded-lg border font-medium whitespace-nowrap shrink-0 transition-colors"
          :class="
            orgFilter === org.id
              ? 'bg-zinc-900 text-white border-zinc-900 dark:bg-white dark:text-zinc-900 dark:border-white font-semibold'
              : 'bg-white text-zinc-600 border-black/[0.08] dark:bg-[#1C1C1E] dark:text-zinc-300 dark:border-white/[0.1]'
          "
        >
          <Building2 v-if="org.id !== 'all'" class="w-3 h-3 shrink-0" :stroke-width="1.75" />
          <span>{{ org.label }}</span>
          <span class="opacity-70 tabular-nums">{{ org.count }}</span>
        </button>
      </div>
    </div>

    <!-- Empty Archive/Active Fallback -->
    <div
      v-if="!activeTopic"
      class="ios-surface-2 px-4 py-6 text-center text-xs text-zinc-500 dark:text-zinc-400"
    >
      {{
        (regionFilter !== 'all' || orgFilter !== 'all')
          ? t('当前地区或机构筛选下暂无匹配专题，请点击「全部地区」重置。', 'No matching topics under active filters.')
          : topicScope === 'archive'
            ? t('当前暂无已完结的历史专题，活跃专题完结后会自动沉淀于此。', 'No concluded topics archived yet; concluded spotlights automatically move here.')
            : t('当前暂无活跃专题，可切至上方「历史专题库」回看已完结大事件。', 'No active topics at the moment; check Topic Archive above for concluded stories.')
      }}
    </div>

    <template v-else>
      <!-- Structured Topic Selector: Grid Cards in Archive View (Categorized), Sleek Pills in Active View -->
      <div v-if="topicScope === 'archive'" class="grid grid-cols-1 sm:grid-cols-2 gap-2" role="tablist">
        <button
          v-for="tp in currentTopicList"
          :key="tp.topic_id"
          type="button"
          role="tab"
          :aria-selected="activeTopic.topic_id === tp.topic_id"
          @click="selectTopic(tp.topic_id)"
          class="ios-tap text-left rounded-xl p-2.5 border transition-colors space-y-1"
          :class="
            activeTopic.topic_id === tp.topic_id
              ? 'bg-zinc-900 text-white border-zinc-900 dark:bg-[#0A84FF] dark:border-[#0A84FF]'
              : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] border-transparent text-zinc-800 dark:text-zinc-100 hover:bg-zinc-200/70'
          "
        >
          <div class="flex flex-wrap items-center justify-between gap-1 text-[10px]">
            <div class="flex flex-wrap items-center gap-1">
              <span
                v-if="tp.region_label"
                class="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded font-semibold"
                :class="activeTopic.topic_id === tp.topic_id ? 'bg-white/20 text-white' : 'bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200'"
              >
                <MapPin class="w-2.5 h-2.5 shrink-0" :stroke-width="1.75" />
                <span>{{ tp.region_label }}</span>
              </span>
              <span
                v-for="org in (tp.primary_orgs || []).slice(0, 2)"
                :key="`${tp.topic_id}-o-${org}`"
                class="px-1.5 py-0.2 rounded font-medium"
                :class="activeTopic.topic_id === tp.topic_id ? 'bg-white/15 text-white' : 'bg-blue-500/10 text-blue-700 dark:text-blue-300'"
              >
                {{ org }}
              </span>
            </div>
            <span class="tabular-nums opacity-75 shrink-0">{{ tp.source_count }} 源 · {{ tp.timeline.length }} 条</span>
          </div>
          <div class="text-xs font-semibold leading-snug line-clamp-2">{{ pickBiText(tp.title, tp.title_en) }}</div>
        </button>
      </div>

      <div v-else class="space-y-1.5">
        <div class="flex flex-wrap items-center gap-1.5" role="tablist">
          <button
            v-for="(tp, idx) in currentTopicList"
            :key="tp.topic_id"
            type="button"
            role="tab"
            :aria-selected="activeTopic.topic_id === tp.topic_id"
            @click="selectTopic(tp.topic_id)"
            class="ios-tap items-center gap-1.5 min-h-[34px] px-2.5 py-1 rounded-xl text-xs font-medium transition-colors max-w-full"
            :class="[
              idx >= 3 && activeTopic.topic_id !== tp.topic_id && !mobileTopicsExpanded ? 'hidden sm:inline-flex' : 'inline-flex',
              activeTopic.topic_id === tp.topic_id
                ? 'bg-zinc-900 text-white dark:bg-[#0A84FF] font-semibold'
                : 'bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200/70 dark:hover:bg-zinc-700/70',
            ]"
          >
            <span
              class="px-1.5 py-0.2 rounded-md text-[10px] font-semibold shrink-0"
              :class="
                activeTopic.topic_id === tp.topic_id
                  ? 'bg-white/20 text-white'
                  : lifecycleBadgeClass(tp.lifecycle_status)
              "
            >
              {{ lifecycleLabel(tp) }}
            </span>
            <span v-if="tp.region_label" class="text-[10px] opacity-80 shrink-0">{{ tp.region_label }}</span>
            <span class="truncate max-w-[230px]">{{ pickBiText(tp.title, tp.title_en) }}</span>
            <span
              v-if="getTopicDeltaBadge(tp)"
              class="px-1.5 py-0.2 rounded-md text-[10px] font-semibold tabular-nums shrink-0"
              :class="
                activeTopic.topic_id === tp.topic_id
                  ? 'bg-white/20 text-white'
                  : getTopicDeltaBadge(tp)!.hot
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'
                    : 'bg-blue-500/10 text-blue-700 dark:text-blue-300'
              "
            >
              {{ getTopicDeltaBadge(tp)!.label }}
            </span>
            <span class="opacity-70 tabular-nums shrink-0">{{ tp.timeline.length }}</span>
          </button>
        </div>

        <button
          v-if="currentTopicList.length > 3"
          type="button"
          @click="mobileTopicsExpanded = !mobileTopicsExpanded"
          class="sm:hidden w-full min-h-[32px] px-3 py-1 rounded-xl border border-black/[0.08] dark:border-white/[0.1] bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs font-semibold text-[#007AFF] dark:text-[#66B2FF] inline-flex items-center justify-center gap-1"
          data-testid="mobile-topics-expand-btn"
        >
          <span>
            {{
              mobileTopicsExpanded
                ? t('收起专题列表', 'Collapse topics')
                : t(`展开全部 ${currentTopicList.length} 个活跃专题`, `Show all ${currentTopicList.length} active topics`)
            }}
          </span>
          <component :is="mobileTopicsExpanded ? ChevronUp : ChevronDown" class="w-3.5 h-3.5 shrink-0" />
        </button>
      </div>

      <!-- Active Topic Header + Timeline Order Switch -->
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 pt-0.5">
        <div class="space-y-1 min-w-0">
          <div class="flex flex-wrap items-center gap-1.5">
            <span
              class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold shrink-0"
              :class="lifecycleBadgeClass(activeTopic.lifecycle_status)"
            >
              <span
                v-if="activeTopic.lifecycle_status !== 'concluded'"
                class="jx-sonar-dot jx-sonar-emerald"
                aria-hidden="true"
              />
              <span>{{ lifecycleLabel(activeTopic) }}</span>
            </span>
            <span
              v-if="activeTopic.region_label"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 shrink-0"
            >
              <MapPin class="w-3 h-3 shrink-0" :stroke-width="1.75" />
              <span>{{ activeTopic.region_label }}</span>
            </span>
            <span
              v-for="org in (activeTopic.primary_orgs || []).slice(0, 2)"
              :key="`hd-org-${org}`"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-medium bg-[#F5F5F7] dark:bg-[#2C2C2E] text-zinc-700 dark:text-zinc-200 shrink-0"
            >
              <Building2 class="w-3 h-3 shrink-0" :stroke-width="1.75" />
              <span>{{ org }}</span>
            </span>
            <span
              v-if="getTopicDeltaBadge(activeTopic)"
              class="px-2 py-0.5 rounded-md text-[11px] font-semibold tabular-nums shrink-0"
              :class="
                getTopicDeltaBadge(activeTopic)!.hot
                  ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300'
                  : 'bg-[#007AFF]/10 text-[#007AFF] dark:text-[#0A84FF]'
              "
            >
              {{ getTopicDeltaBadge(activeTopic)!.label }}
            </span>
            <h2 class="text-[16px] sm:text-lg font-bold text-zinc-950 dark:text-white leading-snug w-full">
              {{ pickBiText(activeTopic.title, activeTopic.title_en) }}
            </h2>
          </div>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">
            {{ activeTopic.subtitle }}
            <template v-if="!showSourceRepeatInSubtitle(activeTopic.subtitle)">
              · <span class="tabular-nums">{{ t(`${activeTopic.source_count} 家信源 · ${activeTopic.timeline.length} 个脉络节点`, `${activeTopic.source_count} sources · ${activeTopic.timeline.length} nodes`) }}</span>
            </template>
            <template v-if="formatTopicSpan(activeTopic)">
              · <span class="tabular-nums">{{ formatTopicSpan(activeTopic) }}</span>
            </template>
          </p>
        </div>

        <button
          type="button"
          @click="timelineOrder = timelineOrder === 'desc' ? 'asc' : 'desc'"
          class="ios-tap self-start inline-flex items-center gap-1 px-2.5 min-h-[30px] rounded-lg bg-[#F5F5F7] dark:bg-[#2C2C2E] text-[11px] font-semibold text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200/70 shrink-0"
          :aria-label="t('切换时间线正倒序', 'Toggle timeline order')"
        >
          <ArrowDownUp class="w-3 h-3 text-[#007AFF]" :stroke-width="1.5" />
          <span>{{ timelineOrder === 'desc' ? t('最新在前', 'Newest First') : t('从头回溯', 'Chronological') }}</span>
        </button>
      </div>

      <!-- Collapsible Topic Brief Overview & Responsive Parties Comparison (Default Collapsed on Headline Entry) -->
      <div
        v-if="activeTopic.brief_overview || (activeTopic.comparison_table && activeTopic.comparison_table.rows?.length)"
        class="rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E]/80 border border-black/[0.06] dark:border-white/[0.08] p-3 space-y-2.5 text-xs"
        data-testid="topic-brief-overview"
      >
        <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
          <div v-if="activeTopic.brief_overview" class="flex items-start gap-2 text-zinc-700 dark:text-zinc-200 leading-relaxed min-w-0 flex-1">
            <FileText class="w-3.5 h-3.5 text-[#007AFF] shrink-0 mt-0.5" :stroke-width="1.75" />
            <p :class="overviewExpanded ? '' : 'line-clamp-2'">{{ activeTopic.brief_overview }}</p>
          </div>
          <button
            v-if="activeTopic.comparison_table && activeTopic.comparison_table.rows?.length"
            type="button"
            @click="overviewExpanded = !overviewExpanded"
            class="self-start sm:self-center shrink-0 inline-flex items-center gap-1 px-2.5 min-h-[28px] rounded-lg bg-white dark:bg-[#1C1C1E] border border-black/[0.08] dark:border-white/[0.12] text-[11px] font-semibold text-[#007AFF] dark:text-[#66B2FF] hover:bg-blue-50/60 whitespace-nowrap"
            :aria-expanded="overviewExpanded"
            data-testid="topic-overview-toggle"
          >
            <span>{{ overviewExpanded ? t('收起对比', 'Collapse') : t('展开全局脉络与各方立场对比', 'Expand Overview & Stances') }}</span>
            <ChevronDown class="w-3.5 h-3.5 transition-transform" :class="{ 'rotate-180': overviewExpanded }" />
          </button>
        </div>

        <template v-if="overviewExpanded && activeTopic.comparison_table && activeTopic.comparison_table.rows?.length">
          <!-- Desktop Table (>= sm) -->
          <div
            class="hidden sm:block overflow-x-auto rounded-lg border border-black/[0.06] dark:border-white/[0.08] bg-white dark:bg-[#1C1C1E]"
            data-testid="topic-comparison-table"
          >
            <table class="w-full text-left text-[11.5px] border-collapse">
              <thead class="bg-zinc-50 dark:bg-zinc-800/70 text-zinc-600 dark:text-zinc-300">
                <tr>
                  <th
                    v-for="(hdr, hi) in activeTopic.comparison_table.headers"
                    :key="`th-${hi}`"
                    class="px-2.5 py-1.5 font-semibold whitespace-nowrap"
                  >
                    {{ hdr }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-black/[0.05] dark:divide-white/[0.06]">
                <tr v-for="(r, ri) in activeTopic.comparison_table.rows" :key="`tr-${ri}`">
                  <td
                    v-for="(cell, ci) in r"
                    :key="`td-${ri}-${ci}`"
                    class="px-2.5 py-1.5 text-zinc-700 dark:text-zinc-200"
                    :class="ci === 0 ? 'font-semibold text-zinc-900 dark:text-white whitespace-nowrap' : ''"
                  >
                    {{ cell }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Mobile Stacked Cards (< 640px, zero squeezed 2-char columns) -->
          <div class="sm:hidden space-y-2" data-testid="topic-comparison-mobile-cards">
            <div
              v-for="(r, ri) in activeTopic.comparison_table.rows"
              :key="`mc-${ri}`"
              class="rounded-lg border border-black/[0.06] dark:border-white/[0.08] bg-white dark:bg-[#1C1C1E] p-2.5 space-y-1 text-[11.5px]"
            >
              <div class="font-bold text-zinc-950 dark:text-white">{{ r[0] }}</div>
              <div v-if="r[1]" class="text-zinc-700 dark:text-zinc-200 leading-relaxed">
                <span class="font-semibold text-zinc-500 dark:text-zinc-400">{{ activeTopic.comparison_table.headers?.[1] || t('核心立场', 'Stance') }}：</span>{{ r[1] }}
              </div>
              <div v-if="r[2]" class="text-zinc-600 dark:text-zinc-300 leading-relaxed">
                <span class="font-semibold text-zinc-500 dark:text-zinc-400">{{ activeTopic.comparison_table.headers?.[2] || t('关键影响', 'Impact') }}：</span>{{ r[2] }}
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Clean Single-Rail Timeline -->
      <ol class="relative border-l-2 border-black/[0.08] dark:border-white/[0.12] ml-2 pl-4 space-y-2">
        <li
          v-for="(node, idx) in visibleNodes"
          :key="`${activeTopic.topic_id}-${idx}-${node.title.slice(0, 16)}`"
          class="relative rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] p-3 transition-colors"
        >
          <span
            class="absolute -left-[22px] top-4 w-2.5 h-2.5 rounded-full ring-4 ring-white dark:ring-[#1C1C1E]"
            :class="idx === 0 && timelineOrder === 'desc' ? 'bg-[#007AFF]' : 'bg-zinc-400 dark:bg-zinc-500'"
          />
          <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] mb-1">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="px-1.5 py-0.5 rounded-md font-semibold" :class="stageBadgeClass(node.stage_tag)">
                {{ node.stage_tag }}
              </span>
              <span class="inline-flex items-center gap-1 text-zinc-500 dark:text-zinc-400 tabular-nums font-medium">
                <Clock class="w-3 h-3" :stroke-width="1.5" />
                <span>{{ formatNodeClock(node.time) }}</span>
              </span>
              <span class="text-zinc-500 dark:text-zinc-400">
                · {{ translateSourceName(node.publisher_name || node.source_name, node.title) }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <button
                v-if="node.event_id"
                type="button"
                @click="emit('jump-event-id', node.event_id, node.url)"
                class="inline-flex items-center px-2 min-h-[28px] rounded-lg bg-white dark:bg-[#3A3A3C] text-[#007AFF] dark:text-[#0A84FF] font-semibold hover:underline shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
              >
                {{ t('定位简报', 'Locate') }}
              </button>
              <a
                v-if="normalizeExternalUrl(node.url)"
                :href="normalizeExternalUrl(node.url)!"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
                class="inline-flex items-center gap-0.5 px-2 min-h-[28px] rounded-lg text-zinc-600 dark:text-zinc-300 hover:text-[#007AFF]"
              >
                <span>{{ t('原文', 'Source') }}</span>
                <ExternalLink class="w-3 h-3" :stroke-width="1.5" />
              </a>
            </div>
          </div>
          <a
            v-if="normalizeExternalUrl(node.url)"
            :href="normalizeExternalUrl(node.url)!"
            target="_blank"
            rel="noopener noreferrer"
            @click.stop
            class="block text-[14px] font-semibold text-zinc-950 dark:text-white hover:text-[#007AFF] leading-snug"
          >
            {{ pickBiText(node.title_zh || node.title, node.title_en || node.title) }}
          </a>
          <div v-else class="text-[14px] font-semibold text-zinc-950 dark:text-white leading-snug">
            {{ pickBiText(node.title_zh || node.title, node.title_en || node.title) }}
          </div>
          <p v-if="node.summary" class="text-xs text-zinc-600 dark:text-zinc-300 mt-1 line-clamp-2 leading-relaxed">
            {{ pickBiText(node.summary_zh || node.summary, node.summary_en || node.summary) }}
          </p>
        </li>
      </ol>

      <div v-if="sortedNodes.length > 6" class="flex justify-center pt-0.5">
        <button
          type="button"
          @click="expandedAllNodes = !expandedAllNodes"
          class="ios-tap inline-flex items-center gap-1 px-3.5 min-h-[34px] rounded-xl bg-[#F5F5F7] dark:bg-[#2C2C2E] text-xs font-medium text-zinc-700 dark:text-zinc-200 hover:bg-zinc-200/70"
        >
          <span>
            {{
              expandedAllNodes
                ? t('收起部分节点', 'Show Fewer')
                : t(`展开全部 ${sortedNodes.length} 个脉络节点`, `Expand All ${sortedNodes.length} Nodes`)
            }}
          </span>
          <ChevronUp v-if="expandedAllNodes" class="w-3.5 h-3.5" />
          <ChevronDown v-else class="w-3.5 h-3.5" />
        </button>
      </div>
    </template>
  </section>
</template>
