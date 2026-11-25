export type CategoryKey = 'finance' | 'global' | 'tech' | 'general'

export interface CategoryInfo {
  id: CategoryKey
  name: string
  nameEn: string
  shortName: string
  shortNameEn: string
  accentDotClass: string
  badgeClass: string
}

export const CATEGORIES: CategoryInfo[] = [
  {
    id: 'finance',
    name: '财经/市场',
    nameEn: 'Markets / Finance',
    shortName: '财经',
    shortNameEn: 'Markets',
    accentDotClass: 'bg-amber-500',
    badgeClass: 'bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800',
  },
  {
    id: 'global',
    name: '国际/宏观',
    nameEn: 'Global / Macro',
    shortName: '国际',
    shortNameEn: 'Global',
    accentDotClass: 'bg-blue-600',
    badgeClass: 'bg-blue-50 text-blue-800 border-blue-200 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800',
  },
  {
    id: 'tech',
    name: '科技/AI',
    nameEn: 'Tech / AI',
    shortName: '科技',
    shortNameEn: 'Tech',
    accentDotClass: 'bg-teal-600',
    badgeClass: 'bg-teal-50 text-teal-800 border-teal-200 dark:bg-teal-950/50 dark:text-teal-300 dark:border-teal-800',
  },
  {
    id: 'general',
    name: '社会/热点',
    nameEn: 'Society / Headlines',
    shortName: '热点',
    shortNameEn: 'Headlines',
    accentDotClass: 'bg-rose-600',
    badgeClass: 'bg-rose-50 text-rose-800 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800',
  },
]

export type EvidenceStatus = 'official_confirmed' | 'multi_source' | 'single_source' | 'needs_verification'

export type WorkbenchTab = 'today' | 'wire' | 'briefing' | 'ai_progress' | 'finance' | 'tracking' | 'calendar' | 'predictions' | 'tools' | 'me'

export interface FactAtom {
  atom_id: string
  subject: string
  metric_or_action: string
  value?: string | null
  unit?: string | null
  period: string
  scope: string
  fact_status: string
  attribution: string
  source_ref?: string | null
  source_url?: string | null
  source_excerpt_or_locator?: string
  is_first_party?: boolean
  first_discovered_at?: string
}

export interface SmartSourceRef {
  item_id: string
  article_id?: string
  source_id: string
  source_name: string
  publisher_name?: string
  source_kind: string
  source_tier?: string
  publisher_family?: string
  is_reprint_copy?: boolean
  title: string
  title_zh?: string
  url: string
  published_at: string | null
  published_at_source?: string | null
  fetched_at: string
  excerpt?: string | null
  deep_fetch_status?: string | null
}

export interface EventFollowup {
  is_continuing: boolean
  prev_batch_id: string | null
  prev_event_id?: string | null
  prev_title?: string | null
  delta_note: string
}

export interface SmartEvent {
  event_id: string
  storyline_id?: string
  article_ids?: string[]
  legacy_event_ids?: string[]
  title: string
  title_zh?: string
  title_en?: string
  summary_zh?: string
  summary_en?: string
  category: CategoryKey
  entities: string[]
  entity_ids?: string[]
  entity_confidences?: Record<string, number>
  importance: 'high' | 'medium' | 'normal'
  severity_tier?: 'S' | 'A' | 'B'
  severity_label?: string
  heavy_reason_tag?: string
  sentiment?: string | null
  special_note?: string | null
  material_stage?: 'ga' | 'beta' | 'waitlist' | 'announced' | null
  material_stage_label?: string | null
  material_stage_confidence?: number | null
  translation_status?: 'native_zh' | 'translated' | 'manual' | 'retry_fallback'
  translation_attempts?: number
  translation_error?: string | null
  thumbnail_url?: string | null
  evidence_status: EvidenceStatus
  evidence_label: string
  evidence_status_reason: string
  attribution_warning?: string | null
  regulatory_note?: string | null
  contradictions?: string[]
  downweight_reasons?: string[]
  quality_flags?: string[]
  radar_score?: number
  material_depth: string
  source_count: number
  platform_count: number
  independent_publisher_count?: number
  reprint_count?: number
  published_at: string | null
  event_date?: string | null
  event_date_source?: string | null
  is_stale_rehash?: boolean
  time_trust_level?: string | null
  first_discovered_at?: string | null
  first_reported_at?: string | null
  latest_fact_update_at?: string | null
  latest_reported_at?: string | null
  fetched_at: string
  input_batch_id: string
  fact_summary: string
  fact_atoms?: FactAtom[]
  ai_analysis: string
  ai_analysis_en?: string | null
  unverified_claims: string[]
  speculation_or_outlook: string | null
  speculation_or_outlook_en?: string | null
  sources: SmartSourceRef[]
  verification?: {
    all_refs_valid?: boolean
    has_primary_url?: boolean
    rejected_refs?: { ref: string; reason: string }[]
    has_first_party?: boolean
  }
  followup: EventFollowup | null
  deep_qa?: Array<{ question: string; answer: string; historical_parallel?: string }>
  is_new_in_batch: boolean
  update_kind?: 'new_discovery' | 'new_fact_update' | 'continuing_coverage'
  legacy_v1_origin?: boolean
}

export interface KeyChangeItem {
  event_id?: string
  storyline_id?: string
  headline: string
  headline_en?: string
  detail: string
  detail_en?: string
  evidence_status?: EvidenceStatus
  attribution_warning?: string | null
  source_count?: number
  primary_url?: string | null
  source_name?: string | null
}

export interface OverviewSection {
  title: string
  title_en?: string
  points: { text: string; text_en?: string; source_refs?: string[] }[]
}

export interface SmartCategoryDoc {
  schema_version: string
  batch_id: string
  input_batch_id: string
  input_cutoff_at: string
  generated_at: string
  published_at: string | null
  category: CategoryKey
  category_label: string
  generation_mode: string
  legacy_v1_notice?: string
  key_changes: KeyChangeItem[]
  overview_sections: OverviewSection[]
  events: SmartEvent[]
  missing?: boolean
  error?: string
  is_fallback?: boolean
  fallback_reason?: string | null
}

export interface SimulatedPerspective {
  id: string
  role: string
  perspective_tag: string
  target_event_id?: string | null
  pro_argument?: string | null
  con_argument?: string | null
  key_unknown?: string | null
  next_catalyst?: string | null
  content: string
  stance: string
}

export interface SimulatedCommentsDoc {
  schema_version: string
  batch_id: string | null
  input_batch_id?: string | null
  generated_at: string | null
  category: CategoryKey
  is_ai_simulated: true
  status: 'ok' | 'not_generated' | 'generation_failed' | 'disabled' | 'batch_mismatch' | 'missing'
  disclaimer: string
  comments: SimulatedPerspective[]
}

export type SourceHealthState = 'ok' | 'empty' | 'error' | 'stale' | 'retired'

export interface RawSourceReport {
  id: string
  name: string
  category: CategoryKey
  kind: string
  status: SourceHealthState
  http_status?: number | null
  upstream_status?: string | null
  upstream_updated_at?: string | null
  fetched_at: string
  last_success_at?: string | null
  item_count: number
  pub_date_coverage?: number
  error_message?: string | null
  fallback_used?: boolean
  fallback_item_count?: number
}

export interface RawItem {
  item_id: string
  source_id: string
  source_name: string
  source_kind: string
  citable_as_news?: boolean
  category: CategoryKey
  title: string
  url: string
  canonical_url: string
  published_at: string | null
  published_at_source?: string | null
  fetched_at: string
  excerpt?: string | null
  metric_label?: string | null
  rank?: number
  is_fallback?: boolean
}

export interface RawPlatform {
  id: string
  name: string
  kind: string
  category: CategoryKey
  status: SourceHealthState
  upstream_status?: string | null
  upstream_updated_at?: string | null
  fetched_at: string
  last_success_at?: string | null
  error_message?: string | null
  fallback_used?: boolean
  fallback_items?: RawItem[]
  items: RawItem[]
}

export interface RawClusterEvent {
  cluster_id: string
  primary_title: string
  primary_url: string
  category: CategoryKey
  source_kind: string
  published_at: string | null
  fetched_at: string
  excerpt: string | null
  metric_label: string | null
  appearances: {
    item_id: string
    source_id: string
    source_name: string
    title: string
    url: string
    published_at: string | null
    excerpt?: string | null
    metric_label?: string | null
    is_fallback?: boolean
  }[]
}

export interface RawBatchMeta {
  schema_version: string
  batch_id: string
  fetched_at: string
  published_at: string | null
  target_cadence_minutes: number
  schedule_source?: string
  crawl_status: 'ok' | 'partial' | 'failed' | 'legacy'
  summary: {
    configured_sources: number
    ok_sources: number
    empty_sources: number
    error_sources: number
    stale_sources: number
    retired_sources: number
    total_raw_items: number
    deduped_events: number
  }
  sources: RawSourceReport[]
  retired_sources?: { id: string; name: string; category: string; reason: string }[]
}

export interface HistoryIndexEntry {
  display: string
  path: string
  batch_id?: string
  input_batch_id?: string
  input_cutoff_at?: string
  fetched_at?: string
  generated_at?: string
  published_at?: string
  status?: string
  has_comments?: boolean
  categories?: string[]
  ok_sources?: number
  error_sources?: number
  total_items?: number
}

export interface ManifestV2 {
  schema_version: string
  site_published_at: string
  raw: {
    latest_batch_id: string
    latest_path: string
    meta_path: string
    fetched_at: string
    published_at: string
    target_cadence_minutes: number
    schedule_source?: string
    status: 'ok' | 'partial' | 'failed'
    summary: RawBatchMeta['summary']
    categories: Record<CategoryKey, { path: string; status: string; item_count: number; ok_sources: number; error_sources: number }>
  }
  smart: {
    latest_batch_id: string
    latest_path: string
    meta_path: string
    input_batch_id: string
    input_raw_path: string
    input_cutoff_at: string
    generated_at: string
    published_at: string
    target_cadence_hours: number
    status: 'complete' | 'partial' | 'failed'
    model_name?: string
    configured_primary_model?: string
    has_comments: boolean
    categories: Record<
      CategoryKey,
      {
        batch_id: string | null
        path: string | null
        comments_path: string | null
        input_batch_id: string
        input_cutoff_at: string
        generated_at: string | null
        status: string
        is_fallback: boolean
        fallback_reason?: string | null
        item_count: number
        verified_count: number
        needs_verification_count: number
        has_comments: boolean
      }
    >
  }
  scheduler?: {
    provider: string
    raw_cron: string
    smart_cron: string
    note: string
  }
  connectors?: {
    latest_path: string
    fetched_at: string
    summary: {
      total_connectors: number
      healthy_connectors: number
      total_first_party_items: number
      tech_tools_count?: number
      calendar_events_count?: number
    }
  }
  gemini_quota?: {
    total_configured_keys: number
    healthy_keys: number
    cooled_down_keys: number
    exhausted_keys: number
    daily_calls_total: number
    updated_at?: string
  }
  v3?: {
    schema_version: string
    generated_at: string
    batch_id: string
    entities_path: string
    storylines_path: string
    topics_path?: string
    live_wire_path?: string
    ai_progress_path?: string
    finance_impact_path?: string
    calendar_path: string
    tech_tools_path: string
    radar_path: string
    predictions_path: string
    connectors_path: string
    entities_count?: number
    storylines_count?: number
    topics_count?: number
    ai_progress_count?: number
    finance_impact_count?: number
    calendar_count?: number
    calendar_ics_path?: string
    calendar_ics_count?: number
    calendar_tbd_skipped?: number
    feed_path?: string
    feeds_by_category?: Record<string, string>
    tech_tools_count?: number
    radar_count?: number
  }
}

export interface EntityProfile {
  entity_id: string
  canonical_name: string
  entity_type: string
  category?: CategoryKey | string
  sector?: string
  tickers: { market: string; symbol: string; label: string }[]
  aliases: string[]
  cik?: string | null
  hkex_code?: string | null
  cninfo_code?: string | null
  industry_tags?: string[]
  operating_variables: string[]
  supply_chain_upstream: string[]
  supply_chain_downstream: string[]
  validation_milestones: string[]
  model_state?: {
    status: string
    last_verified_at: string | null
    current_thesis: string
  }
  model_updates?: unknown[]
  recent_events: {
    event_id: string
    storyline_id: string
    title: string
    title_en?: string
    category: CategoryKey
    evidence_status: EvidenceStatus
    update_kind: string
    first_discovered_at?: string | null
    latest_reported_at?: string | null
    primary_url?: string | null
  }[]
  recent_filings: {
    form: string
    filing_date: string
    report_date?: string | null
    items?: string[]
    description?: string
    url: string
  }[]
  financial_actuals: {
    metric: string
    value: string
    unit: string
    period_end: string
    filed: string
    form: string
    source: string
  }[]
  change_count_30d: number
  recent_event_count?: number
  last_event_at?: string | null
}

export interface FactDiff {
  change_type: string
  change_type_label: string
  new_facts: string[]
  corrections: string[]
  unchanged_background: string[]
  new_source_urls?: (string | null)[]
}

export interface InvestmentCard {
  fact_change: string
  operating_variables: string[]
  supply_chain_links: {
    upstream: string[]
    downstream: string[]
  }
  related_assets: {
    entity: string
    ticker: string
    relation: string
    basis: string
  }[]
  validation_nodes: string[]
  financial_actuals_preview: EntityProfile['financial_actuals']
  market_data_disclosure: string
}

export interface StorylineNode {
  batch_id: string
  event_id: string
  timestamp: string
  fetched_at?: string
  title: string
  title_en?: string
  fact_summary?: string
  summary_en?: string
  evidence_status: EvidenceStatus
  delta_note: string
  source_count: number
  independent_publisher_count?: number
  sources_preview: { source_name: string; url: string; published_at?: string | null }[]
}

export interface StorylineDossier {
  storyline_id: string
  current_event_id: string
  title: string
  title_zh?: string
  title_en?: string
  summary_zh?: string
  summary_en?: string
  category: CategoryKey
  entities: string[]
  entity_ids: string[]
  entity_confidences?: Record<string, number>
  current_stage: string
  evidence_status: EvidenceStatus
  evidence_label: string
  evidence_tier?: string
  evidence_tier_label?: string
  first_discovered_at?: string | null
  first_reported_at?: string | null
  latest_fact_update_at?: string | null
  latest_reported_at?: string | null
  fact_diff: FactDiff
  contradictions: string[]
  open_questions: string[]
  next_catalyst?: string | null
  fact_atoms: FactAtom[]
  investment_card: InvestmentCard | null
  timeline: StorylineNode[]
  sources: SmartSourceRef[]
  ai_analysis?: string
  unverified_claims?: string[]
  stance_comparison?: Array<{ side: string; summary: string; key_sources?: string[] }>
}

export interface CatalystEvent {
  calendar_id: string
  title: string
  title_en?: string
  scheduled_at: string | null
  original_time_note?: string | null
  timezone: string
  certainty: 'confirmed_official' | 'tbd' | string
  certainty_label: string
  is_past?: boolean
  is_clock_tbd?: boolean
  is_breaking_schedule?: boolean
  source_channel?: string
  category: string
  event_type?: 'politics_macro' | 'expo_summit' | 'tech_launch' | 'central_bank' | 'earnings_capital' | string
  event_type_label?: string
  region?: 'china' | 'us' | 'europe_apac' | 'global' | string
  region_label?: string
  country?: string
  city?: string
  location_display?: string
  countdown_days?: number | null
  entity_ids: string[]
  storyline_id?: string | null
  event_id?: string | null
  watch_variable: string
  watch_variable_en?: string
  pre_expectation?: string | null
  pre_expectation_en?: string | null
  actual_result?: string | null
  post_deviation?: string | null
  source_name: string
  source_url: string | null
  is_custom?: boolean
}

export interface PredictionVersion {
  version: number
  updated_at: string
  judgment: string
  probability_pct: number
  reason: string
}

export interface PredictionSettlement {
  outcome: 'correct' | 'incorrect' | 'indeterminate'
  settled_at: string
  evidence_url?: string | null
  evidence_title?: string | null
  note: string
  brier_score?: number | null
}

export interface PredictionRecord {
  prediction_id: string
  mode: 'live' | 'replay'
  status: 'open' | 'settled'
  category?: 'tech_ai' | 'market' | 'macro' | 'global_space' | string
  title: string
  target_entity_id?: string | null
  target_entity?: string | null
  question: string
  created_at: string
  due_at: string
  lock_at?: string
  win_rule: string
  lose_rule: string
  indeterminate_rule?: string
  supporting_evidence: string[]
  opposing_evidence: string[]
  core_assumption: string
  invalidation_trigger: string
  probability_pct: number
  probability_note?: string
  current_judgment: string
  versions: PredictionVersion[]
  settlement: PredictionSettlement | null
  is_seed?: boolean
  source_type?: 'auto_market' | 'user_proposal' | 'ai_flash' | 'seed' | string
  ticker?: string
  base_price?: number | null
  target_price?: number | null
  proposer_username?: string
  arena_status?: 'open' | 'locked' | 'settled' | string
  arena_outcome?: 'yes' | 'no' | 'void' | null
  settled_value?: number | null
}

export interface TechToolEntry {
  tool_id: string
  name: string
  repo?: string | null
  tool_type: string
  sector?: string
  entity_id?: string | null
  availability_stage: 'ga' | 'beta' | 'waitlist' | 'announced' | string
  availability_label: string
  latest_version?: string | null
  version_published_at?: string | null
  license?: string | null
  stars?: number | null
  official_url: string
  release_url?: string | null
  docs_url?: string | null
  summary: string
  deployment_requirements: string
  pricing_or_cost: string
  checked_at: string
  source_name: string
  source_url?: string | null
  pain_point?: string
  best_for?: string
  comparison_note?: string
}

export interface RadarItem {
  event_id: string
  storyline_id: string
  title: string
  title_zh?: string
  title_en?: string
  summary_zh?: string
  summary_en?: string
  category: CategoryKey
  entity_ids: string[]
  radar_score: number
  signal_type?: string
  why_in_radar?: string
  evidence_status: EvidenceStatus
  independent_publisher_count: number
  reprint_count: number
  first_discovered_at?: string | null
  latest_reported_at?: string | null
  primary_url?: string | null
}

export interface ConnectorReport {
  connector_id: string
  connector_name: string
  source_tier: string
  status: 'ok' | 'cached_304' | 'partial' | 'empty' | 'error' | string
  fetched_at: string
  latency_ms: number
  item_count: number
  calendar_count?: number
  error_message?: string | null
  tos_note?: string | null
}

export interface ConnectorsLatestDoc {
  schema_version: string
  fetched_at: string
  summary: {
    total_connectors: number
    healthy_connectors: number
    total_first_party_items: number
    tech_tools_count: number
    calendar_events_count: number
  }
  connectors: ConnectorReport[]
}

export type WatchlistKind = 'company' | 'ticker' | 'industry' | 'tech' | 'event'

export interface WatchlistItem {
  id: string
  kind: WatchlistKind
  label: string
  entity_id?: string | null
  market?: string | null
  keywords: string[]
  created_at: string
  muted?: boolean
}

export interface ResearchNote {
  note_id: string
  target_type: 'event' | 'storyline' | 'entity' | 'qa'
  target_id: string
  title: string
  entity_ids?: string[]
  tickers?: string[]
  question?: string
  answer_markdown: string
  evidence_urls: string[]
  data_cutoff_at?: string | null
  created_at: string
}

export interface AlertRuleSettings {
  firstPartyOnly: boolean
  maxIndependentThreshold: number
  quietHoursStart: string
  quietHoursEnd: string
}

export interface HealthBadgeInfo {
  level: 'healthy' | 'delayed' | 'partial' | 'stale' | 'history'
  label: string
  detail: string
  pillClass: string
}

export interface MajorTopicNode {
  time: string | null
  time_source?: 'published' | 'estimated' | string
  stage_tag: string
  title: string
  title_zh?: string
  title_en?: string
  summary: string
  summary_zh?: string
  summary_en?: string
  source_name: string
  publisher_name?: string
  url: string | null
  event_id: string | null
}

export type TopicLifecycleStatus = 'starting' | 'ongoing' | 'ending_soon' | 'ended'

export interface MajorTopicSpotlight {
  topic_id: string
  title: string
  title_en?: string
  subtitle: string
  badge: string
  category: string
  region?: string
  region_label?: string
  primary_orgs?: string[]
  domain_tag?: string
  lifecycle_status?: TopicLifecycleStatus
  lifecycle_label?: string
  started_at?: string
  ended_at?: string | null
  archived?: boolean
  is_auto_clustered?: boolean
  entity_ids?: string[]
  updated_at: string
  total_mentions: number
  source_count: number
  recent_6h_count?: number
  today_count?: number
  event_ids: string[]
  timeline: MajorTopicNode[]
  brief_overview?: string
  comparison_table?: { headers: string[]; rows: string[][] } | null
}

export interface AiModelLineageNode {
  generation: string
  release_date: string
  status?: string
  specs: string
  pricing_or_license?: string
  filter_keyword?: string
  highlight: string
}

export interface AiRelatedSource {
  source_name: string
  url?: string
  is_first_hand?: boolean
}

export interface AiProgressItem {
  id: string
  date: string
  company_id: string
  company_name: string
  region: string
  category: string
  category_en?: string
  title: string
  title_en?: string
  what_it_does: string
  what_it_does_en?: string
  who_cares?: string
  limitations: string
  limitations_en?: string
  source_name: string
  source_url?: string
  event_id?: string | null
  is_open_source?: boolean
  is_first_hand?: boolean
  source_tier?: string
  milestone_dim?: string
  milestone_dim_label?: string
  milestone_dim_label_en?: string
  is_recent_72h?: boolean
  is_baseline_milestone?: boolean
  related_sources?: AiRelatedSource[]
}

export interface AiCompanyProgress {
  company_id: string
  company_name: string
  company_name_en?: string
  region: string
  region_en?: string
  flagship_model: string
  open_source_line: string
  access_limits: string
  access_limits_en?: string
  model_lineage?: AiModelLineageNode[]
  recent_count: number
  archive_count?: number
  latest_date: string
  latest_headline: string
  items: AiProgressItem[]
}

export interface AiProgressDoc {
  schema_version: string
  generated_at: string
  live_updated_at?: string
  batch_id: string
  search_grounded?: boolean
  archive_path?: string
  archive_total?: number
  weekly_digest: {
    period_label: string
    period_label_en?: string
    summary: string
    summary_en?: string
    highlights: AiProgressItem[]
  }
  companies: AiCompanyProgress[]
  timeline: AiProgressItem[]
  model_comparison_matrix?: Array<{
    model_name: string
    org: string
    region: string
    release_date: string
    positioning: string
    context_window: string
    pricing_input: string
    pricing_output: string
    weight_type: string
    strengths: string
    weaknesses: string
  }>
}

export interface LiveWireItem {
  id: string
  title: string
  title_en?: string
  excerpt: string
  excerpt_en?: string
  category: CategoryKey | string
  source_name: string
  url: string
  published_at: string
  severity_tier?: 'S' | 'A' | 'B'
  heavy_reason_tag?: string | null
  importance: 'high' | 'normal' | string
  tag: string
}

export interface BreakingHighlightItem {
  id: string
  title: string
  excerpt: string
  category: CategoryKey | string
  severity_tier?: 'S' | 'A' | 'B'
  breaking_label?: string
  source_name: string
  url: string
  published_at: string
  related_count?: number
  related_titles?: string[]
}

export interface LiveWireDoc {
  schema_version: string
  updated_at: string
  status: string
  sources_online: string
  total: number
  breaking_highlights?: BreakingHighlightItem[]
  items: LiveWireItem[]
}

export interface FinanceSampleBasis {
  sample_n: number
  volatility_pct: number
  volatility_source: string
  horizon: string
  confidence_label: string
  confidence_label_en?: string
}

export interface MarketQuoteItem {
  symbol?: string
  ticker: string
  name: string
  name_en?: string
  market: string
  role?: string
  price: number
  change?: number | null
  pct_change?: number | null
  atr_20d_pct?: number | null
  source?: string
}

export interface FinanceImpactBar {
  market: string
  sector: string
  sector_en?: string
  pct_low: number
  pct_high: number
  direction: 'positive' | 'negative' | 'mixed'
  proxy_ticker?: string | null
  logic: string
  logic_en?: string
}

export interface FinanceIfThen {
  cond: string
  result: string
  tone: 'bullish' | 'bearish' | 'neutral'
}

export interface FinanceMilestone {
  date: string
  status: 'done' | 'current' | 'upcoming'
  label: string
}

export interface FinancePricedInAnalysis {
  status_code: 'unpriced' | 'overseas_priced_in' | 'partially_priced' | 'fully_priced' | string
  status_label: string
  status_label_en?: string
  session_context: string
  expectation_gap: string
}

export interface FinanceTransmissionStock {
  name: string
  code: string
  market: string
  exposure_logic: string
  direction: 'positive' | 'negative' | 'mixed' | string
}

export interface FinanceTransmissionLayer {
  tier: number
  tier_label: string
  summary: string
  stocks: FinanceTransmissionStock[]
}

export interface FinanceHistoricalPrecedent {
  date: string
  event_title: string
  t1_reaction: string
  t5_reaction: string
  lesson?: string
}

export interface FinanceQuantIfThen {
  case: 'bull' | 'bear' | 'watch' | string
  label: string
  trigger_metric: string
  threshold: string
  action_implication: string
}

export interface EventMarketImpact {
  id: string
  event_id: string
  rule_id: string
  validation_status?: 'verified' | 'insufficient_evidence'
  validation_note?: string
  evidence_tier?: string
  evidence_tier_label?: string
  effective_date_label?: string | null
  qualifier_badge?: string | null
  carried_over?: boolean
  event_title: string
  event_title_en?: string
  event_summary?: string
  event_summary_en?: string
  category: string
  published_at: string
  source_name: string
  source_url?: string
  sources?: { source_name: string; url: string }[]
  tag: string
  tag_en?: string
  polarity: 'bullish' | 'bearish' | 'divergent'
  intensity: number
  one_liner: string
  one_liner_en?: string
  sample_basis?: FinanceSampleBasis | null
  affected_tickers?: Record<string, number>
  realized_quotes?: MarketQuoteItem[]
  bars: FinanceImpactBar[]
  if_then: FinanceIfThen[]
  milestones: FinanceMilestone[]
  priced_in_analysis?: FinancePricedInAnalysis | null
  transmission_layers?: FinanceTransmissionLayer[]
  historical_precedents?: FinanceHistoricalPrecedent[]
  quant_if_then?: FinanceQuantIfThen[]
}

export interface InlineEventImpact {
  event_id: string
  tag: string
  tag_en?: string
  polarity: 'bullish' | 'bearish' | 'divergent'
  validation_status?: 'verified' | 'insufficient_evidence'
  evidence_tier?: string
  evidence_tier_label?: string
  effective_date_label?: string | null
  qualifier_badge?: string | null
  intensity: number
  one_liner: string
  top_a: FinanceImpactBar
  top_us: FinanceImpactBar
  top_hk?: FinanceImpactBar | null
  bars: FinanceImpactBar[]
  if_then: FinanceIfThen[]
  milestones: FinanceMilestone[]
  sample_basis?: FinanceSampleBasis | null
  realized_quotes?: MarketQuoteItem[]
  priced_in_analysis?: FinancePricedInAnalysis | null
  transmission_layers?: FinanceTransmissionLayer[]
  historical_precedents?: FinanceHistoricalPrecedent[]
  quant_if_then?: FinanceQuantIfThen[]
}

export interface FinanceImpactDoc {
  schema_version: string
  generated_at: string
  batch_id: string
  disclaimer: string
  disclaimer_en: string
  quotes_updated_at?: string | null
  index_quotes?: MarketQuoteItem[]
  total_mapped_events: number
  event_impacts: EventMarketImpact[]
  event_impact_map: Record<string, InlineEventImpact>
}

export interface AiClientConfig {
  provider: 'gemini' | 'openai_compat'
  apiKey: string
  model: string
  baseUrl: string
}

export interface PortfolioConfig {
  sectors: string[]
  tickers: string[]
  riskProfile: 'conservative' | 'balanced' | 'aggressive'
}

export interface CrowdPredictionStat {
  prediction_id: string
  vote_count: number
  min_votes: number
  unlocked: boolean
  crowd_avg_pct: number | null
  bull_votes: number | null
  bear_votes: number | null
  user_prob_pct: number | null
  user_reason_tag?: string
  user_early_multiplier?: number
  user_points_awarded?: number
  user_brier_score?: number | null
  reason_breakdown?: {
    counts: Record<string, number>
    bull_top: { tag: string; count: number }[]
    bear_top: { tag: string; count: number }[]
  }
}
