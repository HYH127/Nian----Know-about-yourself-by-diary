import { useState, useRef, useEffect } from 'react'
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

interface DatePickerProps {
  value: string
  onChange: (date: string) => void
}

const DAY_NAMES = ['日', '一', '二', '三', '四', '五', '六']

export default function DatePicker({ value, onChange }: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear())
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth())
  const ref = useRef<HTMLDivElement>(null)

  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  // Close on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Sync view with value when opened
  useEffect(() => {
    if (open && value) {
      const d = new Date(value)
      setViewYear(d.getFullYear())
      setViewMonth(d.getMonth())
    }
  }, [open, value])

  const navigateMonth = (delta: number) => {
    let newMonth = viewMonth + delta
    let newYear = viewYear
    if (newMonth < 0) { newMonth = 11; newYear-- }
    if (newMonth > 11) { newMonth = 0; newYear++ }
    setViewYear(newYear)
    setViewMonth(newMonth)
  }

  const calendarDays = (() => {
    const firstDay = new Date(viewYear, viewMonth, 1).getDay()
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
    const cells: (number | null)[] = []
    for (let i = 0; i < firstDay; i++) cells.push(null)
    for (let d = 1; d <= daysInMonth; d++) cells.push(d)
    while (cells.length < 42) cells.push(null)
    const rows: (number | null)[][] = []
    for (let i = 0; i < cells.length; i += 7) {
      rows.push(cells.slice(i, i + 7))
    }
    return rows
  })()

  const formatDateStr = (day: number) =>
    `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`

  const handleSelect = (day: number) => {
    onChange(formatDateStr(day))
    setOpen(false)
  }

  const displayDate = value
    ? new Date(value).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
    : '选择日期'

  return (
    <div className="relative" ref={ref}>
      {/* Trigger */}
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-2 rounded-xl border transition-all duration-200 ${
          open
            ? 'border-warm-accent/50 ring-4 ring-warm-accent/10 bg-warm-card'
            : 'border-warm-border bg-warm-input hover:border-warm-accent/30'
        }`}
      >
        <Calendar size={16} className={open ? 'text-warm-accent' : 'text-warm-muted'} />
        <span className="text-sm text-warm-text font-medium">{displayDate}</span>
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-2 z-50 w-[280px] rounded-2xl bg-warm-card border border-warm-border shadow-elevated-3 animate-fade-in p-3">
          {/* Header */}
          <div className="flex items-center justify-between px-1 py-2 mb-2">
            <button
              onClick={() => navigateMonth(-1)}
              className="w-7 h-7 rounded-lg hover:bg-warm-input transition-all text-warm-muted hover:text-warm-text flex items-center justify-center"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="text-sm font-semibold text-warm-text">
              {viewYear}年 {viewMonth + 1}月
            </span>
            <button
              onClick={() => navigateMonth(1)}
              className="w-7 h-7 rounded-lg hover:bg-warm-input transition-all text-warm-muted hover:text-warm-text flex items-center justify-center"
            >
              <ChevronRight size={14} />
            </button>
          </div>

          {/* Day Headers */}
          <div className="grid grid-cols-7 mb-1">
            {DAY_NAMES.map(name => (
              <div key={name} className="text-center text-[10px] text-warm-faint py-1.5 font-semibold">
                {name}
              </div>
            ))}
          </div>

          {/* Calendar Grid */}
          <div className="space-y-0.5">
            {calendarDays.map((week, wi) => (
              <div key={wi} className="grid grid-cols-7 gap-0.5">
                {week.map((day, di) => {
                  if (day === null) return <div key={`e-${di}`} className="h-8" />

                  const dateStr = formatDateStr(day)
                  const isToday = dateStr === todayStr
                  const isSelected = dateStr === value
                  const isWeekend = di === 0 || di === 6

                  return (
                    <button
                      key={dateStr}
                      onClick={() => handleSelect(day)}
                      className={`h-8 w-8 mx-auto rounded-full flex items-center justify-center text-[12px] transition-all duration-150 ${
                        isSelected
                          ? 'bg-warm-accent text-white font-bold shadow-elevated-1'
                          : isToday
                            ? 'bg-warm-highlight text-warm-accent-deep font-semibold'
                            : isWeekend
                              ? 'text-warm-muted hover:bg-warm-input'
                              : 'text-warm-text hover:bg-warm-input'
                      }`}
                    >
                      {day}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="mt-2 pt-2 border-t border-warm-border/50 flex justify-between">
            <button
              onClick={() => {
                const now = new Date()
                onChange(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`)
                setOpen(false)
              }}
              className="text-xs text-warm-muted hover:text-warm-accent transition-colors px-2 py-1"
            >
              今天
            </button>
            <button
              onClick={() => setOpen(false)}
              className="text-xs text-warm-muted hover:text-warm-text transition-colors px-2 py-1"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
