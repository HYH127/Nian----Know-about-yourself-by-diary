import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  StickyNote, Save, Clock, Pencil, X, Trash2,
  Utensils, Car, ShoppingBag, Gamepad2, Home, Heart, GraduationCap, MoreHorizontal,
  ChevronLeft, Plus, Loader2, Calendar, Edit3, Check, ArrowLeft, Receipt
} from 'lucide-react'
import PageContainer from '../components/layout/PageContainer'
import { quicknoteApi } from '../api'
import type { QuickNote, ExpenseRecord, ExpenseStats } from '../types'

// ── Category config ──
const EXPENSE_CATEGORIES = [
  { key: '餐饮', icon: Utensils, color: 'bg-warm-amber-light text-warm-amber', dot: 'bg-warm-amber' },
  { key: '交通', icon: Car, color: 'bg-warm-slate-light text-warm-slate', dot: 'bg-warm-slate' },
  { key: '购物', icon: ShoppingBag, color: 'bg-warm-highlight text-warm-accent-deep', dot: 'bg-warm-accent' },
  { key: '娱乐', icon: Gamepad2, color: 'bg-warm-sage-light text-warm-sage', dot: 'bg-warm-sage' },
  { key: '居住', icon: Home, color: 'bg-purple-50 text-purple-500', dot: 'bg-purple-400' },
  { key: '医疗', icon: Heart, color: 'bg-rose-50 text-rose-500', dot: 'bg-rose-400' },
  { key: '教育', icon: GraduationCap, color: 'bg-sky-50 text-sky-500', dot: 'bg-sky-400' },
  { key: '其他', icon: MoreHorizontal, color: 'bg-warm-input text-warm-muted', dot: 'bg-warm-faint' },
]

function getCategoryConfig(key: string) {
  return EXPENSE_CATEGORIES.find(c => c.key === key) || EXPENSE_CATEGORIES[7]
}

// ── Format helpers ──
function formatTime(isoStr: string) {
  const d = new Date(isoStr.replace(' ', 'T'))
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatMoney(n: number) {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ═══════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════
export default function QuickNotePage() {
  const [view, setView] = useState<'note' | 'expense'>('note')

  return (
    <PageContainer className="h-full flex flex-col !p-0 !max-w-none">
      <AnimatePresence mode="wait">
        {view === 'note' ? (
          <motion.div
            key="note"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full overflow-y-auto"
          >
            <NoteView onSwitchToExpense={() => setView('expense')} />
          </motion.div>
        ) : (
          <motion.div
            key="expense"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="h-full overflow-y-auto"
          >
            <ExpenseView onBack={() => setView('note')} />
          </motion.div>
        )}
      </AnimatePresence>
    </PageContainer>
  )
}

// ═══════════════════════════════════════════
// Note View — 随手记录（轻量居中流式布局）
// ═══════════════════════════════════════════
function NoteView({ onSwitchToExpense }: { onSwitchToExpense: () => void }) {
  const queryClient = useQueryClient()
  const [editContent, setEditContent] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editingContent, setEditingContent] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: notes = [] } = useQuery({
    queryKey: ['quicknotes'],
    queryFn: async () => {
      const res = await quicknoteApi.list(100, 0)
      return res.data
    },
  })

  const { data: selectedNote } = useQuery({
    queryKey: ['quicknote', selectedId],
    queryFn: async () => {
      if (!selectedId) return null
      const res = await quicknoteApi.get(selectedId)
      return res.data
    },
    enabled: !!selectedId,
  })

  const createMutation = useMutation({
    mutationFn: () => quicknoteApi.create(editContent.trim()),
    onSuccess: () => {
      setEditContent('')
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 2000)
      queryClient.invalidateQueries({ queryKey: ['quicknotes'] })
      textareaRef.current?.focus()
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedId) return
      await quicknoteApi.update(selectedId, editingContent.trim())
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quicknotes'] })
      queryClient.invalidateQueries({ queryKey: ['quicknote', selectedId] })
      setIsEditing(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => quicknoteApi.delete(id),
    onSuccess: () => {
      setSelectedId(null)
      setIsEditing(false)
      queryClient.invalidateQueries({ queryKey: ['quicknotes'] })
    },
  })

  const handleSave = () => {
    if (!editContent.trim()) return
    createMutation.mutate()
  }

  // Auto-save on blur: save when user has content and leaves the textarea
  const handleBlur = () => {
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current)
    if (editContent.trim() && !createMutation.isPending) {
      createMutation.mutate()
    }
  }

  const handleContentChange = (value: string) => {
    setEditContent(value)
  }

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current)
    }
  }, [])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  // ── Detail overlay ──
  if (selectedId && selectedNote) {
    return (
      <div className="max-w-xl mx-auto px-6 py-8">
        <button
          onClick={() => { setSelectedId(null); setIsEditing(false) }}
          className="flex items-center gap-1.5 text-sm text-warm-muted hover:text-warm-accent transition-colors mb-6 group"
        >
          <ArrowLeft size={15} className="group-hover:-translate-x-0.5 transition-transform" />
          返回
        </button>

        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-warm-accent/10 flex items-center justify-center">
              <StickyNote size={15} className="text-warm-accent" />
            </div>
            <div>
              <span className="text-xs text-warm-muted block">
                {formatTime(selectedNote.edited_at)}
              </span>
              <span className="text-[10px] text-warm-faint">
                创建于 {new Date(selectedNote.created_at.replace(' ', 'T')).toLocaleString('zh-CN')}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            {!isEditing ? (
              <>
                <button
                  onClick={() => { setEditingContent(selectedNote.content); setIsEditing(true) }}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-warm-accent hover:bg-warm-accent/10 transition-colors"
                >
                  <Pencil size={12} /> 编辑
                </button>
                <button
                  onClick={() => deleteMutation.mutate(selectedId)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-warm-faint hover:text-warm-danger hover:bg-warm-danger/5 transition-colors"
                >
                  <Trash2 size={12} />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => { if (editingContent.trim()) updateMutation.mutate() }}
                  disabled={!editingContent.trim() || updateMutation.isPending}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-warm-accent text-white text-xs font-medium disabled:opacity-40 transition-colors btn-primary"
                >
                  <Save size={12} /> {updateMutation.isPending ? '保存中...' : '保存'}
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-warm-input text-warm-muted text-xs hover:text-warm-text transition-colors"
                >
                  <X size={12} /> 取消
                </button>
              </>
            )}
          </div>
        </div>

        {isEditing ? (
          <textarea
            value={editingContent}
            onChange={e => setEditingContent(e.target.value)}
            className="w-full min-h-[260px] resize-y rounded-xl bg-warm-input/60 border border-warm-border/60 p-4 text-sm text-warm-text placeholder-warm-faint focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all leading-relaxed input-enhanced"
          />
        ) : (
          <div className="p-5 rounded-xl bg-warm-input/40 border border-warm-border/40">
            <p className="text-sm text-warm-text leading-relaxed whitespace-pre-wrap">
              {selectedNote.content}
            </p>
          </div>
        )}
      </div>
    )
  }

  // ── Main stream view ──
  return (
    <div className="max-w-xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-warm-accent/12 flex items-center justify-center">
            <StickyNote size={18} className="text-warm-accent" />
          </div>
          <h1 className="text-lg font-semibold text-warm-text font-heading">随手记</h1>
        </div>
        <button
          onClick={onSwitchToExpense}
          className="flex items-center gap-2 px-4 py-2 text-sm bg-warm-input text-warm-muted rounded-xl hover:bg-warm-accent/12 hover:text-warm-accent-deep transition-all btn-press border border-warm-border/50"
        >
          <Receipt size={15} />
          记账本
        </button>
      </div>

      {/* Input area — auto-save on blur + manual save */}
      <div className="relative mb-8">
        <textarea
          ref={textareaRef}
          value={editContent}
          onChange={e => handleContentChange(e.target.value)}
          onBlur={handleBlur}
          placeholder="此刻在想什么..."
          rows={3}
          className="w-full resize-none rounded-2xl bg-warm-input/50 border border-warm-border/50 px-5 py-4 pb-10 text-sm text-warm-text placeholder-warm-faint/50 focus:outline-none focus:border-warm-accent/40 focus:ring-4 focus:ring-warm-accent/8 transition-all leading-relaxed input-enhanced"
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          {createMutation.isPending && (
            <Loader2 size={12} className="animate-spin text-warm-accent" />
          )}
          {saveSuccess && (
            <motion.span
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-xs text-warm-success font-medium"
            >
              已保存
            </motion.span>
          )}
          {editContent.trim() && !saveSuccess && !createMutation.isPending && (
            <button
              onClick={handleSave}
              className="flex items-center gap-1 px-3 py-1 rounded-lg bg-warm-accent hover:bg-warm-accent-hover text-white transition-all btn-primary btn-press text-xs font-medium"
            >
              <Save size={11} />
              保存
            </button>
          )}
        </div>
      </div>

      {/* Notes stream */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 mb-3">
          <Clock size={13} className="text-warm-faint" />
          <span className="text-xs text-warm-faint font-medium">历史记录</span>
          {notes.length > 0 && (
            <span className="text-[11px] text-warm-faint/60">{notes.length} 条</span>
          )}
        </div>

        {notes.length === 0 ? (
          <div className="py-12 text-center">
            <StickyNote size={32} className="mx-auto mb-3 text-warm-faint/30" />
            <p className="text-sm text-warm-faint/60">写下你的第一条想法</p>
          </div>
        ) : (
          <AnimatePresence>
            {notes.map((note, index) => (
              <motion.button
                key={note.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.02, duration: 0.2 }}
                onClick={() => setSelectedId(note.id)}
                className="w-full text-left group px-4 py-3.5 rounded-xl hover:bg-warm-input/50 transition-all duration-150"
              >
                <p className="text-sm text-warm-text/85 leading-relaxed line-clamp-3 group-hover:text-warm-text transition-colors">
                  {note.content}
                </p>
                <div className="flex items-center gap-1.5 mt-2">
                  <Clock size={10} className="text-warm-faint/60" />
                  <span className="text-[11px] text-warm-faint/60">
                    {formatTime(note.edited_at)}
                  </span>
                </div>
              </motion.button>
            ))}
          </AnimatePresence>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════
// Expense View — 记账本（居中单栏布局）
// ═══════════════════════════════════════════
function ExpenseView({ onBack }: { onBack: () => void }) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('餐饮')
  const [description, setDescription] = useState('')
  const [note, setNote] = useState('')
  const [expenseDate, setExpenseDate] = useState(new Date().toISOString().split('T')[0])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editAmount, setEditAmount] = useState('')
  const [editCategory, setEditCategory] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editNote, setEditNote] = useState('')
  const [editDate, setEditDate] = useState('')

  const now = new Date()
  const monthStart = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
  const monthEnd = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

  const { data: expenses = [] } = useQuery({
    queryKey: ['expenses'],
    queryFn: async () => {
      const res = await quicknoteApi.listExpenses({ limit: 200 })
      return res.data
    },
  })

  const { data: stats } = useQuery({
    queryKey: ['expenseStats', monthStart, monthEnd],
    queryFn: async () => {
      const res = await quicknoteApi.getExpenseStats({ start_date: monthStart, end_date: monthEnd })
      return res.data
    },
  })

  const createMutation = useMutation({
    mutationFn: () => quicknoteApi.createExpense({
      amount: parseFloat(amount),
      category,
      description: description.trim(),
      note: note.trim() || undefined,
      expense_date: expenseDate,
    }),
    onSuccess: () => {
      setAmount('')
      setDescription('')
      setNote('')
      setExpenseDate(new Date().toISOString().split('T')[0])
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['expenseStats'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editingId) return
      await quicknoteApi.updateExpense(editingId, {
        amount: parseFloat(editAmount),
        category: editCategory,
        description: editDescription.trim(),
        note: editNote.trim() || undefined,
        expense_date: editDate,
      })
    },
    onSuccess: () => {
      setEditingId(null)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['expenseStats'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => quicknoteApi.deleteExpense(id),
    onSuccess: () => {
      setEditingId(null)
      queryClient.invalidateQueries({ queryKey: ['expenses'] })
      queryClient.invalidateQueries({ queryKey: ['expenseStats'] })
    },
  })

  const handleAdd = () => {
    const num = parseFloat(amount)
    if (isNaN(num) || num <= 0) return
    createMutation.mutate()
  }

  const handleStartEdit = (record: ExpenseRecord) => {
    setEditingId(record.id)
    setEditAmount(String(record.amount))
    setEditCategory(record.category)
    setEditDescription(record.description)
    setEditNote(record.note || '')
    setEditDate(record.expense_date)
  }

  // Group expenses by date
  const groupedExpenses = expenses.reduce<Record<string, ExpenseRecord[]>>((acc, e) => {
    const d = e.expense_date
    if (!acc[d]) acc[d] = []
    acc[d].push(e)
    return acc
  }, {})
  const sortedDates = Object.keys(groupedExpenses).sort((a, b) => b.localeCompare(a))

  // Category breakdown bar
  const renderCategoryBar = (breakdown: ExpenseStats['category_breakdown']) => {
    if (!breakdown.length) return null
    return (
      <div className="flex rounded-full overflow-hidden h-2.5 bg-warm-input">
        {breakdown.map((item, i) => {
          const cfg = getCategoryConfig(item.category)
          return (
            <motion.div
              key={item.category}
              initial={{ width: 0 }}
              animate={{ width: `${item.percentage}%` }}
              transition={{ delay: i * 0.05, duration: 0.4 }}
              className={`${cfg.dot} opacity-80`}
              title={`${item.category}: ${item.percentage}%`}
            />
          )
        })}
      </div>
    )
  }

  return (
    <div className="max-w-xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={onBack}
          className="w-9 h-9 rounded-xl flex items-center justify-center text-warm-muted hover:bg-warm-input hover:text-warm-accent transition-colors"
        >
          <ChevronLeft size={20} />
        </button>
        <div className="w-9 h-9 rounded-xl bg-warm-accent/12 flex items-center justify-center">
          <Receipt size={18} className="text-warm-accent" />
        </div>
        <h1 className="text-lg font-semibold text-warm-text font-heading">记账本</h1>
      </div>

      {/* Quick add area */}
      <div className="p-5 rounded-2xl bg-warm-input/40 border border-warm-border/40 space-y-4">
        {/* Amount */}
        <div>
          <label className="text-xs text-warm-muted mb-1.5 block">金额</label>
          <div className="relative">
            <span className="absolute left-7 top-1/2 -translate-y-1/2 text-warm-accent font-heading font-bold text-lg select-none">¥</span>
            <input
              type="number"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              placeholder="0"
              min="0"
              step="0.01"
              className="w-full pl-14 pr-4 py-3 rounded-xl bg-warm-bg border border-warm-border/60 text-lg font-heading font-bold text-warm-text placeholder-warm-faint/40 focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all input-enhanced"
            />
          </div>
        </div>

        {/* Category */}
        <div>
          <label className="text-xs text-warm-muted mb-1.5 block">分类</label>
          <div className="flex flex-wrap gap-2">
            {EXPENSE_CATEGORIES.map(cat => {
              const Icon = cat.icon
              const isActive = category === cat.key
              return (
                <button
                  key={cat.key}
                  onClick={() => setCategory(cat.key)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all duration-200 ${
                    isActive
                      ? cat.color + ' font-medium ring-1 ring-warm-accent/20'
                      : 'bg-warm-bg text-warm-muted hover:text-warm-text border border-warm-border/40'
                  }`}
                >
                  <Icon size={12} />
                  {cat.key}
                </button>
              )
            })}
          </div>
        </div>

        {/* Description + Date row */}
        <div className="flex gap-3">
          <div className="flex-1">
            <label className="text-xs text-warm-muted mb-1.5 block">描述</label>
            <input
              type="text"
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="买了什么..."
              className="w-full px-3.5 py-2.5 rounded-xl bg-warm-bg border border-warm-border/60 text-sm text-warm-text placeholder-warm-faint/40 focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all input-enhanced"
            />
          </div>
          <div className="w-36">
            <label className="text-xs text-warm-muted mb-1.5 block">日期</label>
            <input
              type="date"
              value={expenseDate}
              onChange={e => setExpenseDate(e.target.value)}
              className="w-full px-3 py-2.5 rounded-xl bg-warm-bg border border-warm-border/60 text-sm text-warm-text focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all input-enhanced"
            />
          </div>
        </div>

        {/* Note */}
        <div>
          <label className="text-xs text-warm-muted mb-1.5 block">备注</label>
          <input
            type="text"
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="可选"
            className="w-full px-3.5 py-2.5 rounded-xl bg-warm-bg border border-warm-border/60 text-sm text-warm-text placeholder-warm-faint/40 focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all input-enhanced"
          />
        </div>

        {/* Add button */}
        <button
          onClick={handleAdd}
          disabled={!amount || parseFloat(amount) <= 0 || createMutation.isPending}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-warm-accent hover:bg-warm-accent-hover text-white font-medium disabled:opacity-30 disabled:cursor-not-allowed transition-all btn-primary btn-press text-sm"
        >
          {createMutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          记一笔
        </button>

        {/* Stats — always visible below the add button */}
        {stats && stats.total_amount > 0 && (
          <div className="pt-3 space-y-3 border-t border-warm-border/30">
            {/* Monthly total */}
            <div className="flex items-baseline justify-between">
              <span className="text-xs text-warm-muted">本月总支出</span>
              <span className="text-xl font-bold font-heading text-warm-accent-deep">
                ¥{formatMoney(stats.total_amount)}
              </span>
            </div>

            {/* Category breakdown */}
            {stats.category_breakdown.length > 0 && (
              <div>
                {renderCategoryBar(stats.category_breakdown)}
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
                  {stats.category_breakdown.slice(0, 5).map(item => {
                    const cfg = getCategoryConfig(item.category)
                    return (
                      <div key={item.category} className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                        <span className="text-[11px] text-warm-text">{item.category}</span>
                        <span className="text-[11px] text-warm-faint">{item.percentage}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Expense list */}
      <div className="mt-6">
        {sortedDates.length === 0 ? (
          <div className="py-10 text-center">
            <Receipt size={32} className="mx-auto mb-3 text-warm-faint/30" />
            <p className="text-sm text-warm-faint/60">还没有消费记录</p>
            <p className="text-xs text-warm-faint/40 mt-1">在上方添加第一笔消费</p>
          </div>
        ) : (
          sortedDates.map(date => {
            const dayTotal = groupedExpenses[date].reduce((s, e) => s + e.amount, 0)
            return (
              <div key={date} className="mb-4">
                {/* Date header */}
                <div className="flex items-center justify-between mb-2 px-1">
                  <div className="flex items-center gap-2">
                    <Calendar size={12} className="text-warm-accent/60" />
                    <span className="text-xs font-medium text-warm-muted font-heading">
                      {new Date(date + 'T00:00:00').toLocaleDateString('zh-CN', {
                        month: 'long', day: 'numeric', weekday: 'short'
                      })}
                    </span>
                  </div>
                  <span className="text-xs text-warm-faint">
                    ¥{formatMoney(dayTotal)}
                  </span>
                </div>

                {/* Items */}
                <div className="space-y-1.5">
                  {groupedExpenses[date].map(record => {
                    const cfg = getCategoryConfig(record.category)
                    const Icon = cfg.icon
                    const isEditing = editingId === record.id

                    return (
                      <motion.div
                        key={record.id}
                        layout
                        className={`px-4 py-3 rounded-xl transition-all duration-200 group ${
                          isEditing
                            ? 'bg-warm-accent/8 border border-warm-accent/25'
                            : 'hover:bg-warm-input/40'
                        }`}
                      >
                        {isEditing ? (
                          <div className="space-y-3">
                            <div className="flex items-center gap-3">
                              <div className="relative flex-1">
                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-warm-accent font-heading font-bold text-sm select-none">¥</span>
                                <input
                                  type="number"
                                  value={editAmount}
                                  onChange={e => setEditAmount(e.target.value)}
                                  className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-warm-bg border border-warm-border text-sm font-heading font-bold text-warm-text focus:outline-none focus:border-warm-accent/50 transition-all input-enhanced"
                                />
                              </div>
                              <input
                                type="date"
                                value={editDate}
                                onChange={e => setEditDate(e.target.value)}
                                className="px-2.5 py-1.5 rounded-lg bg-warm-bg border border-warm-border text-xs text-warm-text focus:outline-none focus:border-warm-accent/50 transition-all input-enhanced"
                              />
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {EXPENSE_CATEGORIES.map(cat => {
                                const CatIcon = cat.icon
                                return (
                                  <button
                                    key={cat.key}
                                    onClick={() => setEditCategory(cat.key)}
                                    className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] transition-all ${
                                      editCategory === cat.key
                                        ? cat.color + ' font-medium ring-1 ring-warm-accent/20'
                                        : 'bg-warm-bg text-warm-muted hover:text-warm-text'
                                    }`}
                                  >
                                    <CatIcon size={10} />
                                    {cat.key}
                                  </button>
                                )
                              })}
                            </div>
                            <input
                              type="text"
                              value={editDescription}
                              onChange={e => setEditDescription(e.target.value)}
                              placeholder="描述"
                              className="w-full px-3 py-1.5 rounded-lg bg-warm-bg border border-warm-border text-sm text-warm-text focus:outline-none focus:border-warm-accent/50 transition-all input-enhanced"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => { if (parseFloat(editAmount) > 0) updateMutation.mutate() }}
                                disabled={parseFloat(editAmount) <= 0 || updateMutation.isPending}
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-warm-accent text-white text-xs font-medium disabled:opacity-40 transition-colors btn-primary"
                              >
                                <Check size={12} /> 保存
                              </button>
                              <button
                                onClick={() => setEditingId(null)}
                                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-warm-input text-warm-muted text-xs hover:text-warm-text transition-colors"
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-3">
                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${cfg.color}`}>
                              <Icon size={14} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm text-warm-text font-medium truncate">
                                  {record.description || record.category}
                                </span>
                                {record.note && (
                                  <span className="text-[11px] text-warm-faint truncate">{record.note}</span>
                                )}
                              </div>
                              <span className="text-[11px] text-warm-faint">{record.category}</span>
                            </div>
                            <span className="text-sm font-heading font-bold text-warm-accent-deep shrink-0">
                              -¥{formatMoney(record.amount)}
                            </span>
                            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                              <button
                                onClick={() => handleStartEdit(record)}
                                className="w-6 h-6 rounded-md flex items-center justify-center text-warm-faint hover:text-warm-accent hover:bg-warm-accent/10 transition-colors"
                              >
                                <Edit3 size={11} />
                              </button>
                              <button
                                onClick={() => deleteMutation.mutate(record.id)}
                                className="w-6 h-6 rounded-md flex items-center justify-center text-warm-faint hover:text-warm-danger hover:bg-warm-danger/10 transition-colors"
                              >
                                <Trash2 size={11} />
                              </button>
                            </div>
                          </div>
                        )}
                      </motion.div>
                    )
                  })}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
