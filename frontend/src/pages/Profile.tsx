import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Hash, Clock, TrendingUp, AlertCircle, GitBranch, ArrowUpRight, MessageSquare, BookOpen, UserCircle, Sparkles, Brain, Loader2, History, ArrowLeft } from 'lucide-react'
import PageContainer from '../components/layout/PageContainer'
import PageHeader from '../components/layout/PageHeader'
import { profileApi } from '../api'
import type { ProfileFragment, ProfileChange, ChangeType, PortraitModule, PortraitRecord, PortraitVersionItem } from '../types'

const CONFIDENCE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  explicit: { label: '明确', color: 'text-green-500', bg: 'bg-green-400/15 border-green-400/30' },
  frequent: { label: '频繁', color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/30' },
  implied: { label: '暗示', color: 'text-yellow-600', bg: 'bg-yellow-400/10 border-yellow-400/30' },
  inferred: { label: '推断', color: 'text-warm-muted', bg: 'bg-gray-400/10 border-gray-400/30' },
}

const CHANGE_TYPE_CONFIG: Record<ChangeType, { label: string; color: string; bg: string }> = {
  habit_fading: { label: '习惯消退', color: 'text-orange-500', bg: 'bg-orange-400/10 border-orange-400/30' },
  trait_shift: { label: '特质转变', color: 'text-red-500', bg: 'bg-red-400/10 border-red-400/30' },
  preference_change: { label: '偏好变化', color: 'text-blue-400', bg: 'bg-blue-400/10 border-blue-400/30' },
  decision_pattern: { label: '决策模式', color: 'text-green-500', bg: 'bg-green-400/15 border-green-400/30' },
}

type TabKey = 'profile' | 'changes' | 'detailed' | 'deep'

export default function Profile() {
  const [activeTab, setActiveTab] = useState<TabKey>('profile')
  const navigate = useNavigate()

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: async () => {
      try {
        const res = await profileApi.getProfiles()
        return Array.isArray(res.data) ? res.data : []
      } catch {
        return []
      }
    },
  })

  const { data: changes = [], isLoading: changesLoading } = useQuery({
    queryKey: ['profile-changes'],
    queryFn: async () => {
      try {
        const res = await profileApi.getChanges()
        return res.data || []
      } catch {
        return []
      }
    },
  })

  const sortedChanges = useMemo(() =>
    [...changes].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  , [changes])

  return (
    <PageContainer className="h-full flex flex-col !p-0 !max-w-none">
      {/* 标签页切换 */}
      <div className="flex items-center gap-1 px-6 pt-4 border-b border-warm-border bg-warm-card/30">
        <button
          onClick={() => setActiveTab('profile')}
          className={`px-4 py-2 text-sm rounded-t-lg transition-colors ${
            activeTab === 'profile'
              ? 'bg-warm-card text-warm-accent border-b-2 border-warm-accent'
              : 'text-warm-muted hover:text-warm-text'
          }`}
        >
          画像片段
        </button>
        <button
          onClick={() => setActiveTab('detailed')}
          className={`px-4 py-2 text-sm rounded-t-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'detailed'
              ? 'bg-warm-card text-warm-accent border-b-2 border-warm-accent'
              : 'text-warm-muted hover:text-warm-text'
          }`}
        >
          <Sparkles size={14} />
          懂你细节
        </button>
        <button
          onClick={() => setActiveTab('deep')}
          className={`px-4 py-2 text-sm rounded-t-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'deep'
              ? 'bg-warm-card text-warm-accent border-b-2 border-warm-accent'
              : 'text-warm-muted hover:text-warm-text'
          }`}
        >
          <Brain size={14} />
          灵魂洞察
        </button>
        <button
          onClick={() => setActiveTab('changes')}
          className={`px-4 py-2 text-sm rounded-t-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'changes'
              ? 'bg-warm-card text-warm-accent border-b-2 border-warm-accent'
              : 'text-warm-muted hover:text-warm-text'
          }`}
        >
          <GitBranch size={14} />
          变化历史
          {changes.length > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-warm-accent/30 text-warm-highlight-text">
              {changes.length}
            </span>
          )}
        </button>
        <div className="flex-1" />
        <button
          onClick={() => navigate('/character')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-warm-input text-warm-muted hover:text-warm-text transition-colors text-sm"
          title="查看人物总览"
        >
          <UserCircle size={16} className="text-warm-accent" style={{ animation: 'pulse-soft 2s ease-in-out infinite' }} />
          <span>人物总览</span>
        </button>
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'profile' ? (
          <ProfileTab profiles={profiles} isLoading={isLoading} />
        ) : activeTab === 'detailed' ? (
          <PortraitTab portraitType="detailed" />
        ) : activeTab === 'deep' ? (
          <PortraitTab portraitType="deep" />
        ) : (
          <ChangesTab changes={sortedChanges} isLoading={changesLoading} />
        )}
      </div>
    </PageContainer>
  )
}

function ProfileTab({
  profiles,
  isLoading,
}: {
  profiles: ProfileFragment[]
  isLoading: boolean
}) {
  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto">
        <PageHeader
          title="画像片段"
          description={`${profiles.length} 个画像片段`}
          icon={<Hash size={20} />}
        />

        {isLoading ? (
          <div className="flex items-center justify-center h-full text-warm-faint">
            加载中...
          </div>
        ) : profiles.length === 0 ? (
          <div className="text-center text-warm-faint py-12 empty-state">
            暂无画像数据
          </div>
        ) : (
          <div className="space-y-3">
            {profiles.map(fragment => (
              <FragmentCard key={fragment.id} fragment={fragment} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ChangesTab({ changes, isLoading }: { changes: ProfileChange[]; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-warm-faint">
        加载中...
      </div>
    )
  }

  if (changes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-warm-faint">
        <div className="text-center">
          <GitBranch size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-lg mb-2">暂无变化记录</p>
          <p className="text-sm">当画像数据发生变化时，记录将显示在这里</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto">
        <PageHeader
          title="变化历史"
          description={`${changes.length} 条记录`}
          icon={<GitBranch size={20} />}
        />

        <div className="relative">
          <div className="absolute left-[7px] top-2 bottom-2 w-0.5 bg-warm-input" />

          <div className="space-y-4">
            {changes.map((change, index) => (
              <ChangeTimelineItem key={change.id} change={change} index={index} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ChangeTimelineItem({ change, index }: { change: ProfileChange; index: number }) {
  const typeConfig = CHANGE_TYPE_CONFIG[change.change_type] || CHANGE_TYPE_CONFIG.preference_change
  const ref = useRef<HTMLDivElement>(null)
  const nodeRef = useRef<HTMLDivElement>(null)
  const [isInView, setIsInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true)
          observer.unobserve(el)
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -20px 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      className={`relative pl-7 timeline-item-hidden ${isInView ? 'timeline-item-visible' : ''}`}
      style={isInView ? { animationDelay: `${index * 120}ms` } : undefined}
    >
      {/* 时间线节点 */}
      <div
        ref={nodeRef}
        className={`absolute left-0 top-2.5 w-3.5 h-3.5 rounded-full border-2 timeline-node-hidden ${isInView ? 'timeline-node-visible' : ''} ${
        change.change_type === 'habit_fading' ? 'border-orange-400 bg-orange-400/20' :
        change.change_type === 'trait_shift' ? 'border-red-400 bg-red-400/20' :
        change.change_type === 'preference_change' ? 'border-blue-400 bg-blue-400/20' :
        'border-green-400 bg-green-400/20'
      }`}
      style={isInView ? { animationDelay: `${index * 120 + 100}ms` } : undefined}
    />

      <div className="rounded-xl section-card p-4 hover:border-warm-border transition-colors">
        <div className="flex items-center gap-2 mb-2">
          <span className={`text-xs px-2 py-0.5 rounded-full border ${typeConfig.bg} ${typeConfig.color}`}>
            {typeConfig.label}
          </span>
          <span className="text-xs text-warm-faint flex items-center gap-1">
            <Clock size={10} />
            {new Date(change.created_at).toLocaleString('zh-CN')}
          </span>
        </div>
        <p className="text-sm text-warm-text leading-relaxed">{change.description}</p>
        {change.contact_name && (
          <p className="text-xs text-warm-faint mt-0.5">联系人: {change.contact_name}</p>
        )}
      </div>
    </div>
  )
}

function FragmentCard({ fragment }: { fragment: ProfileFragment }) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()
  const conf = CONFIDENCE_CONFIG[fragment.confidence] || CONFIDENCE_CONFIG.inferred

  const sourceInfo = useMemo(() => {
    const src = fragment.source
    if (!src) return null
    const colonIdx = src.indexOf(':')
    if (colonIdx === -1) return { label: src, type: 'unknown' as const, id: src }
    const type = src.slice(0, colonIdx)
    const id = src.slice(colonIdx + 1)
    if (type === 'diary') return { label: '查看日记', type: 'diary' as const, id }
    if (type === 'chat') return { label: '查看对话', type: 'chat' as const, id }
    return { label: src, type: 'unknown' as const, id: src }
  }, [fragment.source])

  const handleSourceClick = () => {
    if (!sourceInfo) return
    if (sourceInfo.type === 'diary') {
      navigate(`/diary?id=${sourceInfo.id}`)
    } else if (sourceInfo.type === 'chat') {
      navigate(`/?session=${sourceInfo.id}`)
    }
  }

  return (
    <div className="rounded-xl section-card overflow-hidden transition-colors">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-4 -m-4 mb-0"
      >
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-sm text-warm-text leading-relaxed">
              {fragment.content}
            </p>
            <div className="flex items-center gap-2 mt-2 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full border ${conf.bg} ${conf.color}`}>
                {conf.label}
              </span>
              <span className="text-xs text-warm-faint flex items-center gap-1">
                <TrendingUp size={10} />
                {fragment.frequency}
              </span>
            </div>
          </div>
          <ChevronRight
            size={16}
            className={`text-warm-faint shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
          />
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 border-t border-warm-border/50 pt-3 space-y-3">
          {/* 证据列表 */}
          {fragment.evidence.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-warm-muted mb-1.5">证据</h4>
              <ul className="space-y-1">
                {fragment.evidence.map((ev, i) => (
                  <li key={i} className="text-xs text-warm-text flex items-start gap-1.5">
                    <span className="text-warm-faint mt-0.5">•</span>
                    <span>{ev}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 来源跳转 */}
          {sourceInfo && (
            <button
              onClick={handleSourceClick}
              className="flex items-center gap-1.5 text-xs text-warm-accent hover:text-warm-accent-hover transition-colors group"
            >
              {sourceInfo.type === 'diary' ? <BookOpen size={12} /> : <MessageSquare size={12} />}
              <span>{sourceInfo.label}</span>
              <ArrowUpRight size={10} className="group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
            </button>
          )}

          {/* 信号频率 */}
          <div className="flex items-center gap-4 text-xs text-warm-muted">
            <span className="flex items-center gap-1">
              <TrendingUp size={10} />
              信号频率: {fragment.frequency}
            </span>
          </div>

          {/* 时间范围 */}
          <div className="flex items-center gap-4 text-xs text-warm-muted">
            <span className="flex items-center gap-1">
              <Clock size={10} />
              首次: {fragment.first_seen}
            </span>
            <span className="flex items-center gap-1">
              <Clock size={10} />
              更新: {fragment.last_updated}
            </span>
          </div>

          {/* 变化叙事 */}
          {fragment.change_narrative && (
            <div className="p-3 rounded-lg bg-orange-400/15 border border-orange-500/30">
              <div className="flex items-center gap-1.5 mb-1">
                <AlertCircle size={12} className="text-orange-500" />
                <span className="text-xs font-medium text-orange-500">变化叙事</span>
              </div>
              <p className="text-xs text-orange-300/80">{fragment.change_narrative}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PortraitTab({ portraitType }: { portraitType: 'detailed' | 'deep' }) {
  const [generating, setGenerating] = useState(false)
  const [showVersions, setShowVersions] = useState(false)
  const [viewingVersionId, setViewingVersionId] = useState<string | null>(null)
  const [viewingVersion, setViewingVersion] = useState<PortraitRecord | null>(null)
  const [loadingVersion, setLoadingVersion] = useState(false)

  const { data: records = [], isLoading, refetch } = useQuery({
    queryKey: ['portrait-records', portraitType],
    queryFn: async () => {
      try {
        const res = await profileApi.getPortraitRecords(portraitType)
        return (res.data || []) as PortraitRecord[]
      } catch {
        return [] as PortraitRecord[]
      }
    },
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
    enabled: showVersions,
  })

  const currentRecord = useMemo(() => {
    return records.find(r => r.is_current === 1)
  }, [records])

  const handleGenerate = useCallback(async () => {
    if (generating) return
    setGenerating(true)
    try {
      if (portraitType === 'detailed') {
        await profileApi.generateDetailedPortrait()
      } else {
        await profileApi.generateDeepPortrait()
      }
      await refetch()
    } catch (err) {
      console.error('生成画像失败', err)
    } finally {
      setGenerating(false)
    }
  }, [portraitType, generating, refetch])

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

  const handleBackToCurrent = useCallback(() => {
    setViewingVersionId(null)
    setViewingVersion(null)
  }, [])

  const isDetailed = portraitType === 'detailed'

  // 决定显示哪个画像数据：查看历史版本时显示历史版本，否则显示当前版本
  const displayRecord = viewingVersion || currentRecord
  const modules = displayRecord?.modules || []
  const reflectionQuestions = displayRecord?.extra?.reflection_questions || []
  const isViewingHistorical = viewingVersionId !== null && displayRecord?.is_current !== 1

  return (
    <div className="h-full overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto">
        <PageHeader
          title={isDetailed ? '懂你细节' : '灵魂洞察'}
          description={displayRecord ? `生成于 ${new Date(displayRecord.created_at).toLocaleString('zh-CN')}` : undefined}
          icon={isDetailed ? <Sparkles size={20} /> : <Brain size={20} />}
          actions={
            <div className="flex items-center gap-2">
              {isViewingHistorical && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-warm-input text-warm-muted">
                  历史版本
                </span>
              )}
            {isViewingHistorical && (
              <button
                onClick={handleBackToCurrent}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-warm-input text-warm-muted hover:text-warm-text transition-colors text-sm"
              >
                <ArrowLeft size={14} />
                返回当前版本
              </button>
            )}
            <button
              onClick={() => setShowVersions(!showVersions)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-warm-input text-warm-muted hover:text-warm-text transition-colors text-sm"
            >
              <History size={14} />
              历史版本
            </button>
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-warm-accent hover:bg-warm-accent-hover text-white transition-colors text-sm disabled:opacity-50"
            >
              {generating ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Sparkles size={14} />
              )}
              {generating ? '生成中...' : '生成画像'}
            </button>
          </div>
        }
        />

        {/* 历史版本面板 */}
        {showVersions && (
          <div className="mb-6 rounded-xl section-card overflow-hidden">
            <div className="p-4 border-b border-warm-border">
              <h3 className="text-sm font-medium text-warm-text flex items-center gap-2">
                <History size={14} className="text-warm-accent" />
                版本历史
              </h3>
            </div>
            {versionsLoading ? (
              <div className="flex items-center justify-center py-8 text-warm-faint">
                <Loader2 size={16} className="animate-spin mr-2" />
                加载中...
              </div>
            ) : versions.length === 0 ? (
              <div className="py-8 text-center text-warm-faint text-sm">
                暂无历史版本
              </div>
            ) : (
              <div className="divide-y divide-warm-border">
                {versions.map((v) => (
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
                          <span className="text-xs px-1.5 py-0.5 rounded-full bg-warm-accent/20 text-warm-highlight-text">
                            当前
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-warm-faint">
                        {v.modules_count} 个模块
                      </span>
                    </div>
                    <ChevronRight size={14} className="text-warm-faint shrink-0" />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {loadingVersion ? (
          <div className="flex items-center justify-center py-20 text-warm-faint">
            <Loader2 size={24} className="animate-spin mr-2" />
            加载版本...
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-20 text-warm-faint">
            <Loader2 size={24} className="animate-spin mr-2" />
            加载中...
          </div>
        ) : modules.length === 0 ? (
          <div className="text-center text-warm-faint py-20">
            {isDetailed ? (
              <Sparkles size={48} className="mx-auto mb-4 opacity-30" />
            ) : (
              <Brain size={48} className="mx-auto mb-4 opacity-30" />
            )}
            <p className="text-lg mb-2">暂无{isDetailed ? '细致型' : '深度型'}画像数据</p>
            <p className="text-sm mb-4">点击「生成画像」按钮，从你的行为数据中提取{isDetailed ? '具体偏好和习惯细节' : '行为模式和心理特质'}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {modules.map((module, index) => (
              <PortraitModuleCard
                key={index}
                module={module}
              />
            ))}

            {/* 深度型画像的反思问题 */}
            {!isDetailed && reflectionQuestions.length > 0 && (
              <div className="rounded-xl bg-warm-card border border-warm-border p-5 mt-6">
                <h3 className="flex items-center gap-2 text-sm font-medium text-warm-text mb-4">
                  <AlertCircle size={16} className="text-warm-accent" />
                  反思性问题
                </h3>
                <div className="space-y-3">
                  {reflectionQuestions.map((q, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-warm-text leading-relaxed">
                      <span className="text-warm-accent shrink-0 mt-0.5">Q{i + 1}</span>
                      <span>{q}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function PortraitModuleCard({ module }: { module: PortraitModule }) {
  const conf = CONFIDENCE_CONFIG[module.confidence] || CONFIDENCE_CONFIG.inferred

  return (
    <div className="rounded-xl section-card overflow-hidden">
      <div className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm font-medium text-warm-text">{module.title}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full border ${conf.bg} ${conf.color}`}>
            {conf.label}
          </span>
          {module.abstraction_level && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-warm-input text-warm-muted">
              {module.abstraction_level}
            </span>
          )}
          {module.evidence.length > 0 && (
            <span className="text-xs text-warm-faint flex items-center gap-1">
              <Hash size={10} />
              {module.evidence.length} 条证据
            </span>
          )}
        </div>
        <div className="text-sm text-warm-text leading-relaxed whitespace-pre-line">
          {module.content}
        </div>
        {module.evidence.length > 0 && (
          <div className="mt-3 pt-3 border-t border-warm-border/50">
            <h4 className="text-xs font-medium text-warm-muted mb-1.5">证据来源</h4>
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
