import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserCircle, Sparkles, Hash, TrendingUp, BarChart3, Smile, Loader2 } from 'lucide-react'
import { profileApi } from '../api'
import type { ProfileFragment } from '../types'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

const CONFIDENCE_CONFIG: Record<string, { label: string; color: string }> = {
  explicit: { label: '明确', color: '#10b981' },
  frequent: { label: '频繁', color: '#3b82f4' },
  implied: { label: '暗示', color: '#ca8a04' },
  inferred: { label: '推断', color: '#8b6f64' },
}

const ACCENT_COLOR = '#E8A0BF'

export default function Character() {
  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ['profiles-all'],
    queryFn: async () => {
      try {
        const res = await profileApi.getProfiles()
        return Array.isArray(res.data) ? res.data : []
      } catch {
        return []
      }
    },
  })

  const { data: charSummary, isLoading: summaryLoading } = useQuery({
    queryKey: ['character-summary'],
    queryFn: async () => {
      try {
        const res = await profileApi.getCharacterSummary()
        return res.data
      } catch {
        return { traits: [], portrait: '暂无法生成人物面貌，请多记录一些日记。' }
      }
    },
    enabled: profiles.length > 0,
  })

  const profileAnalysis = useMemo(() => {
    const confidenceMap = new Map<string, number>()

    for (const p of profiles) {
      confidenceMap.set(p.confidence, (confidenceMap.get(p.confidence) || 0) + 1)
    }

    const explicitCount = confidenceMap.get('explicit') || 0
    const frequentCount = confidenceMap.get('frequent') || 0
    const highConf = explicitCount + frequentCount
    const reliability = profiles.length > 0 ? Math.round((highConf / profiles.length) * 100) : 0

    const confidenceData = Object.entries(CONFIDENCE_CONFIG).map(([key, cfg]) => ({
      key,
      label: cfg.label,
      color: cfg.color,
      count: confidenceMap.get(key) || 0,
    }))

    return { reliability, confidenceData }
  }, [profiles])

  return (
    <PageContainer className="max-w-4xl">
      <PageHeader
        title="人物画像"
        icon={<UserCircle size={20} />}
        description="基于全部画像片段的综合分析 · 由 AI 持续构建"
      />

      <div className="space-y-6">
        {/* 顶部横幅 */}
        <div className="rounded-2xl bg-gradient-to-br from-warm-highlight via-warm-card to-warm-bg border border-warm-border p-8 animate-fade-in">
          <div className="flex items-center gap-6">
            <div className="relative">
              <div className="w-20 h-20 rounded-full bg-warm-accent/20 flex items-center justify-center">
                <UserCircle size={48} className="text-warm-accent" />
              </div>
              <div className="absolute -inset-1 rounded-full border-2 border-warm-accent/30" style={{ animation: 'pulse-soft 2s ease-in-out infinite' }} />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-heading font-semibold text-warm-text">人物画像总览</h2>
              <p className="text-sm text-warm-muted mt-1">基于全部画像片段的综合分析 · 由 AI 持续构建</p>
              <div className="flex items-center gap-6 mt-4">
                <StatBadge icon={<Hash size={14} />} label="画像片段" value={profiles.length} />
                <StatBadge icon={<TrendingUp size={14} />} label="可信度" value={`${profileAnalysis.reliability}%`} />
              </div>
            </div>
          </div>
        </div>

        {isLoading ? (
          <div className="empty-state">
            <Loader2 size={32} className="animate-spin mb-2 opacity-30" />
            <p className="text-sm">加载中...</p>
          </div>
        ) : profiles.length === 0 ? (
          <div className="empty-state">
            <UserCircle size={48} className="mb-4 opacity-30" />
            <p className="text-lg mb-2">暂无画像数据</p>
            <p className="text-sm">开始记录日记后，人物画像将自动构建</p>
          </div>
        ) : (
          <>
            {/* 核心特质 - LLM 提炼 */}
            <div className="section-card">
              <h3 className="flex items-center gap-2 text-sm font-medium text-warm-text mb-3">
                <Sparkles size={16} className="text-warm-accent" />
                核心特质
                <span className="text-xs text-warm-faint font-normal ml-1">AI 提炼</span>
              </h3>
              {summaryLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={20} className="text-warm-accent animate-spin" />
                </div>
              ) : !charSummary?.traits?.length ? (
                <p className="text-sm text-warm-muted text-center py-8">数据积累中，暂无法提炼特质...</p>
              ) : (
                <div className="space-y-2.5">
                  {charSummary.traits.map((trait, i) => (
                    <div
                      key={trait.trait}
                      className="list-item animate-fade-in"
                      style={{ animationDelay: `${i * 80}ms` }}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm text-warm-text font-medium">{trait.trait}</span>
                        <span className="text-xs text-warm-muted">
                          {Math.round(trait.weight * 100)}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-warm-border/30 overflow-hidden mb-1.5">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.round(trait.weight * 100)}%`,
                            backgroundColor: ACCENT_COLOR,
                          }}
                        />
                      </div>
                      <p className="text-xs text-warm-muted leading-relaxed">{trait.evidence}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* AI 人格描述 - 哲学家式 */}
            <div className="section-card">
              <h3 className="flex items-center gap-2 text-sm font-medium text-warm-text mb-3">
                <Smile size={16} className="text-warm-accent" />
                人格面貌
                <span className="text-xs text-warm-faint font-normal ml-1">AI 深度思考</span>
              </h3>
              <div className="p-4 rounded-lg bg-warm-input border border-warm-border/50">
                {summaryLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 size={20} className="text-warm-accent animate-spin" />
                  </div>
                ) : (
                  <p className="text-sm text-warm-text leading-relaxed whitespace-pre-wrap">
                    {charSummary?.portrait || '正在生成人物面貌描述...'}
                  </p>
                )}
              </div>
            </div>

            {/* 可信度分布 */}
            <div className="section-card">
              <h3 className="flex items-center gap-2 text-sm font-medium text-warm-text mb-3">
                <BarChart3 size={16} className="text-warm-accent" />
                可信度分布
              </h3>
              <div className="space-y-2.5">
                {profileAnalysis.confidenceData.map(d => {
                  const maxCount = Math.max(...profileAnalysis.confidenceData.map(c => c.count), 1)
                  return (
                    <div key={d.key} className="space-y-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-warm-text">{d.label}</span>
                        <span className="text-warm-muted">{d.count}</span>
                      </div>
                      <div className="h-4 rounded-full bg-warm-border/30 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.round((d.count / maxCount) * 100)}%`,
                            backgroundColor: d.color,
                            minWidth: d.count > 0 ? '12px' : '0',
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </PageContainer>
  )
}

function StatBadge({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-warm-input border border-warm-border/50">
      <span className="text-warm-accent">{icon}</span>
      <div>
        <p className="text-xs text-warm-muted">{label}</p>
        <p className="text-sm font-semibold text-warm-text">{value}</p>
      </div>
    </div>
  )
}
