export * from './gbrain'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  mode: string
  session_id: string
  created_at: string
  showDataConfirmation?: boolean
  webSearchResults?: WebSearchResult[]
  toolCalls?: ToolCallRecord[]
  retrievalSource?: string
}

export interface ToolCallRecord {
  name: string
  args: Record<string, unknown>
  result?: unknown
}

export interface WebSearchResult {
  title: string
  url: string
  content: string
  score: number
}

export interface Session {
  session_id: string
  last_message_at: string
  message_count: number
  id?: string
  title?: string
  created_at?: string
  updated_at?: string
}

export interface Diary {
  id: string
  date: string
  content: string
  extracted_summary?: string
  extracted_tags?: string
  location?: string
  weather?: string
  temperature?: string
  humidity?: string
  created_at: string
}

export interface DiaryDateItem {
  id: string
  date: string
}

export interface ProfileFragment {
  id: string
  content: string
  confidence: 'explicit' | 'frequent' | 'implied' | 'inferred'
  evidence: string[]
  frequency: number
  first_seen: string
  last_updated: string
  is_active: boolean
  superseded_by?: string
  change_narrative?: string
  source?: string
}

export interface CharacterTrait {
  trait: string
  weight: number
  evidence: string
}

export interface CharacterSummary {
  traits: CharacterTrait[]
  portrait: string
}

export interface TimelineEvent {
  id: string
  timestamp: string
  event_type: string
  summary: string
  source_type?: string
  source_id?: string
  sentiment?: number
  importance_score: number
  is_milestone: boolean
  is_confirmed?: boolean
  confirmed_at?: string
}

export interface KnowledgeItem {
  id: string
  title: string
  type: string
  summary?: string
  genres?: string[]
  themes?: string[]
  depth_level: number
  creator?: string
  year?: number
  source?: string
}

export interface KnowledgeDetail extends KnowledgeItem {
  detailed_content?: string
  cultural_impact?: string
  review_summary?: string
  similar_works?: string[]
}

export type MediaType = '书籍' | '电影' | '电视剧' | '音乐' | '播客'

export interface MediaImportRequest {
  title: string
  media_type: MediaType
  consumed_date?: string
  rating?: number
  notes?: string
}

export interface MediaImportResponse {
  kb_id: string
  message: string
}

export interface MediaRecord {
  id: string
  title: string
  media_type: MediaType
  consumed_date?: string
  rating?: number
  notes?: string
  created_at: string
}

export type PrivacyTier = 'tier1' | 'tier2' | 'tier3'

export interface ImportBatch {
  id: string
  contact_name: string
  message_count: number
  privacy_tier: PrivacyTier
  created_at: string
}

export interface WechatImportResponse {
  import_batch_id: string
  imported_count: number
}

export interface WechatPrivacyInfo {
  contact_name: string
  privacy_tier: PrivacyTier
  tier2_authorized: boolean
  tier3_authorized: boolean
  tier3_expires_at: string | null
}

export type ChangeType = 'habit_fading' | 'trait_shift' | 'preference_change' | 'decision_pattern'

export interface ProfileChange {
  id: string
  change_type: ChangeType
  description: string
  created_at: string
  contact_name?: string
  is_acknowledged: boolean
}

export interface ContextLabel {
  label: string
  icon: string
}

export interface ConsumptionItem {
  date: string
  merchant: string
  description: string
  amount: number
  category: string
}

export interface QuickNote {
  id: string
  content: string
  edited_at: string
  created_at: string
  processing_status: string
}

export interface ExpenseRecord {
  id: string
  amount: number
  category: string
  description: string
  note: string | null
  expense_date: string
  created_at: string
}

export interface ExpenseStats {
  total_amount: number
  category_breakdown: { category: string; amount: number; count: number; percentage: number }[]
  daily_trend: { date: string; amount: number }[]
}

export interface ConsumptionHabit {
  habit: string
  evidence: string
  category: string
  frequency: string
}

export interface PortraitModule {
  title: string
  content: string
  evidence: string[]
  confidence: 'explicit' | 'frequent' | 'implied' | 'inferred'
  abstraction_level?: string
}

export interface PortraitResult {
  id: string
  modules: PortraitModule[]
  reflection_questions?: string[]
}

export interface PortraitRecord {
  id: string
  portrait_type: 'detailed' | 'deep'
  modules_json: string
  extra_json: string | null
  created_at: string
  is_current: number
  modules: PortraitModule[]
  extra: { reflection_questions?: string[] } | null
}

export interface PortraitVersionItem {
  id: string
  portrait_type: 'detailed' | 'deep'
  created_at: string
  is_current: number
  modules_count: number
}

export interface MonitorDiaryStatus {
  total: number
  processed: number
  pending: number
}

export interface MonitorTimelineStatus {
  total: number
  confirmed: number
  unconfirmed: number
}

export interface MonitorPagesStatus {
  total: number
  compiled: number
  uncompiled: number
}

export interface MonitorPortraitsStatus {
  detailed: number
  deep: number
}

export interface MonitorStatus {
  diaries: MonitorDiaryStatus
  timeline_events: MonitorTimelineStatus
  pages: MonitorPagesStatus
  portraits: MonitorPortraitsStatus
}

export interface MonitorUnconfirmedEvent {
  id: string
  timestamp: string
  summary: string
  event_type: string
  source_type: string
  page_slugs: string[]
  importance_score: number
}

export interface MonitorPending {
  unconfirmed_events: MonitorUnconfirmedEvent[]
}

// Insight Dashboard Types

export interface EmotionSeasonDay {
  date: string
  avg_sentiment: number
  count: number
  dominant_emotion?: string
}


