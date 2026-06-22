import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TreePine, AlertTriangle, Heart } from 'lucide-react'
import { insightApi } from '../api'
import EmotionSeason from '../components/insight/EmotionSeason'

type TabKey = 'emotion'

const TABS: { key: TabKey; label: string; icon: typeof TreePine; color: string }[] = [
  { key: 'emotion', label: '情绪四季', icon: TreePine, color: '#D4856A' },
]

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '12px 16px', borderRadius: 12,
      background: 'rgba(196,107,107,0.08)',
      border: '1px solid rgba(196,107,107,0.3)',
      color: '#C46B6B', fontSize: 13,
    }}>
      <AlertTriangle size={16} />
      <span>数据加载失败：{message}</span>
    </div>
  )
}

export default function Insight() {
  const [activeTab, setActiveTab] = useState<TabKey>('emotion')
  const [selectedYear, setSelectedYear] = useState<number | undefined>(undefined)

  const { data: emotionData, isLoading: emotionLoading, isError: emotionError, error: emotionErr } = useQuery({
    queryKey: ['insight', 'emotion-season', selectedYear],
    queryFn: async () => {
      const res = await insightApi.getEmotionSeason({ year: selectedYear })
      return res.data
    },
  })

  // 后端返回的实际年份（可能因回退而与 selectedYear 不同）
  const actualYear = emotionData?.year ?? selectedYear ?? new Date().getFullYear()
  const availableYears: number[] = emotionData?.available_years ?? []

  // 年份切换
  const handlePrevYear = useCallback(() => {
    const current = actualYear
    const idx = availableYears.indexOf(current)
    if (idx > 0) {
      setSelectedYear(availableYears[idx - 1])
    } else {
      setSelectedYear(current - 1)
    }
  }, [actualYear, availableYears])

  const handleNextYear = useCallback(() => {
    const current = actualYear
    const idx = availableYears.indexOf(current)
    if (idx < availableYears.length - 1) {
      setSelectedYear(availableYears[idx + 1])
    } else {
      setSelectedYear(current + 1)
    }
  }, [actualYear, availableYears])

  const isLoading = emotionLoading

  const activeError = emotionError ? emotionErr : null

  const activeTabInfo = TABS.find(t => t.key === activeTab)!

  const emotionDays = emotionData?.daily?.length ?? 0
  const avgSentiment = (() => {
    const d = emotionData?.daily || []
    if (d.length === 0) return 0
    const sum = d.reduce((s: number, x: any) => s + (x.avg_sentiment || 0), 0)
    return sum / d.length
  })()

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        background: 'var(--color-warm-bg, #FAF7F4)',
      }}
    >
      {/* Top tab bar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px',
          borderBottom: '1px solid var(--color-warm-border, #E8E0D8)',
          background: '#FFFFFF',
        }}
      >
        {TABS.map(({ key, label, icon: Icon, color }) => {
          const isActive = activeTab === key
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 16px',
                borderRadius: 10,
                fontSize: 13,
                fontWeight: isActive ? 600 : 400,
                color: isActive ? '#2C2420' : '#7A6E64',
                background: isActive ? 'rgba(212,133,106,0.10)' : 'transparent',
                border: '1px solid',
                borderColor: isActive ? 'rgba(212,133,106,0.3)' : 'transparent',
                cursor: 'pointer',
                transition: 'background 0.15s ease, color 0.15s ease, border-color 0.15s ease',
                fontFamily: "'Source Serif 4', Georgia, serif",
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = 'rgba(232,224,216,0.4)'
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = 'transparent'
              }}
            >
              <Icon size={15} style={{ color: isActive ? '#D4856A' : '#B5A99E' }} />
              <span>{label}</span>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  backgroundColor: color,
                  opacity: isActive ? 1 : 0.5,
                }}
              />
            </button>
          )
        })}

        {/* 右侧状态 */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#2C2420' }}>
          {!isLoading && !activeError && (
            <>
              <span style={{
                color: '#D4856A',
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 600,
              }}>{emotionDays}</span>
              <span>天情绪记录</span>
            </>
          )}
        </div>
      </div>

      {/* 顶部摘要卡 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 14,
        padding: '14px 16px 16px 16px',
        borderBottom: '1px solid var(--color-warm-border, #E8E0D8)',
        background: 'var(--color-warm-bg, #FAF7F4)',
      }}>
        {/* 情绪 */}
        <div style={{
          padding: '12px 14px',
          borderRadius: 12,
          background: '#FFFFFF',
          border: '1px solid #E8E0D8',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <Heart size={14} style={{ color: '#D4856A', opacity: 0.6 }} />
            <span style={{ fontSize: 11, color: '#7A6E64', fontFamily: "'Source Serif 4', Georgia, serif" }}>情绪记录</span>
          </div>
          <div style={{
            fontSize: 20,
            fontWeight: 600,
            color: '#D4856A',
            fontFamily: "'JetBrains Mono', monospace",
            lineHeight: 1.2,
          }}>
            {emotionDays}
          </div>
          <div style={{ fontSize: 11, color: '#7A6E64', marginTop: 6 }}>
            平均 <span style={{
              color: avgSentiment >= 0 ? '#D4856A' : '#C46B6B',
              fontWeight: 600,
            }}>{avgSentiment >= 0 ? '+' : ''}{avgSentiment.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Visualization Area */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '0 12px 12px',
        background: 'var(--color-warm-bg, #FAF7F4)',
      }}>
        {activeError ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 280 }}>
            <ErrorBanner message={(activeError as Error)?.message || '未知错误'} />
          </div>
        ) : isLoading ? (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 280 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: activeTabInfo.color,
                  opacity: 0.3,
                  animation: 'pulse 1.4s ease-in-out infinite',
                }}
              />
              <span style={{ fontSize: 13, color: '#B5A99E' }}>加载中</span>
            </div>
          </div>
        ) : (
          <>
            {activeTab === 'emotion' && emotionData && (
              <EmotionSeason
                daily={emotionData.daily}
                monthlyAvg={emotionData.monthly_avg}
                year={actualYear}
                onPrevYear={handlePrevYear}
                onNextYear={handleNextYear}
                availableYears={availableYears}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
