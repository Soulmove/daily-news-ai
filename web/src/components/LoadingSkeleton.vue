<script setup lang="ts">
defineProps<{
  variant?: 'cards' | 'list' | 'grid'
  count?: number
}>()
</script>

<template>
  <div class="space-y-3 animate-pulse" aria-busy="true" aria-live="polite">
    <!-- Grid variant (e.g. Tools / AI Companies / Calendar) -->
    <div v-if="variant === 'grid'" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      <div
        v-for="i in (count || 6)"
        :key="i"
        class="h-44 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 flex flex-col justify-between"
      >
        <div class="space-y-2.5">
          <div class="flex items-center justify-between gap-2">
            <div class="h-4 w-28 rounded bg-slate-200 dark:bg-slate-800" />
            <div class="h-5 w-16 rounded-full bg-slate-200 dark:bg-slate-800" />
          </div>
          <div class="h-3.5 w-full rounded bg-slate-100 dark:bg-slate-800/80" />
          <div class="h-3.5 w-4/5 rounded bg-slate-100 dark:bg-slate-800/80" />
        </div>
        <div class="flex items-center gap-2 pt-2">
          <div class="h-5 w-14 rounded bg-slate-100 dark:bg-slate-800" />
          <div class="h-5 w-20 rounded bg-slate-100 dark:bg-slate-800" />
        </div>
      </div>
    </div>

    <!-- High-density list variant (e.g. Live Wire / Tracking index / Calendar) -->
    <div
      v-else-if="variant === 'list'"
      class="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden"
    >
      <div v-for="i in (count || 8)" :key="i" class="px-4 py-3 flex items-start gap-3 h-[68px]">
        <div class="h-3.5 w-16 rounded bg-slate-200 dark:bg-slate-800 shrink-0 mt-1" />
        <div class="flex-1 space-y-2">
          <div class="h-4 w-3/4 rounded bg-slate-200 dark:bg-slate-800" />
          <div class="h-3 w-1/3 rounded bg-slate-100 dark:bg-slate-800/80" />
        </div>
      </div>
    </div>

    <!-- Event cards variant (e.g. Today / Briefings / Finance) -->
    <div v-else class="space-y-3">
      <div
        v-for="i in (count || 4)"
        :key="i"
        class="h-40 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 sm:p-5 flex flex-col justify-between"
      >
        <div class="space-y-2.5">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <div class="h-5 w-16 rounded bg-slate-200 dark:bg-slate-800" />
              <div class="h-5 w-28 rounded bg-slate-100 dark:bg-slate-800" />
            </div>
            <div class="h-4 w-16 rounded bg-slate-100 dark:bg-slate-800" />
          </div>
          <div class="h-5 w-4/5 rounded bg-slate-200 dark:bg-slate-800" />
          <div class="h-3.5 w-full rounded bg-slate-100 dark:bg-slate-800/80" />
          <div class="h-3.5 w-2/3 rounded bg-slate-100 dark:bg-slate-800/80" />
        </div>
      </div>
    </div>
  </div>
</template>
