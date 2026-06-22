import { useState, useCallback, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Loader2, User, Lightbulb, Heart, Building2,
  FolderKanban, Calendar, BookOpen, FileText, Settings,
  Clock, Upload, Activity, BarChart3, AlertCircle,
  Merge, CheckSquare, X, Pencil,
  Briefcase, Users, Wallet, Smile, HelpCircle, Trophy, Film, RefreshCw, MapPin, Lock, Trash2,
} from 'lucide-react'
import { gbrainApi } from '../api'
import { PAGE_TYPE_LABELS } from '../types'
import type { PageType, PageListItem, PageDetail, SearchResult, TimelineEntry, PageLink, StatsResponse, HealthReport, GraphNode, GraphEdge } from '../types'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

const ALL_TYPES: { key: PageType | ''; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'person', label: '人物' },
  { key: 'concept', label: '概念' },
  { key: 'self', label: '自我' },
  { key: 'company', label: '组织' },
  { key: 'project', label: '项目' },
  { key: 'meeting', label: '会议' },
  { key: 'media', label: '书影音' },
  { key: 'source', label: '来源' },
  { key: 'system', label: '系统' },
  { key: 'habit', label: '习惯' },
  { key: 'emotion_pattern', label: '情绪模式' },
  { key: 'value_signal', label: '价值观' },
  { key: 'place', label: '地点' },
]

const TYPE_ICONS: Record<string, typeof User> = {
  person: User,
  concept: Lightbulb,
  self: Heart,
  company: Building2,
  project: FolderKanban,
  meeting: Calendar,
  media: BookOpen,
  source: FileText,
  system: Settings,
  habit: Activity,
  emotion_pattern: Heart,
  value_signal: Lightbulb,
  place: BarChart3,
}

const SOURCE_LABELS: Record<string, string> = {
  diary: '日记',
  chat: '对话',
  media: '媒体',
  import: '导入',
  external: '外部',
  graph: '图谱',
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  // Try regex-based extraction first to avoid Invalid Date
  const m = dateStr.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  // Fallback: try Date parse
  try {
    const d = new Date(dateStr)
    if (!isNaN(d.getTime())) return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    // ignore
  }
  return dateStr.slice(0, 10)
}

function renderWikiText(text: string, onNavigate: (slug: string) => void) {
  const parts = text.split(/(\[\[.+?\]\])/g)
  return parts.map((part, i) => {
    const match = part.match(/^\[\[(.+?)\]\]$/)
    if (match) {
      const slug = match[1].includes(':') ? match[1].split(':')[1] : match[1]
      return (
        <button
          key={i}
          onClick={() => onNavigate(slug)}
          className="text-warm-accent hover:text-warm-accent-hover underline underline-offset-2 cursor-pointer transition-colors"
        >
          {match[1]}
        </button>
      )
    }
    return <span key={i}>{part}</span>
  })
}

export default function Knowledge() {
  const navigate = useNavigate()
  const [pages, setPages] = useState<PageListItem[]>([])
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<PageType | ''>('')
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [detail, setDetail] = useState<PageDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [searching, setSearching] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [ingesting, setIngesting] = useState(false)
  const [healthReport, setHealthReport] = useState<HealthReport | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [ingestDir, setIngestDir] = useState('')
  const [showIngestInput, setShowIngestInput] = useState(false)
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list')
  const [hoveredGraphNode, setHoveredGraphNode] = useState<string | null>(null)
  const [typeFilterCollapsed, setTypeFilterCollapsed] = useState(false)
  const [mergeMode, setMergeMode] = useState(false)
  const [selectedMergeSlugs, setSelectedMergeSlugs] = useState<Set<string>>(new Set())
  const [showMergeModal, setShowMergeModal] = useState(false)
  const [mergeTargetSlug, setMergeTargetSlug] = useState<string>('')
  const [merging, setMerging] = useState(false)
  const [mergeSuggestions, setMergeSuggestions] = useState<{ target_slug: string; target_title: string; source_slugs: string[]; source_titles: string[]; reason: string; type: string }[]>([])
  const [ignoredSuggestions, setIgnoredSuggestions] = useState<Set<string>>(new Set())
  const [mergingSuggestion, setMergingSuggestion] = useState<string | null>(null)
  const [mergeUndoInfo, setMergeUndoInfo] = useState<{ snapshotId: string; targetTitle: string; sourceTitles: string[] } | null>(null)
  const [undoing, setUndoing] = useState(false)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; slug: string; title: string } | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [editTimelineEntry, setEditTimelineEntry] = useState<TimelineEntry | null>(null)
  const [editTlSummary, setEditTlSummary] = useState('')
  const [editTlContent, setEditTlContent] = useState('')
  const [editTlEventType, setEditTlEventType] = useState('routine')
  const [editTlTimestamp, setEditTlTimestamp] = useState('')
  const [editTlImportance, setEditTlImportance] = useState(0.5)
  const [editTlSaving, setEditTlSaving] = useState(false)
  const [graphZoom, setGraphZoom] = useState(1)
  const [graphPan, setGraphPan] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 })

  const loadPages = useCallback(async (type?: PageType | '') => {
    setLoading(true)
    setError(null)
    try {
      const params: { type?: string } = {}
      if (type) params.type = type
      const res = await gbrainApi.listPages(params)
      setPages(res.data.items || [])
      setSearchResults(null)
    } catch {
      setError('加载页面列表失败')
      setPages([])
    } finally {
      setLoading(false)
    }
  }, [])

  const handleDeletePage = useCallback(async (slug: string) => {
    setDeleting(true)
    try {
      await gbrainApi.deletePage(slug)
      if (selectedSlug === slug) {
        setSelectedSlug(null)
        setDetail(null)
      }
      await loadPages(typeFilter)
    } catch {
      setError('删除实体失败')
    } finally {
      setDeleting(false)
      setContextMenu(null)
    }
  }, [selectedSlug, loadPages, typeFilter])

  useEffect(() => {
    loadPages()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadMergeSuggestions = useCallback(async () => {
    try {
      const res = await gbrainApi.getMergeSuggestions()
      setMergeSuggestions(res.data.suggestions || [])
    } catch {
      // silently ignore
    }
  }, [])

  useEffect(() => {
    loadMergeSuggestions()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setSearchResults(null)
      loadPages(typeFilter)
      return
    }
    setSearching(true)
    setError(null)
    try {
      const res = await gbrainApi.search(searchQuery.trim(), { mode: 'conservative' })
      setSearchResults(res.data.results || [])
    } catch {
      setError('搜索失败')
    } finally {
      setSearching(false)
    }
  }

  const handleSelectPage = async (slug: string) => {
    setSelectedSlug(slug)
    setDetail(null)
    setDetailError(null)
    setDetailLoading(true)
    try {
      const res = await gbrainApi.getPage(slug)
      setDetail(res.data)
    } catch {
      setDetailError('加载页面详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleTypeFilter = (type: PageType | '') => {
    setTypeFilter(type)
    setSearchQuery('')
    setSearchResults(null)
    loadPages(type)
  }

  const handleIngest = async () => {
    if (ingesting) return
    setIngesting(true)
    try {
      await gbrainApi.ingest(ingestDir || '.')
      setIngestDir('')
      setShowIngestInput(false)
      loadPages(typeFilter)
    } catch {
      setError('导入失败')
    } finally {
      setIngesting(false)
    }
  }

  const handleHealth = async () => {
    try {
      const res = await gbrainApi.health()
      setHealthReport(res.data)
    } catch {
      setError('健康检查失败')
    }
  }

  const handleStats = async () => {
    try {
      const res = await gbrainApi.stats()
      setStats(res.data)
    } catch {
      setError('获取统计失败')
    }
  }

  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)

  const loadGraph = useCallback(async () => {
    setGraphLoading(true)
    try {
      const params: { type?: string; slug?: string; depth?: number } = {}
      if (typeFilter) params.type = typeFilter
      const res = await gbrainApi.getGraph(params)
      setGraphData(res.data as any)
    } catch {
      setGraphData(null)
    } finally {
      setGraphLoading(false)
    }
  }, [typeFilter])

  useEffect(() => {
    if (viewMode === 'graph') {
      loadGraph()
    }
  }, [viewMode, loadGraph])

  const displayedItems: { slug: string; type: PageType; title: string; tags?: string[]; updated_at: string; snippet?: string; highlight?: string; source?: string }[] = useMemo(() => {
    if (searchResults) {
      return searchResults.map(r => ({
        slug: r.slug,
        type: r.type,
        title: r.title,
        updated_at: '',
        snippet: r.snippet,
        highlight: r.highlight,
        source: r.source,
      }))
    }
    return pages
  }, [pages, searchResults])

  const groupedByType = useMemo(() => {
    const groups: Record<string, typeof displayedItems> = {}
    displayedItems.forEach(item => {
      const t = item.type || 'unknown'
      if (!groups[t]) groups[t] = []
      groups[t].push(item)
    })
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
  }, [displayedItems])

  const TYPE_COLORS: Record<string, string> = {
    person: '#E8734A',
    concept: '#5B8DEF',
    self: '#E8A0BF',
    company: '#4CAF50',
    project: '#FF9800',
    meeting: '#9C27B0',
    media: '#00BCD4',
    source: '#795548',
    system: '#607D8B',
    habit: '#FF5722',
    emotion_pattern: '#E91E63',
    value_signal: '#009688',
    place: '#8BC34A',
  }

  const CONFIDENCE_DASH: Record<string, string> = {
    explicit: '',
    frequent: '',
    implied: '6 3',
    inferred: '8 4',
    reference: '4 4',
  }

  const handleGraphWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    setGraphZoom(prev => Math.min(3, Math.max(0.3, prev * delta)))
  }

  const handleGraphMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true)
    setDragStart({ x: e.clientX - graphPan.x, y: e.clientY - graphPan.y })
  }

  const handleGraphMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return
    setGraphPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y })
  }

  const handleGraphMouseUp = () => {
    setIsDragging(false)
  }

  const renderGraphView = () => {
    if (graphLoading) {
      return (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={24} className="animate-spin text-warm-accent" />
          <span className="ml-2 text-warm-muted text-sm">加载图谱...</span>
        </div>
      )
    }
    if (!graphData || graphData.nodes.length === 0) {
      return (
        <div className="text-center py-8 text-warm-faint text-sm">暂无图谱数据</div>
      )
    }

    // Simple force-directed layout using spring simulation
    const W = 700
    const H = 500
    const nodes = graphData.nodes.map((n, i) => ({
      ...n,
      x: W / 2 + Math.cos((2 * Math.PI * i) / graphData.nodes.length) * 150,
      y: H / 2 + Math.sin((2 * Math.PI * i) / graphData.nodes.length) * 150,
      vx: 0,
      vy: 0,
    }))
    const nodeMap = new Map(nodes.map(n => [(n as any).slug, n]))

    // Simple 30-iteration force simulation
    for (let iter = 0; iter < 30; iter++) {
      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x
          const dy = nodes[j].y - nodes[i].y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const force = 800 / (dist * dist)
          const fx = (dx / dist) * force
          const fy = (dy / dist) * force
          nodes[i].vx -= fx
          nodes[i].vy -= fy
          nodes[j].vx += fx
          nodes[j].vy += fy
        }
      }
      // Attraction along edges
      for (const edge of graphData.edges) {
        const src = nodeMap.get(edge.source)
        const tgt = nodeMap.get(edge.target)
        if (!src || !tgt) continue
        const dx = tgt.x - src.x
        const dy = tgt.y - src.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = (dist - 120) * 0.01
        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        src.vx += fx
        src.vy += fy
        tgt.vx -= fx
        tgt.vy -= fy
      }
      // Center gravity
      for (const n of nodes) {
        n.vx += (W / 2 - n.x) * 0.001
        n.vy += (H / 2 - n.y) * 0.001
        n.x += n.vx * 0.5
        n.y += n.vy * 0.5
        n.vx *= 0.6
        n.vy *= 0.6
        // Keep in bounds
        n.x = Math.max(30, Math.min(W - 30, n.x))
        n.y = Math.max(20, Math.min(H - 20, n.y))
      }
    }

    const activeGraphSlug = hoveredGraphNode ?? selectedSlug

    return (
      <div
        className="w-full h-full flex flex-col overflow-hidden cursor-grab active:cursor-grabbing"
        onWheel={handleGraphWheel}
        onMouseDown={handleGraphMouseDown}
        onMouseMove={handleGraphMouseMove}
        onMouseUp={handleGraphMouseUp}
        onMouseLeave={handleGraphMouseUp}
      >
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full flex-1"
          style={{ minHeight: 300, transform: `scale(${graphZoom}) translate(${graphPan.x / graphZoom}px, ${graphPan.y / graphZoom}px)`, transformOrigin: 'center center', transition: isDragging ? 'none' : 'transform 0.1s ease-out' }}
        >
          <defs>
            <radialGradient id="graph-bg-knowledge" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fce4ec" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#fff5f0" stopOpacity="0" />
            </radialGradient>
          </defs>
          <rect x={0} y={0} width={W} height={H} fill="url(#graph-bg-knowledge)" />

          {/* Edges */}
          {graphData.edges.map((edge, i) => {
            const src = nodeMap.get(edge.source)
            const tgt = nodeMap.get(edge.target)
            if (!src || !tgt) return null
            const isActive = activeGraphSlug === edge.source || activeGraphSlug === edge.target
            return (
              <g key={`e-${i}`}>
                <line
                  x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                  stroke={isActive ? '#E8A0BF' : '#D4A5A0'}
                  strokeWidth={isActive ? 2 : 1}
                  strokeDasharray={CONFIDENCE_DASH[edge.confidence] || CONFIDENCE_DASH.reference}
                  opacity={isActive ? 0.8 : 0.4}
                />
                <text
                  x={(src.x + tgt.x) / 2}
                  y={(src.y + tgt.y) / 2 - 5}
                  textAnchor="middle"
                  fill={isActive ? '#C4758B' : '#B8A094'}
                  fontSize="8"
                >
                  {(edge as any).link_type}
                </text>
              </g>
            )
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const color = TYPE_COLORS[node.type] || '#C4A882'
            const isActive = activeGraphSlug === (node as any).slug
            const r = isActive ? 16 : 12
            return (
              <g
                key={(node as any).slug}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => handleSelectPage((node as any).slug)}
                onMouseEnter={() => setHoveredGraphNode((node as any).slug)}
                onMouseLeave={() => setHoveredGraphNode(null)}
                className="cursor-pointer"
              >
                {isActive && (
                  <circle r={r + 5} fill="none" stroke={color} strokeWidth="2" opacity="0.4" />
                )}
                <circle r={r} fill={color + '30'} stroke={color} strokeWidth={isActive ? 2.5 : 1.5} />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="#3D2C2A"
                  fontSize={isActive ? 10 : 8}
                  fontWeight={isActive ? 'bold' : 'normal'}
                >
                  {(node as any).title?.slice(0, 2)}
                </text>
                <text
                  y={r + 12}
                  textAnchor="middle"
                  fill={isActive ? '#C4758B' : '#8B6F64'}
                  fontSize="8"
                >
                  {(node as any).title?.length > 6 ? (node as any).title.slice(0, 6) + '…' : (node as any).title}
                </text>
              </g>
            )
          })}
        </svg>
        <div className="flex items-center justify-between px-3 py-1.5 text-xs text-warm-faint bg-warm-bg/50">
          <span>缩放: {Math.round(graphZoom * 100)}%</span>
          <button
            onClick={() => { setGraphZoom(1); setGraphPan({ x: 0, y: 0 }) }}
            className="px-2 py-0.5 rounded bg-warm-input hover:bg-warm-overlay text-warm-muted hover:text-warm-text transition-colors"
          >
            重置视图
          </button>
        </div>
      </div>
    )
  }

  const renderLeftPanel = () => (
    <div className="w-80 shrink-0 bg-warm-sidebar/60 surface-frosted flex flex-col h-full">
      {/* Merge Suggestions Banner */}
      {mergeSuggestions.filter(s => !ignoredSuggestions.has(`${s.source_slugs[0]}-${s.target_slug}`)).length > 0 && (
        <div className="p-2 border-b border-warm-border bg-amber-50">
          {mergeSuggestions
            .filter(s => !ignoredSuggestions.has(`${s.source_slugs[0]}-${s.target_slug}`))
            .slice(0, 3)
            .map((suggestion) => {
              const suggestionKey = `${suggestion.source_slugs[0]}-${suggestion.target_slug}`
              return (
                <div key={suggestionKey} className="flex items-center gap-1.5 py-1.5 px-2 bg-amber-100/80 rounded-lg mb-1 last:mb-0">
                  <AlertCircle size={14} className="text-amber-600 shrink-0" />
                  <span className="text-xs text-amber-800 flex-1 leading-snug">
                    {suggestion.source_titles[0]} 可能与 {suggestion.target_title} 是同一实体
                  </span>
                  <button
                    onClick={async () => {
                      if (mergingSuggestion) return
                      setMergingSuggestion(suggestionKey)
                      try {
                        const res = await gbrainApi.mergePages(suggestion.target_slug, suggestion.source_slugs)
                        const snapshotId = res.data?.merge_snapshot_id
                        setIgnoredSuggestions(prev => new Set(prev).add(suggestionKey))
                        loadPages(typeFilter)
                        loadMergeSuggestions()
                        if (snapshotId) {
                          setMergeUndoInfo({ snapshotId, targetTitle: suggestion.target_title, sourceTitles: suggestion.source_titles })
                        }
                      } catch {
                        setError('合并失败')
                      } finally {
                        setMergingSuggestion(null)
                      }
                    }}
                    disabled={mergingSuggestion === suggestionKey}
                    className="shrink-0 px-2 py-0.5 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 transition-colors"
                  >
                    {mergingSuggestion === suggestionKey ? <Loader2 size={10} className="animate-spin" /> : '合并'}
                  </button>
                  <button
                    onClick={() => setIgnoredSuggestions(prev => new Set(prev).add(suggestionKey))}
                    className="shrink-0 px-2 py-0.5 text-xs bg-amber-200 text-amber-700 rounded hover:bg-amber-300 transition-colors"
                  >
                    忽略
                  </button>
                </div>
              )
            })}
        </div>
      )}
      <div className="p-3 pb-2 mb-1">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-warm-faint" />
          <input
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="搜索 Wiki 页面..."
            className="w-full input-enhanced !pl-9 !pr-3 !py-2.5"
          />
        </div>

        <div className="mt-2 flex items-center gap-1">
          <button
            onClick={() => setViewMode('list')}
            className={`tab-btn flex-1 text-xs ${viewMode === 'list' ? 'active' : ''}`}
          >
            列表
          </button>
          <button
            onClick={() => setViewMode('graph')}
            className={`tab-btn flex-1 text-xs ${viewMode === 'graph' ? 'active' : ''}`}
          >
            图谱
          </button>
        </div>
      </div>

      <div className="p-2 pb-2 mb-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-warm-muted">类型筛选</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setMergeMode(!mergeMode)
                setSelectedMergeSlugs(new Set())
              }}
              className={`tab-btn text-xs flex items-center gap-1 ${mergeMode ? 'active' : ''}`}
            >
              <Merge size={12} />
              合并
            </button>
            <button
              onClick={() => setTypeFilterCollapsed(!typeFilterCollapsed)}
              className="text-xs text-warm-faint hover:text-warm-muted transition-colors"
            >
              {typeFilterCollapsed ? '展开 ▼' : '收起 ▲'}
            </button>
          </div>
        </div>
        {!typeFilterCollapsed && (
          <div className="flex flex-wrap gap-1">
            {ALL_TYPES.map(t => (
              <button
                key={t.key}
                onClick={() => handleTypeFilter(t.key)}
                className={`tab-btn text-xs ${typeFilter === t.key ? 'active' : ''}`}
              >
                {t.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {viewMode === 'graph' ? (
          renderGraphView()
        ) : loading || searching ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={24} className="animate-spin text-warm-accent" />
            <span className="ml-2 text-warm-muted text-sm">{searching ? '搜索中...' : '加载中...'}</span>
          </div>
        ) : error ? (
          <div className="text-center py-8">
            <AlertCircle size={24} className="mx-auto text-red-400 mb-2" />
            <p className="text-sm text-red-400 mb-2">{error}</p>
            <button
              onClick={() => loadPages(typeFilter)}
              className="px-3 py-1 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors"
            >
              重试
            </button>
          </div>
        ) : displayedItems.length === 0 ? (
          <div className="text-center py-8 text-warm-faint text-sm">
            {searchQuery ? '未找到匹配结果' : '暂无页面'}
          </div>
        ) : (
          <div className="space-y-4">
            {groupedByType.map(([type, items]) => {
              const typeLabel = PAGE_TYPE_LABELS[type as PageType] || type
              const Icon = TYPE_ICONS[type] || BookOpen
              return (
                <div key={type}>
                  <div className="flex items-center gap-1.5 px-1 mb-1.5">
                    <Icon size={14} className="text-warm-muted" />
                    <span className="text-xs font-medium text-warm-muted">{typeLabel}</span>
                    <span className="text-xs text-warm-faint">({items.length})</span>
                  </div>
                  <div className="space-y-0.5">
                    {items.map(item => (
                      <button
                        key={item.slug}
                        onClick={() => {
                          if (mergeMode) {
                            setSelectedMergeSlugs(prev => {
                              const next = new Set(prev)
                              if (next.has(item.slug)) {
                                next.delete(item.slug)
                              } else {
                                next.add(item.slug)
                              }
                              return next
                            })
                          } else {
                            handleSelectPage(item.slug)
                          }
                        }}
                        onContextMenu={(e) => {
                          e.preventDefault()
                          setContextMenu({ x: e.clientX, y: e.clientY, slug: item.slug, title: item.title })
                        }}
                        className={`w-full text-left list-item transition-colors ${
                          mergeMode && selectedMergeSlugs.has(item.slug)
                            ? 'bg-warm-accent/10 border-warm-accent/30'
                            : selectedSlug === item.slug
                            ? 'bg-warm-accent/10 border-warm-accent/30'
                            : ''
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          {mergeMode && (
                            <CheckSquare
                              size={14}
                              className={`mt-0.5 shrink-0 ${
                                selectedMergeSlugs.has(item.slug) ? 'text-warm-accent' : 'text-warm-faint'
                              }`}
                            />
                          )}
                          <Icon size={14} className="text-warm-accent mt-0.5 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-sm text-warm-text truncate">{item.title}</p>
                              {item.source && (
                                <span className="badge text-[10px]">
                                  {SOURCE_LABELS[item.source] || item.source}
                                </span>
                              )}
                            </div>
                            {(item.highlight || item.snippet) && (
                              <p className="text-xs text-warm-faint mt-0.5 line-clamp-2">
                                {item.highlight || item.snippet}
                              </p>
                            )}
                            {item.updated_at && (
                              <div className="flex items-center gap-1 mt-0.5">
                                <Clock size={10} className="text-warm-faint" />
                                <span className="text-xs text-warm-faint">{formatDate(item.updated_at)}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="border-t border-warm-border p-3 space-y-2">
        {stats && (
          <div className="flex items-center gap-2 text-xs text-warm-muted mb-2">
            <span>{stats.total_pages} 页面</span>
            <span>·</span>
            <span>{stats.total_signals} 信号</span>
          </div>
        )}

        {showIngestInput && (
          <div className="flex gap-1.5">
            <input
              value={ingestDir}
              onChange={e => setIngestDir(e.target.value)}
              placeholder="目录路径..."
              className="flex-1 input-enhanced text-xs py-1"
              onKeyDown={e => e.key === 'Enter' && handleIngest()}
            />
            <button
              onClick={handleIngest}
              disabled={ingesting}
              className="btn-primary text-xs px-3 py-1 disabled:opacity-50"
            >
              {ingesting ? <Loader2 size={12} className="animate-spin" /> : '确认'}
            </button>
          </div>
        )}
      </div>

      {healthReport && (
        <div className="border-t border-warm-border p-3 max-h-48 overflow-y-auto">
          <p className="text-xs font-medium text-warm-text mb-2">健康报告</p>
          <div className="space-y-1 text-xs text-warm-muted">
            <p>总页面: {healthReport.total_pages}</p>
            {healthReport.orphan_pages.length > 0 && (
              <p className="text-orange-400">孤立页面: {healthReport.orphan_pages.length}</p>
            )}
            {healthReport.stale_pages.length > 0 && (
              <p className="text-yellow-400">过期页面: {healthReport.stale_pages.length}</p>
            )}
            {healthReport.inconsistencies.length > 0 && (
              <p className="text-red-400">不一致: {healthReport.inconsistencies.length}</p>
            )}
            {healthReport.suggestions.length > 0 && (
              <div>
                <p className="mt-1 font-medium">建议:</p>
                {healthReport.suggestions.slice(0, 3).map((s, i) => (
                  <p key={i} className="text-warm-faint">· {s}</p>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {mergeMode && selectedMergeSlugs.size >= 2 && (
        <div className="border-t border-warm-border p-3 bg-warm-accent/10">
          <div className="flex items-center justify-between">
            <span className="text-xs text-warm-text">已选择 {selectedMergeSlugs.size} 个实体</span>
            <button
              onClick={() => {
                setMergeTargetSlug('')
                setShowMergeModal(true)
              }}
              className="btn-primary text-xs px-3 py-1.5"
            >
              确认合并
            </button>
          </div>
        </div>
      )}

      {showMergeModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-warm-card border border-warm-border rounded-xl shadow-xl w-[420px] max-h-[80vh] overflow-y-auto">
            <div className="p-4 border-b border-warm-border flex items-center justify-between">
              <h3 className="text-sm font-semibold font-heading text-warm-text">合并实体</h3>
              <button
                onClick={() => {
                  setShowMergeModal(false)
                  setMergeTargetSlug('')
                }}
                className="text-warm-faint hover:text-warm-muted transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <p className="text-xs text-warm-muted mb-2">选中的实体</p>
                <div className="space-y-1">
                  {Array.from(selectedMergeSlugs).map(slug => {
                    const item = displayedItems.find(i => i.slug === slug)
                    return (
                      <div key={slug} className="list-item flex items-center gap-2 text-xs">
                        <span className="text-warm-text">{item?.title || slug}</span>
                        <span className={`text-warm-faint type-${item?.type}`}>({PAGE_TYPE_LABELS[item?.type as PageType] || item?.type || '未知'})</span>
                      </div>
                    )
                  })}
                </div>
              </div>
              <div>
                <p className="text-xs text-warm-muted mb-2">选择目标实体（合并到此实体）</p>
                <select
                  value={mergeTargetSlug}
                  onChange={e => setMergeTargetSlug(e.target.value)}
                  className="w-full input-enhanced"
                >
                  <option value="">请选择目标实体</option>
                  {Array.from(selectedMergeSlugs).map(slug => {
                    const item = displayedItems.find(i => i.slug === slug)
                    return (
                      <option key={slug} value={slug}>
                        {item?.title || slug} ({PAGE_TYPE_LABELS[item?.type as PageType] || item?.type || '未知'})
                      </option>
                    )
                  })}
                </select>
              </div>
              {mergeTargetSlug && (
                <div className="bg-warm-input rounded-lg p-3 text-xs text-warm-muted space-y-1">
                  <p>合并预览：</p>
                  <p>· 目标实体：<span className="text-warm-text">{displayedItems.find(i => i.slug === mergeTargetSlug)?.title || mergeTargetSlug}</span></p>
                  <p>· 将合并 {selectedMergeSlugs.size - 1} 个源实体</p>
                  <p>· 源实体的时间线、标签、别名将合并到目标实体</p>
                  <p>· 源实体将被删除</p>
                </div>
              )}
            </div>
            <div className="p-4 border-t border-warm-border flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowMergeModal(false)
                  setMergeTargetSlug('')
                }}
                className="px-4 py-2 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  if (!mergeTargetSlug || merging) return
                  setMerging(true)
                  try {
                    const sourceSlugs = Array.from(selectedMergeSlugs).filter(s => s !== mergeTargetSlug)
                    const res = await gbrainApi.mergePages(mergeTargetSlug, sourceSlugs)
                    const snapshotId = res.data?.merge_snapshot_id
                    const targetTitle = displayedItems.find(i => i.slug === mergeTargetSlug)?.title || mergeTargetSlug
                    const sourceTitles = sourceSlugs.map(s => displayedItems.find(i => i.slug === s)?.title || s)
                    setShowMergeModal(false)
                    setMergeMode(false)
                    setSelectedMergeSlugs(new Set())
                    setMergeTargetSlug('')
                    loadPages(typeFilter)
                    // Show undo toast
                    if (snapshotId) {
                      setMergeUndoInfo({ snapshotId, targetTitle, sourceTitles })
                    }
                  } catch {
                    setError('合并失败')
                  } finally {
                    setMerging(false)
                  }
                }}
                disabled={!mergeTargetSlug || merging}
                className="btn-primary text-xs px-4 py-2 disabled:opacity-50"
              >
                {merging ? <Loader2 size={12} className="animate-spin" /> : '确认合并'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )

  const renderTimeline = (entries: TimelineEntry[]) => {
    if (!entries || entries.length === 0) return null

    // Helper: extract YYYY-MM-DD from timestamp. Never returns Invalid Date.
    function toISODate(ts: string | undefined): string {
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

    function formatMonthDay(dateStr: string): string {
      const m = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/)
      if (m) return `${parseInt(m[2])}.${parseInt(m[3])}`
      return dateStr
    }

    function toYear(dateStr: string): string {
      const m = dateStr.match(/^(\d{4})/)
      return m ? m[1] : ''
    }

    // Group by date first, then organize by year (skip events with no valid date)
    const dateMap = new Map<string, TimelineEntry[]>()
    for (const entry of entries) {
      const dateStr = toISODate(entry.timestamp)
      if (!dateStr) continue // Skip events with invalid/empty date
      const list = dateMap.get(dateStr) || []
      list.push(entry)
      dateMap.set(dateStr, list)
    }

    const yearMap = new Map<string, { dateStr: string; entries: TimelineEntry[] }[]>()
    const sortedDates = Array.from(dateMap.keys()).sort().reverse()
    for (const dateStr of sortedDates) {
      const year = toYear(dateStr) || '未知'
      if (!yearMap.has(year)) yearMap.set(year, [])
      yearMap.get(year)!.push({ dateStr, entries: dateMap.get(dateStr)! })
    }

    const EVENT_ICONS: Record<string, typeof Briefcase> = {
      work: Briefcase, social: Users, health: Heart, consumption: Wallet,
      emotion: Smile, decision: HelpCircle, milestone: Trophy, media: Film, routine: RefreshCw,
    }

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

    function isEntryLocked(entry: TimelineEntry): boolean {
      if (entry.is_confirmed) return true
      if (!entry.timestamp) return false
      try {
        const entryDate = new Date(entry.timestamp)
        const now = new Date()
        const hoursDiff = (now.getTime() - entryDate.getTime()) / (1000 * 60 * 60)
        return hoursDiff > 24
      } catch {
        return false
      }
    }

    return (
      <div className="space-y-4">
        {Array.from(yearMap.entries()).map(([year, dateGroups]) => (
          <div key={year}>
            {/* Year marker */}
            <div className="flex items-center gap-3 mb-3">
              <div className="w-2.5 h-2.5 rounded-full bg-warm-accent" />
              <h3 className="text-base font-semibold font-heading text-warm-text">{year}</h3>
              <div className="flex-1 h-px bg-warm-border" />
            </div>

            {dateGroups.map(({ dateStr, entries: dateEntries }) => (
              <div key={dateStr} className="mb-3">
                {/* Month.Day header */}
                <div className="flex items-center gap-2 mb-2 ml-4">
                  <span className="text-xs font-medium text-warm-muted">{formatMonthDay(dateStr)}</span>
                  <div className="flex-1 h-px bg-warm-input" />
                </div>

                <div className="space-y-2 ml-1">
                  {dateEntries.map((entry) => {
                    const eventType = entry.event_type || 'routine'
                    const EventIcon = EVENT_ICONS[eventType] || MapPin
                    const isMilestone = entry.is_milestone
                    const sentimentStyle = getSentimentStyle(entry.sentiment)
                    const sentimentLabel = getSentimentLabel(entry.sentiment)
                    const displayText = entry.content || entry.summary
                    const evidenceText = entry.content
                    const summaryText = entry.summary
                    const hasEvidence = evidenceText && summaryText && evidenceText !== summaryText
                    const sourceLabel = entry.source_type ? (SOURCE_LABELS[entry.source_type] || entry.source_type) : ''
                    const canNavigate = entry.source_type === 'diary' || entry.source_type === 'chat'
                    const locked = isEntryLocked(entry)
                    return (
                      <div key={entry.id || entry.timestamp + entry.content} className="relative pl-7 group">
                        <div className={`absolute left-0 top-3 w-4 h-4 rounded-full flex items-center justify-center text-[8px] ${
                          isMilestone
                            ? 'bg-yellow-400/20 border-2 border-yellow-400'
                            : 'bg-warm-input border-2 border-warm-border group-hover:border-warm-accent'
                        } transition-colors`}>
                          <EventIcon size={8} />
                        </div>
                        <div
                          className={`section-card transition-all ${
                            canNavigate ? 'cursor-pointer hover:shadow-md' : ''
                          } ${
                            isMilestone
                              ? 'border-yellow-400/50 hover:border-yellow-300'
                              : ''
                          }`}
                          onClick={() => {
                            if (!canNavigate) return
                            if (entry.source_type === 'diary') {
                              navigate(`/diary?id=${entry.source_id}`)
                            } else if (entry.source_type === 'chat') {
                              navigate('/')
                            }
                          }}
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1.5">
                                <EventIcon size={14} className="text-warm-muted" />
                                {isMilestone && (
                                  <span className="flex items-center gap-1 text-xs text-yellow-600">
                                    里程碑
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-warm-text leading-relaxed">{displayText}</p>
                              {hasEvidence && (
                                <div className="mt-1.5 p-2 bg-warm-bg rounded border-l-2 border-warm-accent">
                                  <span className="text-[10px] text-warm-faint uppercase tracking-wide">推断依据</span>
                                  <p className="text-xs text-warm-muted mt-0.5 leading-relaxed">"{evidenceText}"</p>
                                </div>
                              )}
                              {!hasEvidence && summaryText && summaryText !== displayText && (
                                <div className="mt-1.5">
                                  <span className="text-[10px] text-warm-faint uppercase tracking-wide">摘要</span>
                                  <p className="text-xs text-warm-muted mt-0.5 leading-relaxed">{summaryText}</p>
                                </div>
                              )}
                              <div className="flex items-center gap-3 mt-2">
                                {entry.sentiment != null && (
                                  <span className={`text-xs ${sentimentStyle}`}>
                                    {sentimentLabel} ({entry.sentiment.toFixed(2)})
                                  </span>
                                )}
                                {entry.importance_score != null && (
                                  <span className="text-xs text-warm-faint">
                                    重要性 {entry.importance_score.toFixed(1)}
                                  </span>
                                )}
                                {entry.source_type && (
                                  <span className={`text-xs ${canNavigate ? 'text-warm-accent hover:underline' : 'text-warm-faint'}`}>
                                    {sourceLabel}{canNavigate ? ' →' : ''}
                                  </span>
                                )}
                                {locked && (
                                  <Lock size={12} className="text-warm-faint" />
                                )}
                              </div>
                              {!locked && entry.id && (
                                <div className="flex items-center gap-2 mt-2">
                                  <button
                                    onClick={async (e) => {
                                      e.stopPropagation()
                                      try {
                                        const { timelineApi } = await import('../api')
                                        await timelineApi.confirmEvent(entry.id!)
                                        // Refresh detail
                                        if (selectedSlug) handleSelectPage(selectedSlug)
                                      } catch {
                                        // ignore
                                      }
                                    }}
                                    className="btn-primary text-xs px-2 py-0.5"
                                  >
                                    确认
                                  </button>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      // Extract date from timestamp
                                      const ts = entry.timestamp || ''
                                      const m = ts.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/)
                                      const dateStr = m ? `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}` : ts.slice(0, 10)
                                      setEditTimelineEntry(entry)
                                      setEditTlSummary(entry.summary || '')
                                      setEditTlContent(entry.content || '')
                                      setEditTlEventType(entry.event_type || 'routine')
                                      setEditTlTimestamp(dateStr)
                                      setEditTlImportance(entry.importance_score ?? 0.5)
                                    }}
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
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  const renderLinks = (label: string, links: PageLink[]) => {
    if (!links || links.length === 0) return null
    return (
      <div>
        <p className="text-xs font-medium text-warm-muted mb-2">{label}</p>
        <div className="flex flex-wrap gap-1.5">
          {links.map(link => {
            const Icon = TYPE_ICONS[link.type] || BookOpen
            return (
              <button
                key={link.slug}
                onClick={() => handleSelectPage(link.slug)}
                className="badge flex items-center gap-1"
              >
                <Icon size={12} />
                <span>{link.title}</span>
              </button>
            )
          })}
        </div>
      </div>
    )
  }

  const renderTypeSpecificFields = (detail: PageDetail) => {
    const fm = detail.frontmatter || {}
    const type = detail.type

    if (type === 'person') {
      const intimacy = typeof fm.intimacy === 'number' ? fm.intimacy : null
      const relationshipType = typeof fm.relationship_type === 'string' ? fm.relationship_type : ''
      const firstSeen = typeof fm.first_seen === 'string' ? fm.first_seen : ''
      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">人物信息</div>
          {intimacy !== null && (
            <div className="mb-2">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-warm-muted">亲密度</span>
                <span className="text-warm-text font-medium">{intimacy}/100</span>
              </div>
              <div className="w-full h-1.5 bg-warm-border/30 rounded-full overflow-hidden">
                <div style={{ width: `${intimacy}%`, height: '100%', background: intimacy >= 70 ? '#22c55e' : intimacy >= 40 ? '#eab308' : '#ef4444', borderRadius: '3px', transition: 'width 0.3s' }} />
              </div>
            </div>
          )}
          {relationshipType && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">关系：</span>
              <span className="badge">{relationshipType}</span>
            </div>
          )}
          {firstSeen && (
            <div className="text-xs text-warm-muted">
              首次出现：{firstSeen}
            </div>
          )}
        </div>
      )
    }

    if (type === 'habit') {
      const frequency30d = typeof fm.frequency_30d === 'number' ? fm.frequency_30d : null
      const habitType = typeof fm.habit_type === 'string' ? fm.habit_type : ''
      const firstSeen = typeof fm.first_seen === 'string' ? fm.first_seen : ''
      const lastSeen = typeof fm.last_seen === 'string' ? fm.last_seen : ''
      const confidence = typeof fm.confidence === 'string' ? fm.confidence : ''

      let statusLabel = '形成中'
      let statusColor = '#eab308'
      if (confidence === 'frequent' || confidence === 'explicit') {
        statusLabel = '已确认'
        statusColor = '#22c55e'
      } else if (confidence === 'decaying') {
        statusLabel = '消退中'
        statusColor = '#ef4444'
      }

      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">习惯信息</div>
          <div className="flex gap-2 flex-wrap mb-2">
            {habitType && <span className="badge">{habitType}</span>}
            <span className="badge" style={{ background: `${statusColor}20`, color: statusColor, borderColor: `${statusColor}30` }}>{statusLabel}</span>
          </div>
          {frequency30d !== null && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">30天频次：</span>
              <span className="text-warm-text font-medium">{frequency30d}次</span>
            </div>
          )}
          {firstSeen && <div className="text-xs text-warm-muted">首次发现：{firstSeen}</div>}
          {lastSeen && <div className="text-xs text-warm-muted">最近出现：{lastSeen}</div>}
        </div>
      )
    }

    if (type === 'emotion_pattern') {
      const triggers = Array.isArray(fm.triggers) ? fm.triggers : (typeof fm.triggers === 'string' ? [fm.triggers] : [])
      const emotionType = typeof fm.emotion_type === 'string' ? fm.emotion_type : ''
      const recoveryMethod = typeof fm.recovery_method === 'string' ? fm.recovery_method : ''
      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">情绪模式信息</div>
          {emotionType && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">情绪类型：</span>
              <span className="badge">{emotionType}</span>
            </div>
          )}
          {triggers.length > 0 && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">触发条件：</span>
              {triggers.map((t: string, i: number) => (
                <span key={i} className="badge mr-1">{t}</span>
              ))}
            </div>
          )}
          {recoveryMethod && (
            <div className="text-xs text-warm-muted">恢复方式：{recoveryMethod}</div>
          )}
        </div>
      )
    }

    if (type === 'value_signal') {
      const signalType = typeof fm.signal_type === 'string' ? fm.signal_type : ''
      const evidenceStrength = typeof fm.evidence_strength === 'string' ? fm.evidence_strength : ''
      const strengthColors: Record<string, string> = { explicit: '#22c55e', frequent: '#3b82f6', implied: '#eab308', inferred: '#9ca3af' }
      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">价值观信号</div>
          {signalType && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">信号类型：</span>
              <span className="badge">{signalType}</span>
            </div>
          )}
          {evidenceStrength && (
            <div className="text-xs">
              <span className="text-warm-muted">证据强度：</span>
              <span className="badge" style={{ background: `${strengthColors[evidenceStrength] || '#9ca3af'}20`, color: strengthColors[evidenceStrength] || '#9ca3af', borderColor: `${strengthColors[evidenceStrength] || '#9ca3af'}30` }}>{evidenceStrength}</span>
            </div>
          )}
        </div>
      )
    }

    if (type === 'place') {
      const placeType = typeof fm.place_type === 'string' ? fm.place_type : ''
      const relatedActivities = Array.isArray(fm.related_activities) ? fm.related_activities : (typeof fm.related_activities === 'string' ? [fm.related_activities] : [])
      const frequency = typeof fm.frequency === 'number' ? fm.frequency : (typeof fm.frequency === 'string' ? fm.frequency : '')
      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">地点信息</div>
          {placeType && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">地点类型：</span>
              <span className="badge">{placeType}</span>
            </div>
          )}
          {relatedActivities.length > 0 && (
            <div className="text-xs mb-1">
              <span className="text-warm-muted">关联活动：</span>
              {relatedActivities.map((a: string, i: number) => (
                <span key={i} className="badge mr-1">{a}</span>
              ))}
            </div>
          )}
          {frequency && (
            <div className="text-xs text-warm-muted">频次：{frequency}</div>
          )}
        </div>
      )
    }

    if (type === 'media') {
      const mediaType = typeof fm.media_type === 'string' ? fm.media_type : ''
      const rating = typeof fm.rating === 'number' ? fm.rating : null
      const director = typeof fm.director === 'string' ? fm.director : ''
      const keyCharacters = Array.isArray(fm.key_characters) ? fm.key_characters : (typeof fm.key_characters === 'string' ? [fm.key_characters] : [])
      const mediaSummary = typeof fm.media_summary === 'string' ? fm.media_summary : ''
      const mediaTypeLabels: Record<string, string> = { book: '书籍', movie: '电影', tv_series: '电视剧', music: '音乐', podcast: '播客', unknown: '其他' }
      return (
        <div className="section-card mb-3">
          <div className="font-semibold font-heading text-sm text-warm-text mb-2">书影音信息</div>
          <div className="flex gap-2 flex-wrap mb-2">
            {mediaType && <span className="badge">{mediaTypeLabels[mediaType] || mediaType}</span>}
            {rating !== null && (
              <div className="flex items-center gap-0.5">
                {Array.from({ length: 5 }, (_, i) => (
                  <span key={i} className={`text-xs ${i < rating ? 'text-[#FFB300]' : 'text-warm-border'}`}>★</span>
                ))}
                <span className="text-xs text-warm-muted ml-1">{rating}/5</span>
              </div>
            )}
          </div>
          {director && (
            <div className="text-sm mb-1">
              <span className="text-warm-muted">导演/作者：</span>
              <span className="font-medium text-warm-text">{director}</span>
            </div>
          )}
          {keyCharacters.length > 0 && (
            <div className="text-sm mb-1">
              <span className="text-warm-muted">主要人物：</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {keyCharacters.map((c: string, i: number) => (
                  <span key={i} className="badge">{c}</span>
                ))}
              </div>
            </div>
          )}
          {mediaSummary && (
            <div className="text-sm mt-2">
              <div className="text-warm-muted mb-1">作品摘要</div>
              <div className="leading-relaxed text-warm-text">{mediaSummary}</div>
            </div>
          )}
        </div>
      )
    }

    return null
  }

  const renderRightPanel = () => {
    if (!selectedSlug) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <div className="empty-state">
            <BookOpen size={56} className="mb-4 opacity-20" />
            <p className="text-lg">选择左侧页面查看详情</p>
          </div>
        </div>
      )
    }

    if (detailLoading) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <div className="empty-state">
            <Loader2 size={32} className="animate-spin mb-2 opacity-30" />
            <p className="text-sm">加载页面详情...</p>
          </div>
        </div>
      )
    }

    if (detailError) {
      return (
        <div className="flex-1 flex items-center justify-center">
          <div className="empty-state">
            <AlertCircle size={32} className="text-red-400 mb-3" />
            <p className="text-warm-muted mb-3">{detailError}</p>
            <button
              onClick={() => handleSelectPage(selectedSlug)}
              className="btn-primary text-sm px-4 py-2"
            >
              重试
            </button>
          </div>
        </div>
      )
    }

    if (!detail) return null

    const TypeIcon = TYPE_ICONS[detail.type] || BookOpen
    const typeLabel = PAGE_TYPE_LABELS[detail.type] || detail.type

    // Find merge suggestions related to this entity
    const detailMergeSuggestions = mergeSuggestions.filter(
      s => !ignoredSuggestions.has(`${s.source_slugs[0]}-${s.target_slug}`) &&
        (s.source_slugs.includes(selectedSlug) || s.target_slug === selectedSlug)
    )

    return (
      <div className="flex-1 overflow-y-auto p-6 surface-frosted">
        <div className="max-w-3xl mx-auto space-y-6">

          {/* Detail-level merge suggestions */}
          {detailMergeSuggestions.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 space-y-2">
              <div className="flex items-center gap-1.5 mb-1">
                <AlertCircle size={14} className="text-amber-600" />
                <span className="text-xs font-medium text-amber-700">合并建议</span>
              </div>
              {detailMergeSuggestions.map((suggestion) => {
                const suggestionKey = `${suggestion.source_slugs[0]}-${suggestion.target_slug}`
                const isSource = suggestion.source_slugs.includes(selectedSlug)
                const otherTitle = isSource ? suggestion.target_title : suggestion.source_titles[0]
                const otherSlug = isSource ? suggestion.target_slug : suggestion.source_slugs[0]
                return (
                  <div key={suggestionKey} className="flex items-center gap-2 py-1.5 px-3 bg-amber-100/80 rounded-lg">
                    <span className="text-xs text-amber-800 flex-1">
                      此实体可能与 <button onClick={() => handleSelectPage(otherSlug)} className="text-amber-900 underline underline-offset-1 hover:text-amber-700">{otherTitle}</button> 是同一实体（{suggestion.reason}）
                    </span>
                    <button
                      onClick={async () => {
                        if (mergingSuggestion) return
                        setMergingSuggestion(suggestionKey)
                        try {
                          const res = await gbrainApi.mergePages(suggestion.target_slug, suggestion.source_slugs)
                          const snapshotId = res.data?.merge_snapshot_id
                          setIgnoredSuggestions(prev => new Set(prev).add(suggestionKey))
                          loadPages(typeFilter)
                          loadMergeSuggestions()
                          handleSelectPage(suggestion.target_slug)
                          if (snapshotId) {
                            setMergeUndoInfo({ snapshotId, targetTitle: suggestion.target_title, sourceTitles: suggestion.source_titles })
                          }
                        } catch {
                          setError('合并失败')
                        } finally {
                          setMergingSuggestion(null)
                        }
                      }}
                      disabled={mergingSuggestion === suggestionKey}
                      className="shrink-0 px-2.5 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 transition-colors"
                    >
                      {mergingSuggestion === suggestionKey ? <Loader2 size={10} className="animate-spin" /> : '合并'}
                    </button>
                    <button
                      onClick={() => setIgnoredSuggestions(prev => new Set(prev).add(suggestionKey))}
                      className="shrink-0 px-2.5 py-1 text-xs bg-amber-200 text-amber-700 rounded hover:bg-amber-300 transition-colors"
                    >
                      忽略
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-warm-accent/20 flex items-center justify-center shrink-0">
              <TypeIcon size={24} className="text-warm-accent" />
            </div>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-semibold font-heading text-warm-text">{detail.title}</h1>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={`badge type-${detail.type}`}>
                  {typeLabel}
                </span>
                {detail.tags && detail.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {detail.tags.map(tag => (
                      <span key={tag} className="badge text-[10px]">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {detail.aliases && detail.aliases.length > 0 && (
                <div className="flex gap-1 flex-wrap mt-2">
                  {detail.aliases.map((alias, i) => (
                    <span key={i} className="badge text-[10px]">
                      {alias}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {detail.summary && (
            <div className="section-card mb-4 text-sm leading-relaxed">
              <div className="font-semibold text-xs text-warm-muted mb-1">摘要</div>
              {detail.summary}
            </div>
          )}

          {renderTypeSpecificFields(detail)}

          {detail.compiled_truth && (
            <div className="section-card">
              <h2 className="text-sm font-semibold font-heading text-warm-text mb-3">知识总结</h2>
              <pre className="text-sm text-warm-text leading-relaxed whitespace-pre-wrap font-sans">
                {renderWikiText(detail.compiled_truth, handleSelectPage)}
              </pre>
            </div>
          )}

          {detail.type === 'media' && (() => {
            const subContent = typeof detail.frontmatter?.sub_content === 'string' ? detail.frontmatter.sub_content : ''
            const keyCharacters = Array.isArray(detail.frontmatter?.key_characters) ? detail.frontmatter.key_characters : []
            if (!subContent && keyCharacters.length === 0) return null
            return (
              <div className="section-card">
                <h2 className="text-sm font-semibold font-heading text-warm-text mb-3">子内容</h2>
                {keyCharacters.length > 0 && (
                  <div className="mb-3">
                    <div className="text-xs text-warm-muted mb-1.5">角色</div>
                    <div className="flex flex-wrap gap-1.5">
                      {keyCharacters.map((c: string, i: number) => (
                        <span key={i} className="badge">{c}</span>
                      ))}
                    </div>
                  </div>
                )}
                {subContent && (
                  <div>
                    <div className="text-xs text-warm-muted mb-1.5">详细子内容</div>
                    <pre className="text-sm text-warm-text leading-relaxed whitespace-pre-wrap font-sans">
                      {renderWikiText(subContent, handleSelectPage)}
                    </pre>
                  </div>
                )}
              </div>
            )
          })()}

          {(() => {
            const relatedEntities = (detail.frontmatter?.related_entities as string[]) || []
            if (relatedEntities.length === 0) return null
            const CONFIDENCE_COLORS: Record<string, string> = {
              explicit: '#22c55e', frequent: '#3b82f6', implied: '#eab308', inferred: '#9ca3af'
            }
            return (
              <div className="mb-4">
                <div className="font-semibold font-heading text-sm text-warm-text mb-2">相关实体</div>
                {relatedEntities.map((entry, i) => {
                  const match = entry.match(/\[\[(.+?)\]\]\s*\|\s*(.+?)\s*\|\s*confidence:\s*(\w+)/)
                  if (!match) return <div key={i} className="text-sm mb-1">{entry}</div>
                  const slug = match[1].includes(':') ? match[1].split(':')[1] : match[1]
                  const relation = match[2]
                  const confidence = match[3]
                  return (
                    <div key={i} className="flex items-center gap-2 mb-1 text-sm">
                      <a onClick={() => handleSelectPage(slug)} className="cursor-pointer text-warm-accent hover:text-warm-accent-hover transition-colors">{slug}</a>
                      <span className="text-warm-muted">{relation}</span>
                      <span className="badge text-[10px]" style={{ background: '#9ca3af20', color: '#9ca3af', borderColor: '#9ca3af30' }}>{confidence}</span>
                    </div>
                  )
                })}
              </div>
            )
          })()}

          {(() => {
            const changeLog = (detail.frontmatter?.change_log as string[]) || []
            if (changeLog.length === 0) return null
            return (
              <div className="mb-4">
                <div className="font-semibold font-heading text-sm text-warm-text mb-2">变化记录</div>
                {changeLog.map((entry, i) => (
                  <div key={i} className="text-sm mb-1 pl-2 border-l-2 border-warm-accent">
                    {entry}
                  </div>
                ))}
              </div>
            )
          })()}

          {detail.timeline && detail.timeline.length > 0 && (
            <div className="section-card">
              <div className="flex items-center gap-2 mb-4">
                <Clock size={14} className="text-warm-accent" />
                <h2 className="text-sm font-semibold font-heading text-warm-text">时间线</h2>
                <a
                  href="/timeline"
                  className="ml-auto text-xs text-warm-accent hover:text-warm-accent-hover transition-colors"
                >
                  查看全部时间线 →
                </a>
              </div>
              {renderTimeline(detail.timeline)}
            </div>
          )}

          {(detail.forward_links && detail.forward_links.length > 0) || (detail.back_links && detail.back_links.length > 0) ? (
            <div className="section-card space-y-4">
              {renderLinks('前向链接', detail.forward_links)}
              {renderLinks('反向链接', detail.back_links)}
            </div>
          ) : null}

          <div className="section-card">
            <h2 className="text-sm font-semibold font-heading text-warm-text mb-3">页面信息</h2>
            <div className="grid grid-cols-3 gap-4 text-xs">
              <div>
                <p className="text-warm-faint">版本数</p>
                <p className="text-warm-text font-medium mt-0.5">{detail.version_count ?? 0}</p>
              </div>
              <div>
                <p className="text-warm-faint">创建时间</p>
                <p className="text-warm-text font-medium mt-0.5">{formatDate(detail.created_at)}</p>
              </div>
              <div>
                <p className="text-warm-faint">更新时间</p>
                <p className="text-warm-text font-medium mt-0.5">{formatDate(detail.updated_at)}</p>
              </div>
            </div>
          </div>

        </div>
      </div>
    )
  }

  const EVENT_TYPES_KNOWLEDGE = [
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

  return (
    <div className="flex h-full">
      {renderLeftPanel()}
      {renderRightPanel()}

      {/* Timeline Edit Modal */}
      {editTimelineEntry && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={() => setEditTimelineEntry(null)}>
          <div className="bg-warm-card border border-warm-border rounded-xl shadow-xl w-[520px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-warm-border flex items-center justify-between">
              <h3 className="text-sm font-semibold font-heading text-warm-text">编辑时间线事件</h3>
              <button
                onClick={() => setEditTimelineEntry(null)}
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
                  value={editTlTimestamp}
                  onChange={e => setEditTlTimestamp(e.target.value)}
                  className="w-full input-enhanced"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">事件类型</label>
                <select
                  value={editTlEventType}
                  onChange={e => setEditTlEventType(e.target.value)}
                  className="w-full input-enhanced"
                >
                  {EVENT_TYPES_KNOWLEDGE.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">摘要</label>
                <textarea
                  value={editTlSummary}
                  onChange={e => setEditTlSummary(e.target.value)}
                  rows={3}
                  className="w-full input-enhanced resize-none"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">详细内容</label>
                <textarea
                  value={editTlContent}
                  onChange={e => setEditTlContent(e.target.value)}
                  rows={4}
                  className="w-full input-enhanced resize-none"
                />
              </div>
              <div>
                <label className="block text-xs text-warm-muted mb-1">重要性: {editTlImportance.toFixed(1)}</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={editTlImportance}
                  onChange={e => setEditTlImportance(parseFloat(e.target.value))}
                  className="w-full accent-warm-accent"
                />
              </div>
            </div>
            <div className="p-4 border-t border-warm-border flex justify-end gap-2">
              <button
                onClick={() => setEditTimelineEntry(null)}
                className="px-4 py-2 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  if (!editTimelineEntry?.id || editTlSaving) return
                  setEditTlSaving(true)
                  try {
                    const { timelineApi } = await import('../api')
                    await timelineApi.updateEvent(editTimelineEntry.id, {
                      summary: editTlSummary,
                      content: editTlContent,
                      event_type: editTlEventType,
                      timestamp: editTlTimestamp,
                      importance_score: editTlImportance,
                    })
                    setEditTimelineEntry(null)
                    if (selectedSlug) handleSelectPage(selectedSlug)
                  } catch {
                    // ignore
                  } finally {
                    setEditTlSaving(false)
                  }
                }}
                disabled={editTlSaving}
                className="btn-primary text-xs px-4 py-2 disabled:opacity-50"
              >
                {editTlSaving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Merge Undo Toast */}
      {mergeUndoInfo && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4">
          <div className="flex items-center gap-3 px-5 py-3 bg-warm-card border border-warm-border rounded-xl shadow-lg">
            <span className="text-sm text-warm-text">
              已将 {mergeUndoInfo.sourceTitles.join('、')} 合并到 {mergeUndoInfo.targetTitle}
            </span>
            <button
              onClick={async () => {
                if (undoing) return
                setUndoing(true)
                try {
                  await gbrainApi.undoMerge(mergeUndoInfo.snapshotId)
                  setMergeUndoInfo(null)
                  loadPages(typeFilter)
                  loadMergeSuggestions()
                } catch {
                  setError('撤回失败')
                } finally {
                  setUndoing(false)
                }
              }}
              disabled={undoing}
              className="px-3 py-1.5 text-xs bg-warm-accent text-white rounded-lg hover:bg-warm-accent-hover disabled:opacity-50 transition-colors whitespace-nowrap btn-primary"
            >
              {undoing ? <Loader2 size={12} className="animate-spin" /> : '撤回'}
            </button>
            <button
              onClick={() => setMergeUndoInfo(null)}
              className="text-warm-faint hover:text-warm-muted transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      {contextMenu && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setContextMenu(null)}
            onContextMenu={(e) => { e.preventDefault(); setContextMenu(null) }}
          />
          <div
            className="fixed z-50 bg-warm-card border border-warm-border rounded-lg shadow-xl py-1 min-w-[140px]"
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={() => handleDeletePage(contextMenu.slug)}
              disabled={deleting}
              className="w-full text-left px-3 py-2 text-xs text-red-600 hover:bg-red-50 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
              删除实体
            </button>
          </div>
        </>
      )}
    </div>
  )
}