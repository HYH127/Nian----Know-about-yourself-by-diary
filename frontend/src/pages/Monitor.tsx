import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { RefreshCw, Check, ExternalLink, Loader2, BookOpen, Clock, Layers, Briefcase, Users, Heart, Wallet, Smile, Brain, Trophy, Film, Repeat, Pin, AlertTriangle, Activity, Pencil, Trash2, X } from 'lucide-react'
import { monitorApi, timelineApi, type RetrievalMode } from '../api'
import type { MonitorStatus, MonitorPending, MonitorUnconfirmedEvent } from '../types'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

const RETRIEVAL_MODE_STORAGE_KEY = 'nn_retrieval_mode'

const RETRIEVAL_MODE_LABELS: Record<RetrievalMode, string> = {
  rag: '仅 RAG',
  entity: '仅实体图',
  both: 'RAG + 实体图',
}

const EVENT_TYPE_ICONS: Record<string, React.ReactNode> = {
  work: <Briefcase size={18} />, social: <Users size={18} />, health: <Heart size={18} />, consumption: <Wallet size={18} />,
  emotion: <Smile size={18} />, decision: <Brain size={18} />, milestone: <Trophy size={18} />, media: <Film size={18} />, routine: <Repeat size={18} />,
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  diary: '日记', chat: '对话', media: '媒体', import: '导入', external: '外部', graph: '图谱',
}

function formatTimestamp(ts: string): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    if (isNaN(d.getTime())) return ts
    return d.toLocaleDateString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
    })
  } catch {
    return ts
  }
}

function StatusCard({
  title,
  icon,
  total,
  done,
  pending,
  doneLabel,
  pendingLabel,
}: {
  title: string
  icon: React.ReactNode
  total: number
  done: number
  pending: number
  doneLabel: string
  pendingLabel: string
}) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div className="stat-card flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-warm-accent/20 flex items-center justify-center text-warm-accent">
          {icon}
        </div>
        <h3 className="text-sm font-semibold text-warm-text">{title}</h3>
      </div>

      <div className="flex-1 space-y-3">
        <div className="flex justify-between text-xs">
          <span className="text-warm-muted">{doneLabel}</span>
          <span className="text-warm-text font-medium">{done} / {total}</span>
        </div>
        <div className="w-full h-2 bg-warm-input rounded-full overflow-hidden">
          <div
            className="h-full bg-warm-accent rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-warm-muted">{pendingLabel}</span>
          <span className="text-warm-accent font-medium">{pending}</span>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-warm-border text-xs text-warm-faint text-right">
        完成率 {pct}%
      </div>
    </div>
  )
}

function UnconfirmedEventItem({
  event,
  onConfirm,
  onNavigate,
  onEdit,
  onDelete,
}: {
  event: MonitorUnconfirmedEvent
  onConfirm: (id: string) => void
  onNavigate: (slug: string) => void
  onEdit: (event: MonitorUnconfirmedEvent) => void
  onDelete: (event: MonitorUnconfirmedEvent) => void
}) {
  const [confirming, setConfirming] = useState(false)
  const icon = EVENT_TYPE_ICONS[event.event_type] || <Pin size={18} />
  const sourceLabel = SOURCE_TYPE_LABELS[event.source_type] || event.source_type

  const handleConfirm = async () => {
    setConfirming(true)
    try {
      await onConfirm(event.id)
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="bg-warm-card rounded-xl border border-warm-border p-4 hover:border-warm-accent/40 transition-colors">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-lg bg-warm-input flex items-center justify-center shrink-0">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-warm-text leading-relaxed">{event.summary}</p>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="flex items-center gap-1 text-xs text-warm-faint">
              <Clock size={12} />
              {formatTimestamp(event.timestamp)}
            </span>
            <span className="px-1.5 py-0.5 bg-warm-input text-warm-muted text-xs rounded">
              {sourceLabel}
            </span>
            <span className="px-1.5 py-0.5 bg-warm-input text-warm-muted text-xs rounded">
              {event.event_type}
            </span>
          </div>
          {event.page_slugs.length > 0 && (
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              {event.page_slugs.map(slug => (
                <button
                  key={slug}
                  onClick={() => onNavigate(slug)}
                  className="flex items-center gap-1 px-2 py-0.5 bg-warm-accent/10 text-warm-accent text-xs rounded hover:bg-warm-accent/20 transition-colors"
                >
                  <ExternalLink size={10} />
                  {slug}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 flex items-center gap-1.5">
          <button
            onClick={() => onEdit(event)}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text hover:bg-warm-border transition-colors"
            title="编辑"
          >
            <Pencil size={12} />
            编辑
          </button>
          <button
            onClick={() => onDelete(event)}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs bg-warm-input text-red-400 rounded-lg hover:bg-red-50 hover:text-red-500 transition-colors"
            title="删除"
          >
            <Trash2 size={12} />
            删除
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-warm-accent text-white rounded-lg hover:bg-warm-accent-hover disabled:opacity-50 transition-colors"
          >
            {confirming ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Check size={12} />
            )}
            确认
          </button>
        </div>
      </div>
    </div>
  )
}

const EVENT_TYPES = [
  { value: 'work', label: '工作' },
  { value: 'social', label: '社交' },
  { value: 'health', label: '健康' },
  { value: 'consumption', label: '消费' },
  { value: 'emotion', label: '情绪' },
  { value: 'decision', label: '决策' },
  { value: 'milestone', label: '里程碑' },
  { value: 'media', label: '媒体' },
  { value: 'routine', label: '日常' },
]

function EditEventModal({
  event,
  onSave,
  onClose,
}: {
  event: MonitorUnconfirmedEvent
  onSave: (id: string, data: { summary?: string; event_type?: string; timestamp?: string; importance_score?: number }) => void
  onClose: () => void
}) {
  const [summary, setSummary] = useState(event.summary)
  const [eventType, setEventType] = useState(event.event_type)
  const [timestamp, setTimestamp] = useState(event.timestamp ? event.timestamp.slice(0, 16) : '')
  const [importanceScore, setImportanceScore] = useState(event.importance_score ?? 0.5)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(event.id, {
        summary: summary !== event.summary ? summary : undefined,
        event_type: eventType !== event.event_type ? eventType : undefined,
        timestamp: timestamp !== event.timestamp.slice(0, 16) ? timestamp + ':00' : undefined,
        importance_score: importanceScore !== (event.importance_score ?? 0.5) ? importanceScore : undefined,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-warm-card rounded-2xl border border-warm-border shadow-xl w-full max-w-md mx-4 p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-warm-text">编辑时间线事件</h3>
          <button onClick={onClose} className="text-warm-muted hover:text-warm-text transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-warm-muted mb-1">摘要</label>
            <textarea
              value={summary}
              onChange={e => setSummary(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 text-sm bg-warm-input border border-warm-border rounded-lg text-warm-text focus:outline-none focus:border-warm-accent resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-warm-muted mb-1">事件类型</label>
              <select
                value={eventType}
                onChange={e => setEventType(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-warm-input border border-warm-border rounded-lg text-warm-text focus:outline-none focus:border-warm-accent"
              >
                {EVENT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-warm-muted mb-1">重要度</label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={importanceScore}
                onChange={e => setImportanceScore(parseFloat(e.target.value))}
                className="w-full mt-2"
              />
              <div className="text-xs text-warm-muted text-center">{importanceScore.toFixed(1)}</div>
            </div>
          </div>

          <div>
            <label className="block text-xs text-warm-muted mb-1">时间</label>
            <input
              type="datetime-local"
              value={timestamp}
              onChange={e => setTimestamp(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-warm-input border border-warm-border rounded-lg text-warm-text focus:outline-none focus:border-warm-accent"
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-warm-muted hover:text-warm-text transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm bg-warm-accent text-white rounded-lg hover:bg-warm-accent-hover disabled:opacity-50 transition-colors"
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

function DeleteConfirmModal({
  event,
  onConfirm,
  onClose,
}: {
  event: MonitorUnconfirmedEvent
  onConfirm: (id: string) => void
  onClose: () => void
}) {
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await onConfirm(event.id)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-warm-card rounded-2xl border border-warm-border shadow-xl w-full max-w-sm mx-4 p-6" onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-warm-text mb-2">确认删除</h3>
        <p className="text-sm text-warm-muted mb-1">确定要删除这条时间线事件吗？</p>
        <p className="text-xs text-warm-faint mb-4 line-clamp-2">"{event.summary}"</p>
        <p className="text-xs text-red-400 mb-4">此操作不可撤销，关联的实体页面中的时间线引用也会被移除。</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-warm-muted hover:text-warm-text transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="px-4 py-2 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 transition-colors"
          >
            {deleting ? '删除中...' : '删除'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Monitor() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<MonitorStatus | null>(null)
  const [pending, setPending] = useState<MonitorPending | null>(null)
  const [failedCount, setFailedCount] = useState(0)
  const [retrying, setRetrying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingEvent, setEditingEvent] = useState<MonitorUnconfirmedEvent | null>(null)
  const [deletingEvent, setDeletingEvent] = useState<MonitorUnconfirmedEvent | null>(null)
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>(() => {
    try {
      const saved = localStorage.getItem(RETRIEVAL_MODE_STORAGE_KEY) as RetrievalMode | null
      return saved && ['rag', 'entity', 'both'].includes(saved) ? saved : 'both'
    } catch {
      return 'both'
    }
  })

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, pendingRes] = await Promise.all([
        monitorApi.getStatus(),
        monitorApi.getPending(),
      ])
      setStatus(statusRes.data)
      setPending(pendingRes.data)
      setError(null)

      // Fetch failed diaries count
      try {
        const failedRes = await monitorApi.getFailedDiaries()
        setFailedCount(failedRes.data.failed_count)
      } catch {
        // ignore
      }
    } catch {
      setError('加载监控数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [fetchData])

  const handleConfirm = async (eventId: string) => {
    await timelineApi.confirmEvent(eventId)
    fetchData()
  }

  const handleNavigateToKnowledge = (slug: string) => {
    navigate(`/knowledge?slug=${encodeURIComponent(slug)}`)
  }

  const handleEdit = async (eventId: string, data: { summary?: string; event_type?: string; timestamp?: string; importance_score?: number }) => {
    await monitorApi.updateEvent(eventId, data)
    setEditingEvent(null)
    fetchData()
    // Invalidate timeline page queries so it refreshes
    queryClient.invalidateQueries({ queryKey: ['timeline'] })
  }

  const handleDelete = async (eventId: string) => {
    await monitorApi.deleteEvent(eventId)
    setDeletingEvent(null)
    fetchData()
    // Invalidate timeline page queries so it refreshes
    queryClient.invalidateQueries({ queryKey: ['timeline'] })
    // Also invalidate knowledge/entity queries since timeline references may have changed
    queryClient.invalidateQueries({ queryKey: ['knowledge'] })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-warm-bg">
        <Loader2 size={32} className="animate-spin text-warm-accent" />
        <span className="ml-3 text-warm-muted">加载监控数据...</span>
      </div>
    )
  }

  if (error && !status) {
    return (
      <div className="flex items-center justify-center h-full bg-warm-bg">
        <div className="text-center">
          <p className="text-red-400 mb-3">{error}</p>
          <button
            onClick={fetchData}
            className="px-4 py-2 text-sm bg-warm-accent text-white rounded-lg hover:bg-warm-accent-hover transition-colors btn-primary"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  return (
    <PageContainer>
      <PageHeader
        title="系统监控"
        icon={<Activity size={20} />}
        actions={
          <button
            onClick={fetchData}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors"
          >
            <RefreshCw size={14} />
            刷新
          </button>
        }
      />

      {/* 全局检索模式切换（影响对话页面的默认检索模式） */}
      <div className="mb-6 p-4 rounded-xl card-base border border-warm-border/60">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-semibold text-warm-text">对话检索模式</h3>
            <p className="text-xs text-warm-faint mt-0.5">设置对话页面的默认检索方式，用于对比 RAG / 实体图 / 两者结合的效果</p>
          </div>
          <div className="flex items-center gap-1.5">
            {(Object.keys(RETRIEVAL_MODE_LABELS) as RetrievalMode[]).map(mode => (
              <button
                key={mode}
                onClick={() => {
                  setRetrievalMode(mode)
                  try { localStorage.setItem(RETRIEVAL_MODE_STORAGE_KEY, mode) } catch {}
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  retrievalMode === mode
                    ? 'bg-warm-accent text-white shadow-elevated-1'
                    : 'bg-warm-input text-warm-muted hover:text-warm-text border border-warm-border/50'
                }`}
              >
                {RETRIEVAL_MODE_LABELS[mode]}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="space-y-6">

        {/* Status Cards */}
        {status && (
          <div className="grid grid-cols-3 gap-4">
            <StatusCard
              title="日记处理"
              icon={<BookOpen size={16} />}
              total={status.diaries.total}
              done={status.diaries.processed}
              pending={status.diaries.pending}
              doneLabel="已处理"
              pendingLabel="待处理"
            />
            <StatusCard
              title="时间线确认"
              icon={<Clock size={16} />}
              total={status.timeline_events.total}
              done={status.timeline_events.confirmed}
              pending={status.timeline_events.unconfirmed}
              doneLabel="已确认"
              pendingLabel="待确认"
            />
            <StatusCard
              title="实体编译"
              icon={<Layers size={16} />}
              total={status.pages.total}
              done={status.pages.compiled}
              pending={status.pages.uncompiled}
              doneLabel="已编译"
              pendingLabel="未编译"
            />
          </div>
        )}

        {/* Portraits Summary */}
        {status && (status.portraits.detailed > 0 || status.portraits.deep > 0) && (
          <div className="bg-warm-card rounded-xl border border-warm-border p-4">
            <h3 className="text-sm font-semibold text-warm-text mb-2">画像记录</h3>
            <div className="flex gap-4">
              {status.portraits.detailed > 0 && (
                <span className="px-3 py-1 bg-warm-accent/10 text-warm-accent text-xs rounded-lg">
                  详细画像 × {status.portraits.detailed}
                </span>
              )}
              {status.portraits.deep > 0 && (
                <span className="px-3 py-1 bg-warm-accent/10 text-warm-accent text-xs rounded-lg">
                  深度画像 × {status.portraits.deep}
                </span>
              )}
            </div>
          </div>
        )}

        {/* Failed Diaries Retry */}
        {failedCount > 0 && (
          <div className="bg-amber-50 rounded-xl border border-amber-200 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle size={20} className="text-amber-600 shrink-0" />
                <div>
                  <h3 className="text-sm font-semibold text-amber-800">处理失败的日记</h3>
                  <p className="text-xs text-amber-600 mt-0.5">{failedCount} 条日记未完成处理（摘要提取失败）</p>
                </div>
              </div>
              <button
                onClick={async () => {
                  setRetrying(true)
                  try {
                    const res = await monitorApi.retryFailed()
                    const { succeeded, still_failed } = res.data
                    setFailedCount(still_failed)
                    fetchData()
                    alert(`重试完成：成功 ${succeeded} 条，仍失败 ${still_failed} 条`)
                  } catch {
                    alert('重试失败，请稍后再试')
                  } finally {
                    setRetrying(false)
                  }
                }}
                disabled={retrying}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 transition-colors"
              >
                {retrying ? (
                  <>
                    <Loader2 size={12} className="animate-spin" />
                    重试中...
                  </>
                ) : (
                  <>
                    <RefreshCw size={12} />
                    重试全部
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Unconfirmed Timeline Events */}
        <div>
          <h2 className="text-base font-semibold text-warm-text mb-3">待确认时间线</h2>
          {pending && pending.unconfirmed_events.length > 0 ? (
            <div className="space-y-3">
              {pending.unconfirmed_events.map(event => (
                <UnconfirmedEventItem
                  key={event.id}
                  event={event}
                  onConfirm={handleConfirm}
                  onNavigate={handleNavigateToKnowledge}
                  onEdit={setEditingEvent}
                  onDelete={setDeletingEvent}
                />
              ))}
            </div>
          ) : (
            <div className="empty-state section-card">
              <Clock size={32} className="mb-2 opacity-30" />
              <p className="text-sm">暂无待确认的时间线事件</p>
            </div>
          )}
        </div>
      </div>

      {editingEvent && (
        <EditEventModal
          event={editingEvent}
          onSave={handleEdit}
          onClose={() => setEditingEvent(null)}
        />
      )}
      {deletingEvent && (
        <DeleteConfirmModal
          event={deletingEvent}
          onConfirm={handleDelete}
          onClose={() => setDeletingEvent(null)}
        />
      )}
    </PageContainer>
  )
}
