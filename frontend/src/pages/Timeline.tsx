import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useQueryClient, useQuery } from '@tanstack/react-query'
import { Filter, Star, BarChart3, Smile, Frown, Meh, X, Loader2, Briefcase, Users, Heart, DollarSign, Brain, Trophy, Film, RotateCw, MessageCircle, Target, ShoppingCart, Pin, Lock, Clock } from 'lucide-react'
import PageContainer from '../components/layout/PageContainer'
import PageHeader from '../components/layout/PageHeader'
import { timelineApi } from '../api'
import type { TimelineEvent } from '../types'

const EVENT_TYPE_CSS_CLASS: Record<string, string> = {
  work: 'event-work',
  social: 'event-social',
  health: 'event-health',
  consumption: 'event-finance',
  emotion: 'event-emotion',
  decision: 'event-learning',
  milestone: 'event-achievement',
  media: 'event-entertainment',
  routine: 'event-life_change',
}

const EVENT_ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  work: Briefcase,
  social: Users,
  health: Heart,
  consumption: DollarSign,
  emotion: Smile,
  decision: Brain,
  milestone: Trophy,
  media: Film,
  routine: RotateCw,
}

const EVENT_SUB_EMOJI: Record<string, string[]> = {
  work: ['💼', '📝', '📊', '🖥️', '📞', '📋', '🗓️', '📎', '🗂️', '✍️'],
  social: ['👥', '🤝', '🎉', '☕', '🍽️', '🍻', '💬', '🫂', '👋', '🎊'],
  health: ['💪', '🏃', '🧘', '😴', '🥗', '💊', '🏥', '🚴', '🧠', '❤️‍🩹'],
  consumption: ['💰', '🛒', '💳', '🏠', '🎁', '🛍️', '💸', '🏷️', '📦', '🧾'],
  emotion: ['😊', '😢', '😌', '🥰', '😰', '🤗', '😔', '🥺', '😌', '😔'],
  decision: ['🤔', '💡', '🎯', '⚡', '🔑', '✅', '⚖️', '🧭', '📌', '🪜'],
  milestone: ['🏆', '🎓', '💍', '👶', '🎊', '🥂', '🎖️', '🌟', '🎯', '🎇'],
  media: ['🎬', '📚', '🎵', '🎮', '🎨', '🎧', '📺', '🎭', '📷', '🎤'],
  routine: ['🔄', '🚗', '🍳', '🧹', '📦', '🚌', '🛁', '☀️', '🌙', '🛒'],
}

const EVENT_TYPES = [
  { value: 'work', label: '工作' },
  { value: 'social', label: '社交' },
  { value: 'health', label: '健康' },
  { value: 'consumption', label: '消费' },
  { value: 'emotion', label: '情感' },
  { value: 'decision', label: '决策' },
  { value: 'milestone', label: '里程碑' },
  { value: 'media', label: '媒体' },
  { value: 'routine', label: '日常' },
]

function getSentimentStyle(sentiment?: number | null) {
  if (sentiment == null) return 'text-warm-faint'
  if (sentiment > 0.3) return 'text-green-500'
  if (sentiment < -0.3) return 'text-red-500'
  return 'text-warm-muted'
}

function getSentimentLabel(sentiment?: number | null) {
  if (sentiment == null) return ''
  if (sentiment > 0.3) return '积极'
  if (sentiment < -0.3) return '消极'
  return '中性'
}

const getEventEmoji = (eventType: string, summary: string, sentiment?: number | null): string => {
  // Define sentiment-based emoji groups
  const positiveEmojis = ['😊', '🎉', '🌟', '✨', '💪', '❤️', '🥰', '😄', '👏', '🎊']
  const neutralEmojis = ['📝', '📋', '📌', '📎', '🗂️', '📄', '📊', '💼', '🗓️', '✍️']
  const negativeEmojis = ['😢', '😔', '😰', '🥺', '😞', '😩', '💔', '😟', '😣', '😥']

  let pool: string[]
  if (sentiment != null && sentiment > 0.3) {
    pool = positiveEmojis
  } else if (sentiment != null && sentiment < -0.3) {
    pool = negativeEmojis
  } else {
    // Neutral or null sentiment: use event-type-specific neutral emojis
    const typeEmojis = EVENT_SUB_EMOJI[eventType]
    if (typeEmojis && typeEmojis.length > 0) {
      // Filter out clearly negative emojis from type-specific list
      const negativeSet = new Set(['😤', '😢', '😰', '🥺', '😩', '💔'])
      const filtered = typeEmojis.filter(e => !negativeSet.has(e))
      pool = filtered.length > 0 ? filtered : neutralEmojis
    } else {
      pool = neutralEmojis
    }
  }

  // Use summary hash for consistent but varied selection
  let hash = 0
  for (let i = 0; i < summary.length; i++) {
    hash = ((hash << 5) - hash) + summary.charCodeAt(i)
    hash |= 0
  }
  return pool[Math.abs(hash) % pool.length]
}

/** Extract YYYY-MM-DD from timestamp, falling back to raw string. Never returns Invalid Date. */
function toISODate(ts: string): string {
  if (!ts) return ''
  const m = ts.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  // Try to extract any date-like pattern
  const m2 = ts.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (m2) return `${m2[1]}-${m2[2].padStart(2, '0')}-${m2[3].padStart(2, '0')}`
  // Return first 10 chars if they look like a date, otherwise empty
  const prefix = ts.slice(0, 10)
  if (/^\d{4}-\d{2}-\d{2}$/.test(prefix)) return prefix
  return ''
}

/** Format as M.D (e.g. "6.6") */
function formatMonthDay(dateStr: string): string {
  const m = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (m) return `${parseInt(m[2])}.${parseInt(m[3])}`
  return dateStr
}

/** Extract year from YYYY-MM-DD */
function toYear(dateStr: string): string {
  const m = dateStr.match(/^(\d{4})/)
  return m ? m[1] : ''
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const EVENT_ICONS_NO_TEXT: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  milestone: Trophy,
  emotion: MessageCircle,
  social: Users,
  work: Briefcase,
  decision: Target,
  health: Heart,
  consumption: ShoppingCart,
  media: Film,
  other: Pin,
}

export default function Timeline() {
  const [selectedTypes, setSelectedTypes] = useState<string[]>([])
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [minImportance, setMinImportance] = useState(0)
  const [showFilters, setShowFilters] = useState(false)
  const [sentimentFilter, setSentimentFilter] = useState<string | null>(null)

  const PAGE_SIZE = 50

  const {
    data,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['timeline', selectedTypes, startDate, endDate, minImportance],
    queryFn: async ({ pageParam = 0 }) => {
      const params: Record<string, unknown> = { limit: PAGE_SIZE, offset: pageParam }
      if (selectedTypes.length === 1) params.event_type = selectedTypes[0]
      if (startDate) params.start_date = startDate
      if (endDate) params.end_date = endDate
      if (minImportance > 0) params.min_importance = minImportance
      const res = await timelineApi.getEvents(params as Parameters<typeof timelineApi.getEvents>[0])
      return res.data
    },
    getNextPageParam: (lastPage, allPages) => {
      if (!lastPage || lastPage.length < PAGE_SIZE) return undefined
      return allPages.length * PAGE_SIZE
    },
    initialPageParam: 0,
  })

  const events = useMemo(() => data?.pages.flat() ?? [], [data])

  // IntersectionObserver for infinite scroll
  const loadMoreRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { threshold: 0.1, rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Auto-fetch if content is short and there are more pages
  useEffect(() => {
    if (hasNextPage && !isFetchingNextPage && !isLoading && events.length > 0) {
      const container = document.querySelector('.timeline-scroll-container')
      if (container && container.scrollHeight <= container.clientHeight + 100) {
        fetchNextPage()
      }
    }
  }, [hasNextPage, isFetchingNextPage, isLoading, events.length, fetchNextPage])

  const toggleType = useCallback((type: string) => {
    setSelectedTypes(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    )
  }, [])

  const clearFilters = () => {
    setSelectedTypes([])
    setStartDate('')
    setEndDate('')
    setMinImportance(0)
    setSentimentFilter(null)
  }

  const hasActiveFilters = selectedTypes.length > 0 || startDate || endDate || minImportance > 0 || sentimentFilter !== null

  const filteredEvents = (() => {
    let result = selectedTypes.length > 1
      ? events.filter(e => selectedTypes.includes(e.event_type))
      : events
    if (sentimentFilter) {
      result = result.filter(e => {
        const s = e.sentiment
        if (sentimentFilter === 'positive') return s != null && s > 0.3
        if (sentimentFilter === 'neutral') return s != null && s >= -0.3 && s <= 0.3
        if (sentimentFilter === 'negative') return s != null && s < -0.3
        return true
      })
    }
    return result
  })()

  const groupedEvents = groupByYearAndDate(filteredEvents)

  // Fetch overview stats from backend (all events, not just loaded ones)
  const { data: overviewData } = useQuery({
    queryKey: ['timeline-overview-stats'],
    queryFn: async () => {
      const res = await timelineApi.getOverviewStats()
      return res.data
    },
    staleTime: 30000,
  })

  const statsSummary = useMemo(() => {
    if (!overviewData) {
      return { typeData: EVENT_TYPES.map(t => ({ ...t, count: 0 })), maxTypeCount: 1, posCount: 0, negCount: 0, neutralCount: 0, noSentiment: 0, sentimentTotal: 0 }
    }

    const typeData = EVENT_TYPES.map(t => ({
      ...t,
      count: overviewData.type_counts[t.value] || 0,
    })).sort((a, b) => b.count - a.count)

    const maxTypeCount = Math.max(...typeData.map(t => t.count), 1)
    const { pos_count, neg_count, neutral_count, no_sentiment } = overviewData.sentiment
    const sentimentTotal = pos_count + neg_count + neutral_count + no_sentiment

    return { typeData, maxTypeCount, posCount: pos_count, negCount: neg_count, neutralCount: neutral_count, noSentiment: no_sentiment, sentimentTotal }
  }, [overviewData])

  return (
    <PageContainer className="h-full flex flex-col !p-0 !max-w-none">
      {/* 顶部筛选栏 */}
      <div className="bg-warm-bg/50 shrink-0">
        <div className="flex items-center gap-3 px-6 py-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-sm transition-all duration-200 btn-press ${
              hasActiveFilters
                ? 'bg-warm-accent/20 text-warm-accent border border-warm-accent/30 shadow-sm shadow-warm-shadow'
                : 'bg-warm-input text-warm-text hover:bg-warm-accent-hover/20 border border-warm-border/50'
            }`}
          >
            <Filter size={14} />
            筛选
            {hasActiveFilters && (
              <span className="w-4 h-4 flex items-center justify-center rounded-full bg-warm-accent text-white text-[10px] font-medium">
                {selectedTypes.length || ''}
              </span>
            )}
          </button>

          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="text-xs text-warm-muted hover:text-warm-accent transition-colors btn-press"
            >
              清除筛选
            </button>
          )}

          <span className="ml-auto text-xs text-warm-faint">
            已加载 {filteredEvents.length} 个事件
          </span>
        </div>

        {showFilters && (
          <div className="px-6 pb-3 space-y-3 mt-2 pt-2 animate-fade-in">
            {/* 事件类型 */}
            <div>
              <label className="text-xs text-warm-muted mb-1.5 block font-medium">事件类型</label>
              <div className="flex flex-wrap gap-1.5">
                {EVENT_TYPES.map(type => (
                  <button
                    key={type.value}
                    onClick={() => toggleType(type.value)}
                    className={`px-2.5 py-1 rounded-lg text-xs transition-all duration-200 btn-press ${
                      selectedTypes.includes(type.value)
                        ? `bg-warm-accent/25 text-warm-accent-deep border border-warm-accent/40 shadow-sm shadow-warm-shadow ${EVENT_TYPE_CSS_CLASS[type.value] || ''}`
                        : 'bg-warm-input text-warm-muted hover:bg-warm-overlay border border-warm-border/40'
                    }`}
                  >
                    {EVENT_SUB_EMOJI[type.value]?.[0] || ''} {type.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 情感倾向 */}
            <div>
              <label className="text-xs text-warm-muted mb-1.5 block font-medium">情感倾向</label>
              <div className="flex items-center gap-1.5">
                {[
                  { value: 'positive', label: '积极', emoji: '😊' },
                  { value: 'neutral', label: '中性', emoji: '😐' },
                  { value: 'negative', label: '消极', emoji: '😢' },
                ].map(s => (
                  <button
                    key={s.value}
                    onClick={() => {
                      setSentimentFilter(prev => prev === s.value ? null : s.value)
                    }}
                    className={`px-2.5 py-1 rounded-lg text-xs transition-all duration-200 btn-press ${
                      sentimentFilter === s.value
                        ? 'bg-warm-accent/25 text-warm-accent-deep border border-warm-accent/40 shadow-sm shadow-warm-shadow'
                        : 'bg-warm-input text-warm-muted hover:bg-warm-overlay border border-warm-border/40'
                    }`}
                  >
                    {s.emoji} {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 日期范围 */}
            <div>
              <label className="text-xs text-warm-muted mb-1.5 block font-medium">日期范围</label>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  className="px-3 py-1.5 rounded-xl bg-warm-input border border-warm-border/50 text-sm text-warm-text focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all focus-ring-enhanced"
                />
                <span className="text-warm-faint text-sm">至</span>
                <input
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className="px-3 py-1.5 rounded-xl bg-warm-input border border-warm-border/50 text-sm text-warm-text focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all focus-ring-enhanced"
                />
              </div>
            </div>

            {/* 重要性滑块 */}
            <div>
              <label className="text-xs text-warm-muted mb-1.5 block font-medium">
                最低重要性: {minImportance.toFixed(1)}
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={minImportance}
                onChange={e => setMinImportance(parseFloat(e.target.value))}
                className="w-full accent-warm-accent"
              />
            </div>
          </div>
        )}
      </div>

      {/* 时间线主体 */}
      <div className="flex-1 overflow-y-auto timeline-scroll-container">
        {overviewData && overviewData.total > 0 && (
          <TimelineStats stats={statsSummary} totalEvents={overviewData.total} />
        )}
        {isLoading ? (
          <div className="flex items-center justify-center h-full text-warm-faint">
            加载中...
          </div>
        ) : filteredEvents.length === 0 ? (
          <div className="flex items-center justify-center h-full text-warm-faint empty-state">
            <div className="text-center">
              <Clock size={36} className="mx-auto mb-3 text-warm-faint/50" />
              <p className="text-lg mb-2">暂无时间线事件</p>
              <p className="text-sm">开始记录日记后，事件将自动出现在这里</p>
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto p-6">
            {groupedEvents.map(({ year, dateGroups }) => (
              <div key={year} className="mb-8">
                {/* Year marker */}
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-3 h-3 rounded-full bg-gradient-to-br from-warm-accent to-warm-accent-deep shadow-sm shadow-warm-accent/30" />
                  <h3 className="text-lg font-bold font-heading text-warm-accent tracking-wide">{year}</h3>
                  <div className="flex-1 h-px bg-gradient-to-r from-warm-border/60 to-transparent" />
                </div>

                {dateGroups.map(({ dateStr, events: dateEvents }) => (
                  <div key={dateStr} className="mb-4">
                    {/* Month.Day header */}
                    <div className="flex items-center gap-2 mb-2 ml-5">
                      <span className="text-xs font-heading font-semibold text-warm-accent-deep/70 tabular-nums">{formatMonthDay(dateStr)}</span>
                      <div className="flex-1 h-px bg-warm-input" />
                    </div>

                    <div className="space-y-3 ml-1 stagger-enter">
                      {dateEvents.map(event => (
                        <EventCard key={event.id} event={event} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ))}

            {/* Infinite scroll sentinel */}
            <div ref={loadMoreRef} className="h-1" />
            {isFetchingNextPage && (
              <div className="flex items-center justify-center py-4 text-warm-faint text-sm">
                <Loader2 size={14} className="animate-spin mr-2" />
                加载更多...
              </div>
            )}
            {!hasNextPage && filteredEvents.length > 0 && (
              <div className="text-center py-6 text-warm-faint text-xs">
                — 已加载全部时间线 —
              </div>
            )}
          </div>
        )}
      </div>
    </PageContainer>
  )
}

function EventCard({ event }: { event: TimelineEvent }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [confirmed, setConfirmed] = useState(event.is_confirmed ?? false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [editSummary, setEditSummary] = useState(event.summary || '')
  const [editContent, setEditContent] = useState((event as any).content || '')
  const [editEventType, setEditEventType] = useState(event.event_type || 'routine')
  const [editTimestamp, setEditTimestamp] = useState('')
  const [editImportance, setEditImportance] = useState(event.importance_score ?? 0.5)
  const [saving, setSaving] = useState(false)
  const isMilestone = event.is_milestone
  const sentimentStyle = getSentimentStyle(event.sentiment)
  const sentimentLabel = getSentimentLabel(event.sentiment)
  const canNavigate = event.source_type === 'diary' || event.source_type === 'chat'

  const SOURCE_LABELS: Record<string, string> = {
    diary: '日记',
    chat: '对话',
    media: '媒体',
    import: '导入',
    external: '外部',
    graph: '图谱',
  }

  function isEventLocked(): boolean {
    if (confirmed) return true
    if (!event.timestamp) return false
    try {
      const entryDate = new Date(event.timestamp)
      const now = new Date()
      const hoursDiff = (now.getTime() - entryDate.getTime()) / (1000 * 60 * 60)
      return hoursDiff > 24
    } catch {
      return false
    }
  }

  const locked = isEventLocked()

  const handleConfirm = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      const { timelineApi } = await import('../api')
      await timelineApi.confirmEvent(event.id)
      setConfirmed(true)
    } catch {
      // ignore
    }
  }

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation()
    // Extract date from timestamp for the date input
    const dateStr = toISODate(event.timestamp)
    setEditTimestamp(dateStr)
    setEditSummary(event.summary || '')
    setEditContent((event as any).content || '')
    setEditEventType(event.event_type || 'routine')
    setEditImportance(event.importance_score ?? 0.5)
    setShowEditModal(true)
  }

  const handleSaveEdit = async () => {
    setSaving(true)
    try {
      await timelineApi.updateEvent(event.id, {
        summary: editSummary,
        content: editContent,
        event_type: editEventType,
        timestamp: editTimestamp,
        importance_score: editImportance,
      })
      setShowEditModal(false)
      queryClient.invalidateQueries({ queryKey: ['timeline'] })
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div
        className={`relative pl-8 group ${
          isMilestone ? '' : ''
        }`}
      >
        {/* 时间线节点 */}
        <div className={`absolute left-0 top-3.5 w-4 h-4 rounded-full flex items-center justify-center text-[8px] transition-all duration-300 ${EVENT_TYPE_CSS_CLASS[event.event_type] || ''} ${
          isMilestone
            ? 'bg-yellow-400/25 border-2 border-yellow-400 shadow-sm shadow-yellow-400/20'
            : 'bg-warm-input border-2 border-warm-border group-hover:border-warm-accent group-hover:shadow-sm group-hover:shadow-warm-accent/20'
        }`}>
          <span className="text-[8px]">{getEventEmoji(event.event_type, event.summary, event.sentiment)}</span>
        </div>

        {/* 连接线 */}
        <div className="absolute left-[7px] top-8 bottom-0 w-px bg-gradient-to-b from-warm-border to-transparent group-last:hidden" />

        {/* 事件卡片 */}
        <div
          className={`rounded-2xl p-4 transition-all duration-200 card-interactive ${
            canNavigate ? 'cursor-pointer' : ''
          } ${
            isMilestone
              ? 'bg-gradient-to-br from-yellow-50/80 to-warm-card border border-yellow-300/40 shadow-sm shadow-yellow-200/30'
              : 'bg-warm-card/80 backdrop-blur-sm border border-warm-border/60 hover:border-warm-accent/30'
          }`}
          onClick={() => {
            if (!canNavigate) return
            if (event.source_type === 'diary') {
              navigate(`/diary?id=${event.source_id}`)
            } else if (event.source_type === 'chat') {
              navigate('/')
            }
          }}
        >
          <div className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                {isMilestone && (
                  <span className="flex items-center gap-1 text-xs text-yellow-600">
                    <Star size={10} fill="currentColor" />
                    里程碑
                  </span>
                )}
              </div>

              <p className="text-sm text-warm-text leading-relaxed">
                {getEventEmoji(event.event_type, event.summary, event.sentiment)} {event.summary}
              </p>

              <div className="flex items-center gap-3 mt-2">
                {event.sentiment != null && (
                  <span className={`text-xs ${sentimentStyle}`}>
                    {sentimentLabel} ({event.sentiment.toFixed(2)})
                  </span>
                )}
                <span className="text-xs text-warm-faint flex items-center gap-1">
                  <Star size={10} />
                  {event.importance_score.toFixed(1)}
                </span>
                {event.source_type && (
                  <span className={`text-xs ${canNavigate ? 'text-warm-accent' : 'text-warm-faint'}`}>
                    {SOURCE_LABELS[event.source_type] || event.source_type}{canNavigate ? ' →' : ''}
                  </span>
                )}
                {locked && (
                  <span className="text-xs" title="已锁定"><Lock size={12} /></span>
                )}
              </div>
              {!locked && (
                <div className="flex items-center gap-2 mt-2">
                  <button
                    onClick={handleConfirm}
                    className="px-2 py-0.5 text-xs bg-warm-accent hover:bg-warm-accent-hover text-white rounded transition-colors btn-primary"
                  >
                    确认
                  </button>
                  <button
                    onClick={handleEdit}
                    className="px-2 py-0.5 text-xs bg-warm-input text-warm-muted rounded hover:text-warm-text transition-colors"
                  >
                    编辑
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Edit Modal */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setShowEditModal(false)}>
          <div className="bg-warm-card border border-warm-border rounded-xl shadow-xl w-[520px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-warm-border flex items-center justify-between">
              <h3 className="text-sm font-semibold text-warm-text">编辑时间线事件</h3>
              <button
                onClick={() => setShowEditModal(false)}
                className="text-warm-faint hover:text-warm-muted transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-xs text-warm-muted mb-1">日期</label>
                <input
                  type="date"
                  value={editTimestamp}
                  onChange={e => setEditTimestamp(e.target.value)}
                  className="w-full bg-warm-input border border-warm-border rounded-lg px-3 py-2 text-sm text-warm-text focus:outline-none focus:ring-2 focus:ring-warm-accent/20 focus:border-warm-accent"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">事件类型</label>
                <select
                  value={editEventType}
                  onChange={e => setEditEventType(e.target.value)}
                  className="w-full bg-warm-input border border-warm-border rounded-lg px-3 py-2 text-sm text-warm-text focus:outline-none focus:ring-2 focus:ring-warm-accent/20 focus:border-warm-accent"
                >
                  {EVENT_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">摘要</label>
                <textarea
                  value={editSummary}
                  onChange={e => setEditSummary(e.target.value)}
                  rows={3}
                  className="w-full bg-warm-input border border-warm-border rounded-lg px-3 py-2 text-sm text-warm-text placeholder-warm-faint focus:outline-none focus:ring-2 focus:ring-warm-accent/20 focus:border-warm-accent resize-none focus-ring-enhanced"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">详细内容</label>
                <textarea
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  rows={4}
                  className="w-full bg-warm-input border border-warm-border rounded-lg px-3 py-2 text-sm text-warm-text placeholder-warm-faint focus:outline-none focus:ring-2 focus:ring-warm-accent/20 focus:border-warm-accent resize-none focus-ring-enhanced"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">重要性: {editImportance.toFixed(1)}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={editImportance}
                  onChange={e => setEditImportance(parseFloat(e.target.value))}
                  className="w-full accent-warm-accent"
                />
              </div>
            </div>
            <div className="p-4 border-t border-warm-border flex justify-end gap-2">
              <button
                onClick={() => setShowEditModal(false)}
                className="px-4 py-2 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={saving}
                className="px-4 py-2 text-xs bg-warm-accent hover:bg-warm-accent-hover text-white rounded-lg disabled:opacity-50 transition-colors btn-primary"
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function groupByYearAndDate(events: TimelineEvent[]) {
  // Group: year -> [{ dateStr, events }]
  const yearMap = new Map<string, { dateStr: string; events: TimelineEvent[] }[]>()

  // First group by date, skip events with no valid date
  const dateMap = new Map<string, TimelineEvent[]>()
  for (const e of events) {
    const dateStr = toISODate(e.timestamp)
    if (!dateStr) continue // Skip events with invalid/empty date
    const list = dateMap.get(dateStr) || []
    list.push(e)
    dateMap.set(dateStr, list)
  }

  // Sort dates and organize by year
  const sortedDates = Array.from(dateMap.keys()).sort().reverse()
  for (const dateStr of sortedDates) {
    const year = toYear(dateStr) || '未知'
    if (!yearMap.has(year)) yearMap.set(year, [])
    yearMap.get(year)!.push({ dateStr, events: dateMap.get(dateStr)! })
  }

  return Array.from(yearMap.entries()).map(([year, dateGroups]) => ({ year, dateGroups }))
}

function TimelineStats({
  stats,
  totalEvents,
}: {
  stats: {
    typeData: { value: string; label: string; count: number }[]
    maxTypeCount: number
    posCount: number
    negCount: number
    neutralCount: number
    noSentiment: number
    sentimentTotal: number
  }
  totalEvents: number
}) {
  return (
    <div className="max-w-3xl mx-auto px-6 pt-4 pb-2 animate-fade-in">
      <div className="rounded-2xl bg-warm-card/80 backdrop-blur-sm border border-warm-border/50 p-5 shadow-sm shadow-warm-shadow surface-raised">
        <h3 className="flex items-center gap-2 text-sm font-heading font-semibold text-warm-text mb-4">
          <div className="w-6 h-6 rounded-lg bg-warm-accent/15 flex items-center justify-center">
            <BarChart3 size={14} className="text-warm-accent" />
          </div>
          统计概览
          <span className="text-xs font-normal text-warm-faint ml-1">{totalEvents} 个事件</span>
        </h3>

        <div className="grid grid-cols-2 gap-5">
          {/* 事件类型分布 */}
          <div className="space-y-2">
            <span className="text-[11px] text-warm-muted font-medium uppercase tracking-wider">事件类型</span>
            {stats.typeData.filter(t => t.count > 0).map(t => (
              <div key={t.value} className="flex items-center gap-2 text-xs group/type">
                <span className="w-5 flex items-center justify-center shrink-0 text-sm">{EVENT_SUB_EMOJI[t.value]?.[0] || ''}</span>
                <span className="text-warm-text w-10 shrink-0 font-medium">{t.label}</span>
                <div className="flex-1 h-1.5 rounded-full bg-warm-border/20 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700 ease-out stat-bar"
                    style={{
                      width: `${Math.round((t.count / stats.maxTypeCount) * 100)}%`,
                      backgroundColor: t.value === 'milestone' ? '#fbbf24' :
                        t.value === 'emotion' ? '#f472b6' :
                        t.value === 'social' ? '#60a5fa' :
                        t.value === 'work' ? '#a78bfa' :
                        t.value === 'decision' ? '#f97316' :
                        t.value === 'health' ? '#4ade80' :
                        t.value === 'consumption' ? '#facc15' :
                        t.value === 'media' ? '#2dd4bf' : '#9ca3af',
                      minWidth: t.count > 0 ? '4px' : '0',
                    }}
                  />
                </div>
                <span className="text-warm-faint w-5 text-right shrink-0 tabular-nums">{t.count}</span>
              </div>
            ))}
          </div>

          {/* 情感分布 */}
          <div className="space-y-2">
            <span className="text-[11px] text-warm-muted font-medium uppercase tracking-wider">情感倾向</span>
            {stats.sentimentTotal > 0 && (
              <>
                <div className="flex items-center gap-2 text-xs">
                  <Smile size={13} className="text-green-500 shrink-0" />
                  <span className="text-warm-text w-8 shrink-0 font-medium">积极</span>
                  <div className="flex-1 h-1.5 rounded-full bg-warm-border/20 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-green-400/60 transition-all duration-700 ease-out stat-bar"
                      style={{
                        width: `${Math.round((stats.posCount / stats.sentimentTotal) * 100)}%`,
                        minWidth: stats.posCount > 0 ? '4px' : '0',
                      }}
                    />
                  </div>
                  <span className="text-warm-faint w-5 text-right shrink-0 tabular-nums">{stats.posCount}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Meh size={13} className="text-warm-muted shrink-0" />
                  <span className="text-warm-text w-8 shrink-0 font-medium">中性</span>
                  <div className="flex-1 h-1.5 rounded-full bg-warm-border/20 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gray-400/40 transition-all duration-700 ease-out stat-bar"
                      style={{
                        width: `${Math.round((stats.neutralCount / stats.sentimentTotal) * 100)}%`,
                        minWidth: stats.neutralCount > 0 ? '4px' : '0',
                      }}
                    />
                  </div>
                  <span className="text-warm-faint w-5 text-right shrink-0 tabular-nums">{stats.neutralCount}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Frown size={13} className="text-red-400 shrink-0" />
                  <span className="text-warm-text w-8 shrink-0 font-medium">消极</span>
                  <div className="flex-1 h-1.5 rounded-full bg-warm-border/20 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-red-400/40 transition-all duration-700 ease-out stat-bar"
                      style={{
                        width: `${Math.round((stats.negCount / stats.sentimentTotal) * 100)}%`,
                        minWidth: stats.negCount > 0 ? '4px' : '0',
                      }}
                    />
                  </div>
                  <span className="text-warm-faint w-5 text-right shrink-0 tabular-nums">{stats.negCount}</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
