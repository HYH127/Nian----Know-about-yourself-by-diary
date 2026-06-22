import { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Brain, Globe, Loader2, History, ArrowLeft, ChevronRight, Hash, Search, Eye, Calendar, MessageSquare, X, Send, RotateCcw, Trash2, AlertCircle } from 'lucide-react'
import { profileApi, gbrainApi, diaryApi } from '../api'
import type { PortraitRecord, PortraitVersionItem, PortraitModule } from '../types'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

const CONFIDENCE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  explicit: { label: '明确', color: 'text-green-500', bg: 'bg-green-400/15 border-green-400/30' },
  frequent: { label: '频繁', color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/30' },
  implied: { label: '暗示', color: 'text-yellow-600', bg: 'bg-yellow-400/10 border-yellow-400/30' },
  inferred: { label: '推断', color: 'text-warm-muted', bg: 'bg-gray-400/10 border-gray-400/30' },
}

type PortraitTab = 'weekly' | 'monthly' | 'detailed' | 'deep' | 'overall'

const TAB_CONFIG: Record<PortraitTab, { label: string; icon: typeof Sparkles }> = {
  weekly:   { label: '周画像',   icon: Calendar },
  monthly:  { label: '月画像',   icon: Brain },
  detailed: { label: '细节画像', icon: Search },
  deep:     { label: '深度画像', icon: Eye },
  overall:  { label: '总画像',   icon: Globe },
}

const STRATEGY_OPTIONS = [
  { value: 'time_weighted', label: '时间加权融合', shortLabel: '时间加权', description: '近期数据权重高，远期权重低，符合记忆衰减规律' },
  { value: 'recursive', label: '分层递归总结', shortLabel: '递归总结', description: '按年度分层提炼，关注连续性和转折点' },
  { value: 'dual_track', label: '双轨制', shortLabel: '双轨制', description: '静态核心档案+动态近期画像，分离稳定与变化' },
] as const

// Tabs that use pages table (pure text display)
const PAGES_TABS: PortraitTab[] = ['weekly', 'monthly', 'overall']
// Tabs that use portrait_records table (module card display)
const MODULE_TABS: PortraitTab[] = ['detailed', 'deep']

export default function Portraits() {
  const [activeTab, setActiveTab] = useState<PortraitTab>('weekly')
  const [showVersions, setShowVersions] = useState(false)
  const [viewingVersionId, setViewingVersionId] = useState<string | null>(null)
  const [viewingVersion, setViewingVersion] = useState<PortraitRecord | null>(null)
  const [loadingVersion, setLoadingVersion] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState<string | null>(null)
  const [overallStrategy, setOverallStrategy] = useState<string>('time_weighted')
  const [showStrategyPicker, setShowStrategyPicker] = useState(false)

  // Pages-based viewing version state (weekly/monthly/overall)
  const [pagesViewingVersion, setPagesViewingVersion] = useState<string | null>(null)
  const [pagesViewingText, setPagesViewingText] = useState<string | null>(null)

  const isPagesTab = PAGES_TABS.includes(activeTab)
  const isModuleTab = MODULE_TABS.includes(activeTab)
  const isOverall = activeTab === 'overall'
  const isWeekly = activeTab === 'weekly'
  const isMonthly = activeTab === 'monthly'
  const isDetailed = activeTab === 'detailed'
  const isDeep = activeTab === 'deep'

  // ── Weekly profile data (pages table) ──
  const { data: weeklyData, isLoading: weeklyLoading, refetch: weeklyRefetch } = useQuery({
    queryKey: ['weekly-profile'],
    queryFn: async () => {
      try {
        const res = await gbrainApi.getWeeklyProfile()
        return res.data
      } catch {
        return { compiled_truth: '', title: '', updated_at: '', slug: '', versions: [] }
      }
    },
    enabled: isWeekly,
  })

  // ── Monthly profile data (pages table) ──
  const { data: monthlyData, isLoading: monthlyLoading, refetch: monthlyRefetch } = useQuery({
    queryKey: ['monthly-profile'],
    queryFn: async () => {
      try {
        const res = await gbrainApi.getMonthlyProfile()
        return res.data
      } catch {
        return { compiled_truth: '', title: '', updated_at: '', slug: '', versions: [] }
      }
    },
    enabled: isMonthly,
  })

  // ── Overall profile data (pages table) ──
  const { data: overallData, isLoading: overallLoading, refetch: overallRefetch } = useQuery({
    queryKey: ['overall-profile'],
    queryFn: async () => {
      try {
        const res = await gbrainApi.getOverallProfile()
        return res.data
      } catch {
        return { compiled_truth: '', title: '', updated_at: '', versions: [] }
      }
    },
    enabled: isOverall,
  })

  // ── Module-based portrait records (detailed/deep) ──
  const portraitType = isDetailed ? 'detailed' : isDeep ? 'deep' : ''
  const { data: records = [], isLoading: recordsLoading, refetch: recordsRefetch } = useQuery({
    queryKey: ['portrait-records', portraitType],
    queryFn: async () => {
      try {
        const res = await profileApi.getPortraitRecords(portraitType)
        return (res.data || []) as PortraitRecord[]
      } catch {
        return [] as PortraitRecord[]
      }
    },
    enabled: isModuleTab,
  })

  const { data: versions = [], isLoading: versionsLoading } = useQuery({
    queryKey: ['portrait-versions', portraitType],
    queryFn: async () => {
      try {
        const res = await profileApi.getPortraitVersions(portraitType)
        return (res.data || []) as PortraitVersionItem[]
      } catch {
        return [] as PortraitVersionItem[]
      }
    },
    enabled: showVersions && isModuleTab,
  })

  // ── Derived state ──
  const currentRecord = useMemo(() => records.find(r => r.is_current === 1), [records])
  const displayRecord = viewingVersion || currentRecord
  const modules = displayRecord?.modules || []
  const isViewingHistorical = viewingVersionId !== null && displayRecord?.is_current !== 1

  // Pages-based display text
  const pagesData = isWeekly ? weeklyData : isMonthly ? monthlyData : overallData
  const pagesDisplayText = pagesViewingText ?? (pagesData as any)?.compiled_truth ?? ''
  const isPagesViewingHistorical = pagesViewingVersion !== null
  const pagesVersions = (pagesData as any)?.versions || []

  // ── Generate handler ──
  const handleGenerate = useCallback(async () => {
    if (generating) return
    setGenerating(true)
    setGenerateError(null)
    try {
      if (isWeekly || isMonthly) {
        // 检查最近一周/月是否有日记
        const datesRes = await diaryApi.getDates()
        const dates: string[] = datesRes.data.map((d: any) => d.date || d)
        const now = new Date()
        const days = isWeekly ? 7 : 30
        const cutoff = new Date(now.getTime() - days * 24 * 3600 * 1000)
        const hasRecent = dates.some(d => new Date(d) >= cutoff)
        if (!hasRecent) {
          setGenerateError(`最近${isWeekly ? '一周' : '一月'}无日记记录，暂时无法生成`)
          return
        }
      }

      if (isWeekly) {
        await gbrainApi.generateWeeklyProfile()
        await weeklyRefetch()
      } else if (isMonthly) {
        await gbrainApi.generateMonthlyProfile()
        await monthlyRefetch()
      } else if (isDetailed) {
        await profileApi.generateDetailedPortrait()
        await recordsRefetch()
      } else if (isDeep) {
        await profileApi.generateDeepPortrait()
        await recordsRefetch()
      } else {
        await gbrainApi.generateOverallProfile(overallStrategy)
        await overallRefetch()
      }
    } catch (err) {
      console.error('生成画像失败', err)
    } finally {
      setGenerating(false)
    }
  }, [activeTab, generating, weeklyRefetch, monthlyRefetch, recordsRefetch, overallRefetch, overallStrategy])

  const handleViewVersion = useCallback(async (versionId: string) => {
    setLoadingVersion(true)
    try {
      const res = await profileApi.getPortraitVersion(versionId)
      setViewingVersion(res.data)
      setViewingVersionId(versionId)
      setShowVersions(false)
    } catch (err) {
      console.error('获取版本详情失败', err)
    } finally {
      setLoadingVersion(false)
    }
  }, [])

  const handlePagesViewVersion = useCallback((versionId: string, text: string) => {
    setPagesViewingVersion(versionId)
    setPagesViewingText(text)
    setShowVersions(false)
  }, [])

  const handleBackToCurrent = useCallback(() => {
    if (isModuleTab) {
      setViewingVersionId(null)
      setViewingVersion(null)
    } else {
      setPagesViewingVersion(null)
      setPagesViewingText(null)
    }
  }, [isModuleTab])

  const handleTabChange = (tab: PortraitTab) => {
    setActiveTab(tab)
    setShowVersions(false)
    setViewingVersionId(null)
    setViewingVersion(null)
    setPagesViewingVersion(null)
    setPagesViewingText(null)
  }

  const isViewingHistoricalVersion = isModuleTab ? isViewingHistorical : isPagesViewingHistorical

  // ── Tab icon for empty states ──
  const TabIcon = TAB_CONFIG[activeTab].icon

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader title="画像管理" icon={<Sparkles size={20} />} />

      {/* Tab bar */}
      <div className="flex items-center gap-1 mb-6 overflow-x-auto">
        {(Object.keys(TAB_CONFIG) as PortraitTab[]).map(key => {
          const config = TAB_CONFIG[key]
          const Icon = config.icon
          return (
            <button
              key={key}
              onClick={() => handleTabChange(key)}
              className={`tab-btn flex items-center gap-1.5 whitespace-nowrap ${activeTab === key ? 'active' : ''}`}
            >
              <Icon size={14} />
              {config.label}
            </button>
          )
        })}
      </div>

      {/* Header bar */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {isModuleTab ? (
            displayRecord && (
              <span className="text-xs text-warm-faint">
                生成于 {new Date(displayRecord.created_at.replace(' ', 'T')).toLocaleString('zh-CN')}
              </span>
            )
          ) : (
            (pagesData as any)?.updated_at && (
              <span className="text-xs text-warm-faint">
                生成于 {new Date((pagesData as any).updated_at.replace(' ', 'T')).toLocaleString('zh-CN')}
              </span>
            )
          )}
          {isViewingHistoricalVersion && (
            <span className="badge text-[10px]">
              历史版本
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isViewingHistoricalVersion && (
            <button
              onClick={handleBackToCurrent}
              className="tab-btn text-xs flex items-center gap-1.5"
            >
              <ArrowLeft size={14} />
              返回当前版本
            </button>
          )}
          <button
            onClick={() => setShowVersions(!showVersions)}
            className={`tab-btn text-xs flex items-center gap-1.5 ${showVersions ? 'active' : ''}`}
          >
            <History size={14} />
            历史版本
          </button>
          {isOverall && (
            <div className="relative">
              <button
                onClick={() => setShowStrategyPicker(!showStrategyPicker)}
                className="tab-btn text-xs flex items-center gap-1.5"
              >
                <Brain size={14} />
                {STRATEGY_OPTIONS.find(s => s.value === overallStrategy)?.shortLabel || '策略'}
              </button>
              {showStrategyPicker && (
                <div className="absolute right-0 top-full mt-1 z-20 w-72 rounded-xl bg-warm-card border border-warm-border shadow-lg overflow-hidden">
                  {STRATEGY_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      onClick={() => { setOverallStrategy(opt.value); setShowStrategyPicker(false) }}
                      className={`w-full text-left px-4 py-3 hover:bg-warm-input/50 transition-colors ${
                        overallStrategy === opt.value ? 'bg-warm-accent/10' : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-warm-text">{opt.label}</span>
                        {overallStrategy === opt.value && (
                          <span className="badge text-[10px]">当前</span>
                        )}
                      </div>
                      <p className="text-xs text-warm-muted mt-0.5">{opt.description}</p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="btn-primary text-xs flex items-center gap-2 disabled:opacity-50"
          >
            {generating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {generating ? '生成中...' : '生成画像'}
          </button>
        </div>
      </div>

      {generateError && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-700 flex items-center gap-2">
          <AlertCircle size={14} className="shrink-0" />
          {generateError}
        </div>
      )}

          {/* Version history panel */}
          {showVersions && (
            <div className="mb-6 section-card overflow-hidden">
              <div className="p-4 pb-3 mb-3">
                <h3 className="text-sm font-medium text-warm-text flex items-center gap-2">
                  <History size={14} className="text-warm-accent" />
                  版本历史
                </h3>
              </div>
              {isModuleTab ? (
                // Module-based versions from portrait_records
                versionsLoading ? (
                  <div className="empty-state text-sm">
                    <Loader2 size={16} className="animate-spin mb-2 opacity-30" />
                    加载中...
                  </div>
                ) : versions.length === 0 ? (
                  <div className="empty-state text-sm">暂无历史版本</div>
                ) : (
                  <div className="divide-y divide-warm-border">
                    {versions.map(v => (
                      <button
                        key={v.id}
                        onClick={() => handleViewVersion(v.id)}
                        disabled={loadingVersion}
                        className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-warm-input/50 transition-colors disabled:opacity-50 ${
                          v.is_current === 1 ? 'bg-warm-accent/10' : ''
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-warm-text">
                              {new Date(v.created_at).toLocaleString('zh-CN')}
                            </span>
                            {v.is_current === 1 && (
                              <span className="badge text-[10px]">当前</span>
                            )}
                          </div>
                          <span className="text-xs text-warm-faint">{v.modules_count} 个模块</span>
                        </div>
                        <ChevronRight size={14} className="text-warm-faint shrink-0" />
                      </button>
                    ))}
                  </div>
                )
              ) : (
                // Pages-based versions from page_versions
                pagesVersions.length === 0 ? (
                  <div className="empty-state text-sm">暂无历史版本</div>
                ) : (
                  <div className="divide-y divide-warm-border">
                    {pagesVersions.map((v: any) => (
                      <button
                        key={v.id}
                        onClick={() => handlePagesViewVersion(String(v.id), v.compiled_truth_snapshot)}
                        className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-warm-input/50 transition-colors ${
                          pagesViewingVersion === String(v.id) ? 'bg-warm-accent/10' : ''
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm text-warm-text">
                              版本 {v.version_number}
                            </span>
                            <span className="text-xs text-warm-faint">
                              {new Date(v.created_at + (v.created_at.includes('T') ? '' : 'T00:00:00')).toLocaleString('zh-CN')}
                            </span>
                          </div>
                        </div>
                        <ChevronRight size={14} className="text-warm-faint shrink-0" />
                      </button>
                    ))}
                  </div>
                )
              )}
            </div>
          )}

          {/* Main content area */}
          {/* Main content area */}
          {loadingVersion ? (
            <div className="empty-state py-20">
              <Loader2 size={24} className="animate-spin mb-2 opacity-30" />
              <p className="text-sm">加载版本...</p>
            </div>
          ) : isModuleTab ? (
            // ── Module-based display (detailed / deep) ──
            recordsLoading ? (
              <div className="empty-state py-20">
                <Loader2 size={24} className="animate-spin mb-2 opacity-30" />
                <p className="text-sm">加载中...</p>
              </div>
            ) : modules.length === 0 ? (
              <div className="empty-state py-20">
                <TabIcon size={48} className="mb-4 opacity-30" />
                <p className="text-lg mb-2">暂无{TAB_CONFIG[activeTab].label}数据</p>
                <p className="text-sm mb-4">点击「生成画像」按钮，从你的行为数据中提取画像</p>
              </div>
            ) : (
              <div className="space-y-4">
                {modules.map((module, index) => (
                  <PortraitModuleCard
                    key={index}
                    module={module}
                    portraitType={portraitType}
                    index={index}
                  />
                ))}
              </div>
            )
          ) : (
            // ── Pages-based display (weekly / monthly / overall) ──
            (isWeekly ? weeklyLoading : isMonthly ? monthlyLoading : overallLoading) ? (
              <div className="empty-state py-20">
                <Loader2 size={24} className="animate-spin mb-2 opacity-30" />
                <p className="text-sm">加载中...</p>
              </div>
            ) : !pagesDisplayText ? (
              <div className="empty-state py-20">
                <TabIcon size={48} className="mb-4 opacity-30" />
                <p className="text-lg mb-2">暂无{TAB_CONFIG[activeTab].label}数据</p>
                <p className="text-sm mb-4">点击「生成画像」按钮生成{TAB_CONFIG[activeTab].label}</p>
              </div>
            ) : (
              <div className="section-card overflow-hidden">
                <div className="p-6">
                  <PagesFeedbackButton portraitType={activeTab} />
                  <OverallProfileContent text={pagesDisplayText} />
                </div>
              </div>
            )
          )}
    </PageContainer>
  )
}

function PortraitModuleCard({ module, portraitType, index }: { module: PortraitModule; portraitType: string; index: number }) {
  const conf = CONFIDENCE_CONFIG[module.confidence] || CONFIDENCE_CONFIG.inferred
  const [showFeedback, setShowFeedback] = useState(false)

  const blocks = parseModuleContent(module.content)

  // Extract counter_examples from module if present
  const counterExamples: string[] = (module as any).counter_examples || []

  const targetSlug = `${portraitType}_${index}`

  return (
    <div className="section-card overflow-hidden">
      <div className="p-5">
        {/* Header */}
        <div className="flex items-center gap-2 mb-4">
          <span className="inline-block w-1 h-5 rounded-full bg-warm-accent/60" />
          <span className="text-sm font-semibold text-warm-text">{module.title || ''}</span>
          <span className={`badge text-xs ${conf.bg} ${conf.color}`}>
            {conf.label}
          </span>
          {module.abstraction_level && (
            <span className="badge text-xs">
              {module.abstraction_level}
            </span>
          )}
          <div className="flex-1" />
          <button
            onClick={() => setShowFeedback(!showFeedback)}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-all ${
              showFeedback
                ? 'bg-warm-accent/15 text-warm-accent font-medium'
                : 'text-warm-muted hover:text-warm-accent hover:bg-warm-accent/10'
            }`}
            title="反馈修正"
          >
            <MessageSquare size={13} />
            反馈
          </button>
        </div>

        {/* Feedback panel */}
        {showFeedback && (
          <FeedbackPanel
            targetType={portraitType}
            targetSlug={targetSlug}
            onClose={() => setShowFeedback(false)}
          />
        )}

        {/* Content blocks */}
        <div className="space-y-3">
          {blocks.map((block, i) => {
            if (block.type === 'heading') {
              const sizeClass = block.level === 1
                ? 'text-sm font-semibold text-warm-text'
                : block.level === 2
                ? 'text-sm font-semibold text-warm-accent'
                : 'text-xs font-semibold text-warm-muted uppercase tracking-wide'
              const barClass = block.level === 1
                ? 'w-1 h-5 bg-warm-accent'
                : block.level === 2
                ? 'w-1 h-4 bg-warm-accent/60'
                : 'w-1 h-1 bg-warm-accent/50'
              return (
                <div key={i} className={`flex items-center gap-2 ${block.level === 3 ? '' : 'mt-4'} first:mt-0`}>
                  <span className={`inline-block ${barClass} rounded-full`} />
                  <span className={sizeClass}>{block.text}</span>
                </div>
              )
            }
            if (block.type === 'evidence') {
              return (
                <div key={i} className="mt-3 pt-3 border-t border-warm-border/50">
                  <div className="text-xs font-medium text-warm-muted mb-2 flex items-center gap-1.5">
                    <Hash size={10} />
                    证据来源
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {block.items.slice(0, 8).map((ev, j) => (
                      <span key={j} className="badge text-xs">
                        <InlineBoldText text={ev} />
                      </span>
                    ))}
                    {block.items.length > 8 && (
                      <span className="text-xs text-warm-faint">+{block.items.length - 8} 更多</span>
                    )}
                  </div>
                </div>
              )
            }
            if (block.type === 'bulletList') {
              return (
                <div key={i} className="space-y-1.5">
                  {block.items.map((item, j) => (
                    <div key={j} className="flex items-start gap-2 text-sm text-warm-text leading-relaxed">
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-warm-accent/50 mt-2 shrink-0" />
                      <InlineBoldText text={item} />
                    </div>
                  ))}
                </div>
              )
            }
            if (block.type === 'numberedList') {
              return (
                <div key={i} className="space-y-2.5">
                  {block.items.map((item, j) => (
                    <div key={j} className="flex items-start gap-2.5 text-sm text-warm-text leading-relaxed">
                      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-warm-accent/10 text-warm-accent text-xs font-semibold shrink-0 mt-0.5">
                        {j + 1}
                      </span>
                      <div className="flex-1">
                        <InlineBoldText text={item} />
                      </div>
                    </div>
                  ))}
                </div>
              )
            }
            if (block.type === 'question') {
              return (
                <div key={i} className="mt-2 px-3 py-2 rounded-lg bg-warm-accent/8 border-l-2 border-warm-accent/40">
                  <InlineBoldText text={block.text} />
                </div>
              )
            }
            if (block.type === 'counter') {
              return (
                <div key={i} className="mt-2 px-3 py-2 rounded-lg bg-green-400/8 border-l-2 border-green-400/40">
                  <span className="text-xs font-medium text-green-500/80 mr-1">反例</span>
                  <InlineBoldText text={block.text} />
                </div>
              )
            }
            if (block.type === 'quote') {
              return (
                <div key={i} className="px-4 py-3 rounded-lg bg-warm-accent/5 border-l-2 border-warm-accent/30 text-sm text-warm-muted leading-relaxed italic">
                  <InlineBoldText text={block.text} />
                </div>
              )
            }
            // paragraph
            return (
              <div key={i} className="text-sm text-warm-text leading-relaxed">
                <InlineBoldText text={block.text} />
              </div>
            )
          })}
        </div>

        {/* Counter examples from module.counter_examples field */}
        {counterExamples.length > 0 && !blocks.some(b => b.type === 'counter') && (
          <div className="mt-3 pt-3">
            <div className="text-xs font-medium text-warm-muted mb-2">反例</div>
            <div className="space-y-1.5">
              {counterExamples.map((ce, i) => (
                <div key={i} className="px-3 py-2 rounded-lg bg-green-400/8 border-l-2 border-green-400/40">
                  <span className="text-xs font-medium text-green-500/80 mr-1">反例</span>
                  <InlineBoldText text={ce} />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Evidence from module.evidence array (fallback if not parsed from content) */}
        {module.evidence.length > 0 && !blocks.some(b => b.type === 'evidence') && (
          <div className="mt-3 pt-3">
            <div className="text-xs font-medium text-warm-muted mb-2 flex items-center gap-1.5">
              <Hash size={10} />
              证据来源
            </div>
            <div className="flex flex-wrap gap-1.5">
              {module.evidence.slice(0, 8).map((ev, i) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-warm-input text-warm-muted">
                  {ev}
                </span>
              ))}
              {module.evidence.length > 8 && (
                <span className="text-xs text-warm-faint">+{module.evidence.length - 8} 更多</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

type ContentBlock =
  | { type: 'heading'; text: string; level: 1 | 2 | 3 }
  | { type: 'paragraph'; text: string }
  | { type: 'bulletList'; items: string[] }
  | { type: 'numberedList'; items: string[] }
  | { type: 'evidence'; items: string[] }
  | { type: 'question'; text: string }
  | { type: 'counter'; text: string }
  | { type: 'quote'; text: string }

/** 统一内容解析器：支持 markdown 标题/列表/引用 + 中文语义标记（证据/反例/问题） */
function parseContentBlocks(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = []
  const lines = content.split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i].trim()
    if (!line) { i++; continue }

    // Markdown headings: ### / ## / #
    if (line.startsWith('### ')) {
      blocks.push({ type: 'heading', text: line.replace(/^###\s+/, ''), level: 3 })
      i++; continue
    }
    if (line.startsWith('## ')) {
      blocks.push({ type: 'heading', text: line.replace(/^##\s+/, ''), level: 2 })
      i++; continue
    }
    if (line.startsWith('# ')) {
      blocks.push({ type: 'heading', text: line.replace(/^#\s+/, ''), level: 1 })
      i++; continue
    }

    // Bold-only line as sub-heading: **核心人格特质**
    const boldOnly = line.match(/^\*\*(.+)\*\*$/)
    if (boldOnly && !line.includes('：') && line.length < 40) {
      blocks.push({ type: 'heading', text: boldOnly[1], level: 2 })
      i++; continue
    }

    // 证据列表 / 证据：
    if (line.match(/^证据列表[：:]?$/) || line.match(/^证据[：:]/)) {
      i++
      const items: string[] = []
      while (i < lines.length) {
        const evLine = lines[i].trim()
        if (evLine.match(/^[-•*]\s+/)) { items.push(evLine.replace(/^[-•*]\s+/, '')); i++ }
        else if (!evLine) { i++ }
        else { break }
      }
      if (items.length > 0) blocks.push({ type: 'evidence', items })
      continue
    }

    // 可能你想探索的问题：
    if (line.match(/^可能你想探索的问题[：:]/)) {
      const text = line.replace(/^可能你想探索的问题[：:]\s*/, '')
      if (text) blocks.push({ type: 'question', text })
      i++; continue
    }

    // 反例：
    if (line.match(/^反例[：:]/)) {
      const text = line.replace(/^反例[：:]\s*/, '')
      if (text) blocks.push({ type: 'counter', text })
      i++; continue
    }

    // Numbered list: 1. / 1、 / 1)
    if (line.match(/^\d+[.、)]\s+/)) {
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i].trim()
        if (l.match(/^\d+[.、)]\s+/)) { items.push(l.replace(/^\d+[.、)]\s+/, '')); i++ }
        else if (!l) { i++ }
        else { break }
      }
      if (items.length > 0) blocks.push({ type: 'numberedList', items })
      continue
    }

    // Bullet list: - / • / *
    if (line.match(/^[-•*]\s+/)) {
      const items: string[] = []
      while (i < lines.length) {
        const l = lines[i].trim()
        if (l.match(/^[-•*]\s+/)) { items.push(l.replace(/^[-•*]\s+/, '')); i++ }
        else if (!l) { i++ }
        else { break }
      }
      if (items.length > 0) blocks.push({ type: 'bulletList', items })
      continue
    }

    // Quote: > text
    if (line.startsWith('> ')) {
      blocks.push({ type: 'quote', text: line.replace(/^>\s+/, '') })
      i++; continue
    }

    // Paragraph: collect consecutive non-special lines
    const paraLines: string[] = []
    while (i < lines.length) {
      const l = lines[i].trim()
      if (!l || l.startsWith('#') || l.match(/^[-•*]\s+/) || l.match(/^\d+[.、)]\s+/) || l.startsWith('> ')) break
      if (l.match(/^\*\*.+\*\*$/) && !l.includes('：') && l.length < 40) break
      if (l.match(/^证据/) || l.match(/^可能你想/) || l.match(/^反例[：:]/)) break
      paraLines.push(l); i++
    }
    if (paraLines.length > 0) blocks.push({ type: 'paragraph', text: paraLines.join('\n') })
  }

  return blocks
}

// Backward-compatible alias
const parseModuleContent = parseContentBlocks

/** Render overall profile text with full semantic layout */
function OverallProfileContent({ text }: { text: string }) {
  const blocks = parseContentBlocks(text)

  if (blocks.length === 0) {
    return (
      <div className="text-sm text-warm-text leading-relaxed">
        <InlineBoldText text={text} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'heading':
            if (block.level === 1) {
              return (
                <div key={i} className="pt-4 first:pt-0">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="inline-block w-1 h-5 rounded-full bg-warm-accent" />
                    <h3 className="text-base font-semibold text-warm-text">{block.text}</h3>
                  </div>
                </div>
              )
            }
            if (block.level === 2) {
              return (
                <div key={i} className="pt-3 first:pt-0">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="inline-block w-1 h-4 rounded-full bg-warm-accent/60" />
                    <h4 className="text-sm font-semibold text-warm-accent">{block.text}</h4>
                  </div>
                </div>
              )
            }
            return (
              <div key={i} className="pt-2 first:pt-0">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="inline-block w-1 h-1 rounded-full bg-warm-accent/50" />
                  <span className="text-xs font-semibold text-warm-muted uppercase tracking-wide">{block.text}</span>
                </div>
              </div>
            )
          case 'bulletList':
            return (
              <div key={i} className="space-y-1.5 pl-1">
                {block.items.map((item, j) => (
                  <div key={j} className="flex items-start gap-2 text-sm text-warm-text leading-relaxed">
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-warm-accent/50 mt-2 shrink-0" />
                    <InlineBoldText text={item} />
                  </div>
                ))}
              </div>
            )
          case 'numberedList':
            return (
              <div key={i} className="space-y-2.5">
                {block.items.map((item, j) => (
                  <div key={j} className="flex items-start gap-2.5 text-sm text-warm-text leading-relaxed">
                    <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-warm-accent/10 text-warm-accent text-xs font-semibold shrink-0 mt-0.5">
                      {j + 1}
                    </span>
                    <div className="flex-1">
                      <InlineBoldText text={item} />
                    </div>
                  </div>
                ))}
              </div>
            )
          case 'quote':
            return (
              <div key={i} className="px-4 py-3 rounded-lg bg-warm-accent/5 border-l-2 border-warm-accent/30 text-sm text-warm-muted leading-relaxed italic">
                <InlineBoldText text={block.text} />
              </div>
            )
          case 'paragraph':
            return (
              <div key={i} className="text-sm text-warm-text leading-relaxed">
                <InlineBoldText text={block.text} />
              </div>
            )
          default:
            return null
        }
      })}
    </div>
  )
}

/** Render text with inline **bold** support */
function InlineBoldText({ text }: { text: string }) {
  const parts = text.split(/(\*\*.+?\*\*)/g)
  return parts.map((part, i) => {
    const boldMatch = part.match(/^\*\*(.+?)\*\*$/)
    if (boldMatch) {
      return <strong key={i} className="font-semibold text-warm-text">{boldMatch[1]}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

// ── Pages Feedback Button (for weekly/monthly/overall) ──

function PagesFeedbackButton({ portraitType }: { portraitType: string }) {
  const [showFeedback, setShowFeedback] = useState(false)
  const config = TAB_CONFIG[portraitType as keyof typeof TAB_CONFIG]
  const Icon = config?.icon || Brain

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon size={16} className="text-warm-accent" />
          <span className="text-sm font-medium text-warm-text">
            {config?.label || portraitType}
          </span>
        </div>
        <button
          onClick={() => setShowFeedback(!showFeedback)}
          className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-all ${
            showFeedback
              ? 'bg-warm-accent/15 text-warm-accent font-medium'
              : 'text-warm-muted hover:text-warm-accent hover:bg-warm-accent/10'
          }`}
          title="反馈修正"
        >
          <MessageSquare size={13} />
          反馈
        </button>
      </div>
      {showFeedback && (
        <FeedbackPanel
          targetType={portraitType}
          targetSlug={portraitType}
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  )
}

// ── Feedback Panel ──

const ERROR_TYPES = [
  { value: 'fact_error', label: '事实错误', desc: '画像中的事实描述不正确' },
  { value: 'false_habit_formation', label: '习惯误判', desc: '将偶然行为误判为习惯' },
  { value: 'wrong_emotion', label: '情绪误判', desc: '情绪判断不准确' },
  { value: 'wrong_relationship', label: '关系误判', desc: '关系描述不正确' },
  { value: 'dislike', label: '不喜欢', desc: '不想看到这类描述' },
  { value: 'other', label: '其他', desc: '其他问题' },
] as const

function FeedbackPanel({ targetType, targetSlug, onClose }: {
  targetType: string
  targetSlug: string
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [selectedType, setSelectedType] = useState<string>('')
  const [correctionText, setCorrectionText] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const { data: feedbackList = [], isLoading: feedbackLoading } = useQuery({
    queryKey: ['feedback', targetType, targetSlug],
    queryFn: async () => {
      try {
        const res = await profileApi.listFeedback({ target_type: targetType, is_active: 1 })
        return (res.data || []) as any[]
      } catch {
        return []
      }
    },
  })

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!selectedType) return
      return profileApi.submitFeedback({
        target_type: targetType,
        target_slug: targetSlug,
        error_type: selectedType,
        correction_text: selectedType !== 'dislike' ? correctionText : undefined,
      })
    },
    onSuccess: () => {
      setSubmitted(true)
      queryClient.invalidateQueries({ queryKey: ['feedback', targetType, targetSlug] })
      setTimeout(() => {
        setSubmitted(false)
        setSelectedType('')
        setCorrectionText('')
      }, 2000)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => profileApi.deleteFeedback(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedback', targetType, targetSlug] })
    },
  })

  const reactivateMutation = useMutation({
    mutationFn: async (id: string) => profileApi.reactivateFeedback(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedback', targetType, targetSlug] })
    },
  })

  const canSubmit = selectedType && (selectedType === 'dislike' || correctionText.trim())

  return (
    <div className="mb-4 p-4 rounded-xl bg-warm-accent/5 border border-warm-accent/20">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-semibold text-warm-accent flex items-center gap-1.5">
          <MessageSquare size={13} />
          反馈修正
        </span>
        <button onClick={onClose} className="w-5 h-5 rounded-full hover:bg-warm-input flex items-center justify-center text-warm-faint hover:text-warm-muted transition-colors">
          <X size={12} />
        </button>
      </div>

      {/* Error type selection */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {ERROR_TYPES.map(t => (
          <button
            key={t.value}
            onClick={() => setSelectedType(t.value)}
            className={`px-2.5 py-1 rounded-lg text-xs transition-all ${
              selectedType === t.value
                ? 'bg-warm-accent text-white font-medium'
                : 'bg-warm-input text-warm-muted hover:text-warm-text'
            }`}
            title={t.desc}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Correction text */}
      {selectedType && selectedType !== 'dislike' && (
        <textarea
          value={correctionText}
          onChange={e => setCorrectionText(e.target.value)}
          placeholder="请描述正确的信息..."
          className="w-full px-3 py-2 rounded-lg bg-warm-input border border-warm-border text-sm text-warm-text placeholder-warm-muted focus:outline-none focus:border-warm-accent/50 focus:ring-2 focus:ring-warm-accent/10 transition-all resize-none"
          rows={2}
        />
      )}

      {/* Submit button */}
      <div className="flex items-center justify-between mt-3">
        <span className="text-[10px] text-warm-faint">反馈将影响下次画像生成</span>
        <button
          onClick={() => submitMutation.mutate()}
          disabled={!canSubmit || submitMutation.isPending || submitted}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warm-accent text-white text-xs font-medium hover:bg-warm-accent-hover transition-colors disabled:opacity-40"
        >
          {submitted ? (
            <>已提交</>
          ) : submitMutation.isPending ? (
            <Loader2 size={12} className="animate-spin" />
          ) : (
            <Send size={12} />
          )}
          {submitted ? '已提交' : '提交'}
        </button>
      </div>

      {/* Existing feedback list */}
      {feedbackList.length > 0 && (
        <div className="mt-3 pt-3 border-t border-warm-border/50">
          <div className="text-[10px] font-semibold text-warm-faint mb-2">已有反馈</div>
          <div className="space-y-1.5">
            {feedbackList.slice(0, 5).map((fb: any) => (
              <div key={fb.id} className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-warm-input/50">
                <span className="text-xs text-warm-muted flex-1 truncate">
                  {fb.correction_text || fb.error_type}
                </span>
                <span className="text-[10px] text-warm-faint">
                  {fb.error_type}
                </span>
                {fb.is_active === 0 ? (
                  <button
                    onClick={() => reactivateMutation.mutate(fb.id)}
                    className="w-5 h-5 rounded-full hover:bg-warm-accent/10 flex items-center justify-center text-warm-faint hover:text-warm-accent transition-colors"
                    title="重新激活"
                  >
                    <RotateCcw size={10} />
                  </button>
                ) : (
                  <button
                    onClick={() => deleteMutation.mutate(fb.id)}
                    className="w-5 h-5 rounded-full hover:bg-red-400/10 flex items-center justify-center text-warm-faint hover:text-red-400 transition-colors"
                    title="删除"
                  >
                    <Trash2 size={10} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
