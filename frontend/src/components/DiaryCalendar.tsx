import { useState, useMemo } from 'react'
import { ChevronLeft, ChevronRight, BookOpen } from 'lucide-react'

interface DiaryDateItem {
  id: string
  date: string
}

const DAY_NAMES = ['日', '一', '二', '三', '四', '五', '六']
const MONTH_NAMES = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

interface DiaryCalendarProps {
  diaries: DiaryDateItem[]
  onSelectDate: (dateStr: string) => void
}

type PickerMode = 'none' | 'year' | 'month'

export default function DiaryCalendar({ diaries, onSelectDate }: DiaryCalendarProps) {
  const [expanded, setExpanded] = useState(false)
  const [viewYear, setViewYear] = useState(() => new Date().getFullYear())
  const [viewMonth, setViewMonth] = useState(() => new Date().getMonth())
  const [pickerMode, setPickerMode] = useState<PickerMode>('none')
  const [pickerDecade, setPickerDecade] = useState(() =>
    Math.floor(new Date().getFullYear() / 10) * 10
  )

  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  const diaryMap = useMemo(() => {
    const map = new Map<string, DiaryDateItem>()
    for (const d of diaries) {
      map.set(d.date, d)
    }
    return map
  }, [diaries])

  const navigateMonth = (delta: number) => {
    let newMonth = viewMonth + delta
    let newYear = viewYear
    if (newMonth < 0) { newMonth = 11; newYear-- }
    if (newMonth > 11) { newMonth = 0; newYear++ }
    setViewYear(newYear)
    setViewMonth(newMonth)
  }

  const prevMonth = () => navigateMonth(-1)
  const nextMonth = () => navigateMonth(1)

  const selectYear = (year: number) => {
    setViewYear(year)
    setPickerMode('month')
  }

  const selectMonth = (month: number) => {
    setViewMonth(month)
    setPickerMode('none')
  }

  const openYearPicker = () => {
    setPickerDecade(Math.floor(viewYear / 10) * 10)
    setPickerMode('year')
  }

  const openMonthPicker = () => {
    setPickerMode('month')
  }

  const calendarDays = useMemo(() => {
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
  }, [viewYear, viewMonth])

  const formatDateStr = (day: number) =>
    `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`

  const diaryDaysCount = useMemo(() => {
    const monthPrefix = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}`
    let count = 0
    for (const [date] of diaryMap) {
      if (date.startsWith(monthPrefix)) count++
    }
    return count
  }, [diaryMap, viewYear, viewMonth])

  const handleDayClick = (day: number) => {
    const dateStr = formatDateStr(day)
    onSelectDate(dateStr)
  }

  const yearRange = useMemo(() => {
    const years: number[] = []
    for (let y = pickerDecade - 1; y < pickerDecade + 11; y++) {
      years.push(y)
    }
    return years
  }, [pickerDecade])

  return (
    <div className="mb-3">
      {/* Header Button */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl bg-warm-card border border-warm-border hover:border-warm-accent/30 hover:shadow-elevated-2 transition-all duration-300 group"
      >
        <div className={`w-9 h-9 rounded-xl bg-warm-accent/10 flex items-center justify-center transition-transform duration-500 ${expanded ? 'rotate-12' : ''}`}>
          <BookOpen size={18} className="text-warm-accent" />
        </div>
        <div className="flex-1 text-left">
          <p className="text-sm font-semibold text-warm-text">日记本</p>
          <p className="text-xs text-warm-muted mt-0.5">
            {viewYear}年{viewMonth + 1}月 · <span className="text-warm-accent font-medium">{diaryDaysCount}</span> 篇
          </p>
        </div>
        <div className={`w-6 h-6 rounded-full bg-warm-input flex items-center justify-center transition-all duration-300 ${expanded ? 'rotate-180 bg-warm-accent/10' : ''}`}>
          <ChevronRight size={14} className={`transition-colors ${expanded ? 'text-warm-accent' : 'text-warm-faint'}`} />
        </div>
      </button>

      {/* Expanded Calendar */}
      {expanded && (
        <div className="mt-3 rounded-2xl bg-warm-card border border-warm-border overflow-hidden animate-fade-in shadow-elevated-1">
          {/* Month Navigation */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-warm-border/60">
            <button
              onClick={prevMonth}
              className="w-8 h-8 rounded-lg hover:bg-warm-input transition-all duration-200 text-warm-muted hover:text-warm-text flex items-center justify-center"
            >
              <ChevronLeft size={16} />
            </button>

            <div className="flex items-center gap-1.5">
              <button
                onClick={openYearPicker}
                className="px-3 py-1 rounded-lg text-sm font-semibold text-warm-text hover:bg-warm-input transition-colors"
              >
                {viewYear}年
              </button>
              <button
                onClick={openMonthPicker}
                className="px-3 py-1 rounded-lg text-sm font-semibold text-warm-text hover:bg-warm-input transition-colors"
              >
                {viewMonth + 1}月
              </button>
            </div>

            <button
              onClick={nextMonth}
              className="w-8 h-8 rounded-lg hover:bg-warm-input transition-all duration-200 text-warm-muted hover:text-warm-text flex items-center justify-center"
            >
              <ChevronRight size={16} />
            </button>
          </div>

          {pickerMode === 'year' ? (
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <button
                  onClick={() => setPickerDecade(d => d - 10)}
                  className="w-8 h-8 rounded-lg hover:bg-warm-input transition-all text-warm-muted hover:text-warm-text flex items-center justify-center"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="text-sm font-semibold text-warm-text">
                  {pickerDecade} - {pickerDecade + 9}
                </span>
                <button
                  onClick={() => setPickerDecade(d => d + 10)}
                  className="w-8 h-8 rounded-lg hover:bg-warm-input transition-all text-warm-muted hover:text-warm-text flex items-center justify-center"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {yearRange.map(y => {
                  const isCurrent = y === viewYear
                  const isThisYear = y === today.getFullYear()
                  const yearCount = [...diaryMap.keys()].filter(d => d.startsWith(`${y}-`)).length
                  return (
                    <button
                      key={y}
                      onClick={() => selectYear(y)}
                      className={`py-3 rounded-xl text-xs transition-all duration-200 ${
                        isCurrent
                          ? 'bg-warm-accent text-white font-bold shadow-elevated-1'
                          : isThisYear
                            ? 'bg-warm-highlight text-warm-accent-deep font-medium'
                            : 'text-warm-muted hover:bg-warm-input'
                      }`}
                    >
                      <span className="text-sm">{y}</span>
                      {yearCount > 0 && !isCurrent && (
                        <span className="block text-[10px] mt-1 opacity-60">{yearCount} 篇</span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          ) : pickerMode === 'month' ? (
            <div className="p-4">
              <div className="grid grid-cols-4 gap-2">
                {MONTH_NAMES.map((name, idx) => {
                  const isCurrent = idx === viewMonth
                  const monthPrefix = `${viewYear}-${String(idx + 1).padStart(2, '0')}`
                  const count = [...diaryMap.keys()].filter(d => d.startsWith(monthPrefix)).length
                  return (
                    <button
                      key={idx}
                      onClick={() => selectMonth(idx)}
                      className={`py-3 rounded-xl text-xs transition-all duration-200 ${
                        isCurrent
                          ? 'bg-warm-accent text-white font-bold shadow-elevated-1'
                          : count > 0
                            ? 'bg-warm-highlight/60 text-warm-accent-deep font-medium hover:bg-warm-highlight'
                            : 'text-warm-muted hover:bg-warm-input'
                      }`}
                    >
                      <span className="text-sm">{name}</span>
                      {count > 0 && (
                        <span className={`block text-[10px] mt-1 ${isCurrent ? 'opacity-70' : 'opacity-50'}`}>
                          {count} 篇
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
              <button
                onClick={openYearPicker}
                className="mt-3 w-full text-xs text-warm-muted hover:text-warm-text py-2 rounded-xl hover:bg-warm-input transition-colors"
              >
                ← 选择年份
              </button>
            </div>
          ) : (
            <div className="p-3">
              {/* Day Headers */}
              <div className="grid grid-cols-7 mb-2">
                {DAY_NAMES.map(name => (
                  <div key={name} className="text-center text-[11px] text-warm-faint py-2 font-semibold">
                    {name}
                  </div>
                ))}
              </div>

              {/* Calendar Grid */}
              <div className="space-y-1">
                {calendarDays.map((week, wi) => (
                  <div key={wi} className="grid grid-cols-7 gap-1">
                    {week.map((day, di) => {
                      if (day === null) return <div key={`e-${di}`} className="h-9" />

                      const dateStr = formatDateStr(day)
                      const entry = diaryMap.get(dateStr)
                      const isToday = dateStr === todayStr
                      const isWeekend = di === 0 || di === 6

                      return (
                        <button
                          key={dateStr}
                          onClick={() => handleDayClick(day)}
                          className={`h-9 w-9 mx-auto rounded-full flex items-center justify-center text-[13px] transition-all duration-200 relative hover:scale-110 ${
                            isToday
                              ? 'bg-warm-accent text-white font-bold shadow-elevated-1 hover:bg-warm-accent-hover'
                              : entry
                                ? 'bg-warm-highlight/60 text-warm-accent-deep font-semibold hover:bg-warm-highlight'
                                : isWeekend
                                  ? 'text-warm-muted hover:bg-warm-input'
                                  : 'text-warm-text hover:bg-warm-input'
                          }`}
                        >
                          <span>{day}</span>
                          {entry && !isToday && (
                            <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-warm-accent border-2 border-warm-card" />
                          )}
                          {isToday && (
                            <span className="absolute inset-0 rounded-full animate-pulse-soft bg-warm-accent/20 -z-10" />
                          )}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
