export type PageType = 'person' | 'concept' | 'self' | 'company' | 'project' | 'meeting' | 'media' | 'source' | 'system' | 'habit' | 'emotion_pattern' | 'value_signal' | 'place'

export const PAGE_TYPE_LABELS: Record<PageType, string> = {
  person: '人物',
  concept: '概念',
  self: '自我',
  company: '组织',
  project: '项目',
  meeting: '会议',
  media: '书影音',
  source: '来源',
  system: '系统',
  habit: '习惯',
  emotion_pattern: '情绪模式',
  value_signal: '价值观',
  place: '地点',
}

export interface TimelineEntry {
  id?: string
  timestamp: string
  content: string
  summary?: string
  source_type: string
  source_id: string
  event_type?: string
  sentiment?: number
  importance_score?: number
  is_milestone?: boolean
  is_confirmed?: boolean
  confirmed_at?: string
}

export interface PageLink {
  slug: string
  title: string
  type: PageType
  link_type: string
}

export interface PageListItem {
  slug: string
  type: PageType
  title: string
  tags: string[]
  updated_at: string
  created_at: string
}

export interface PageDetail {
  slug: string
  type: PageType
  title: string
  frontmatter: Record<string, unknown>
  compiled_truth: string
  summary: string
  aliases: string[]
  timeline: TimelineEntry[]
  tags: string[]
  forward_links: PageLink[]
  back_links: PageLink[]
  version_count: number
  created_at: string
  updated_at: string
}

export interface PageUpdateRequest {
  compiled_truth?: string
  timeline_append?: TimelineEntry[]
  frontmatter?: Record<string, unknown>
  title?: string
}

export interface SearchResult {
  slug: string
  title: string
  type: PageType
  snippet: string
  score: number
  source?: string
  highlight?: string
  summary?: string
}

export type SearchMode = 'conservative' | 'balanced' | 'tokenmax'

export const SEARCH_MODE_LABELS: Record<SearchMode, string> = {
  conservative: '保守',
  balanced: '平衡',
  tokenmax: '全力',
}

export const SEARCH_MODE_DESC: Record<SearchMode, string> = {
  conservative: '仅关键词，最快',
  balanced: '全文搜索+重排',
  tokenmax: 'AI改写+深度搜索',
}

export interface SearchRequestV2 {
  query: string
  mode?: SearchMode
  limit?: number
  sources?: string[]
  rerank?: boolean
  graph?: boolean
}

export interface HealthReport {
  total_pages: number
  orphan_pages: string[]
  stale_pages: string[]
  inconsistencies: string[]
  suggestions: string[]
}

export interface StatsResponse {
  total_pages: number
  pages_by_type: Record<string, number>
  total_signals: number
  unprocessed_signals: number
  total_versions: number
}

export interface IngestRequest {
  directory: string
}

export interface CompileRequest {
  entity_tag: string
}

export interface GraphNode {
  id: number
  slug: string
  title: string
  type: PageType
}

export interface GraphEdge {
  source: string
  target: string
  link_type: string
  confidence: string
}

export interface BacklinkEntry {
  source_slug: string
  source_title: string
  source_type: string
  link_type: string
  confidence: string
}

export interface KnowledgeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}