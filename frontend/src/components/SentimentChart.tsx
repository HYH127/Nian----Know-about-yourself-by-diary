import { useState, useEffect, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { Calendar } from 'lucide-react'
import { timelineApi } from '../api'

type Period = 'week' | 'month' | 'all' | 'custom'

const PERIOD_LABELS: Record<Period, string> = {
  week: '周',
  month: '月',
  all: '总',
  custom: '自选',
}

interface SentimentDataPoint {
  date: string
  avg_sentiment: number
  count: number
}

function formatXAxisLabel(dateStr: string, period: Period) {
  const m = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return dateStr
  if (period === 'all' || period === 'custom') return `${parseInt(m[2])}.${parseInt(m[3])}`
  return `${parseInt(m[2])}/${parseInt(m[3])}`
}

function CustomTooltip({ active, payload, period }: { active?: boolean; payload?: Array<{ payload: SentimentDataPoint }>; period: Period }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-warm-card border border-warm-border rounded-lg px-3 py-2 shadow-lg text-xs">
      <p className="text-warm-text font-medium">{d.date}</p>
      <p className="text-warm-muted">
        情绪值: <span className={d.avg_sentiment > 0.3 ? 'text-green-500' : d.avg_sentiment < -0.3 ? 'text-red-500' : 'text-warm-text'}>
          {d.avg_sentiment.toFixed(2)}
        </span>
      </p>
      <p className="text-warm-faint">事件数: {d.count}</p>
    </div>
  )
}

export default function SentimentChart() {
  const [period, setPeriod] = useState<Period>('week')
  const [data, setData] = useState<SentimentDataPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  const fetchData = useCallback((p: Period, start?: string, end?: string) => {
    let cancelled = false
    setLoading(true)

    let promise: Promise<{ data: SentimentDataPoint[] }>

    if (p === 'custom' && start && end) {
      // Use existing timeline API with date range, then aggregate on frontend
      promise = timelineApi.getEvents({ start_date: start, end_date: end, limit: 500 }).then(res => {
        // Aggregate sentiment by date
        const dateMap = new Map<string, { sum: number; count: number }>()
        for (const e of res.data) {
          if (e.sentiment == null) continue
          const ts = e.timestamp || ''
          const dateMatch = ts.match(/^(\d{4}-\d{2}-\d{2})/)
          if (!dateMatch) continue
          const date = dateMatch[1]
          const existing = dateMap.get(date) || { sum: 0, count: 0 }
          existing.sum += e.sentiment
          existing.count += 1
          dateMap.set(date, existing)
        }
        const aggregated = Array.from(dateMap.entries())
          .map(([date, { sum, count }]) => ({ date, avg_sentiment: sum / count, count }))
          .sort((a, b) => a.date.localeCompare(b.date))
        return { data: aggregated }
      })
    } else {
      promise = timelineApi.getSentimentStats(p === 'custom' ? 'all' : p)
    }

    promise
      .then(res => {
        if (!cancelled) setData(res.data)
      })
      .catch(() => {
        if (!cancelled) setData([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const cleanup = fetchData(period, customStart, customEnd)
    return cleanup
  }, [period, customStart, customEnd, fetchData])

  const handlePeriodChange = (p: Period) => {
    if (p === 'custom') {
      // Only switch to custom if dates are set
      if (customStart && customEnd) {
        setPeriod(p)
      } else {
        setPeriod(p) // Show date inputs
      }
    } else {
      setPeriod(p)
    }
  }

  const periods: Period[] = ['week', 'month', 'all', 'custom']

  return (
    <div className="rounded-2xl bg-warm-card/80 backdrop-blur-sm border border-warm-border/50 p-5 shadow-sm shadow-warm-shadow">
      <div className="flex items-center justify-between mb-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-warm-text">
          <div className="w-6 h-6 rounded-lg bg-warm-accent/15 flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-warm-accent" />
          </div>
          情绪趋势
        </h3>
        <div className="flex items-center gap-0.5 bg-warm-input/80 rounded-xl p-0.5 border border-warm-border/30">
          {periods.map(p => (
            <button
              key={p}
              onClick={() => handlePeriodChange(p)}
              className={`px-3 py-1 rounded-lg text-xs transition-all duration-200 btn-press ${
                period === p
                  ? 'bg-warm-accent text-white shadow-sm shadow-warm-shadow'
                  : 'text-warm-muted hover:text-warm-text'
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* Custom date range picker */}
      {period === 'custom' && (
        <div className="flex items-center gap-2 mb-4 animate-fade-in">
          <Calendar size={14} className="text-warm-muted shrink-0" />
          <input
            type="date"
            value={customStart}
            onChange={e => setCustomStart(e.target.value)}
            className="px-2.5 py-1 rounded-xl bg-warm-input border border-warm-border/50 text-xs text-warm-text focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all"
          />
          <span className="text-warm-faint text-xs">至</span>
          <input
            type="date"
            value={customEnd}
            onChange={e => setCustomEnd(e.target.value)}
            className="px-2.5 py-1 rounded-xl bg-warm-input border border-warm-border/50 text-xs text-warm-text focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all"
          />
          {customStart && customEnd && (
            <span className="text-xs text-warm-faint">
              {Math.ceil((new Date(customEnd).getTime() - new Date(customStart).getTime()) / 86400000) + 1}天
            </span>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center h-48 text-warm-faint text-sm">
          加载中...
        </div>
      ) : data.length === 0 ? (
        <div className="flex items-center justify-center h-48 text-warm-faint text-sm">
          {period === 'custom' && (!customStart || !customEnd) ? '请选择日期范围' : '暂无情绪数据'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="date"
              tickFormatter={(v: string) => formatXAxisLabel(v, period)}
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
            />
            <YAxis
              domain={[-1, 1]}
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
              tickLine={false}
              ticks={[-1, -0.5, 0, 0.5, 1]}
            />
            <Tooltip content={<CustomTooltip period={period} />} />
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
            <ReferenceLine y={0.3} stroke="rgba(74,222,128,0.2)" strokeDasharray="3 3" />
            <ReferenceLine y={-0.3} stroke="rgba(239,68,68,0.2)" strokeDasharray="3 3" />
            <Line
              type="monotone"
              dataKey="avg_sentiment"
              stroke="#a78bfa"
              strokeWidth={2}
              dot={{ r: 3, fill: '#a78bfa', stroke: '#1a1a2e', strokeWidth: 1 }}
              activeDot={{ r: 5, fill: '#a78bfa', stroke: '#fff', strokeWidth: 2 }}
              animationDuration={500}
              animationEasing="ease-in-out"
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-2 text-xs text-warm-faint">
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-green-400/40 inline-block" /> 积极 ( &gt; 0.3)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-white/15 inline-block" /> 中性
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-0.5 bg-red-400/40 inline-block" /> 消极 ( &lt; -0.3)
        </span>
      </div>
    </div>
  )
}
