import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Save, Tag, Sparkles, Calendar, Loader2, Pencil, X, UserCircle, Copy, AlertTriangle, MapPin, CloudSun, Thermometer, Droplets, BookOpen } from 'lucide-react'
import PageContainer from '../components/layout/PageContainer'
import PageHeader from '../components/layout/PageHeader'
import { diaryApi } from '../api'
import type { Diary } from '../types'
import DiaryCalendar from '../components/DiaryCalendar'
import DatePicker from '../components/DatePicker'

const PAGE_SIZE = 30

export default function Diary() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [selectedDiaryId, setSelectedDiaryId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)

  const [editDate, setEditDate] = useState(new Date().toISOString().split('T')[0])
  const [editContent, setEditContent] = useState('')
  const [saveSuccess, setSaveSuccess] = useState(false)

  const [isEditing, setIsEditing] = useState(false)
  const [editingContent, setEditingContent] = useState('')

  // Duplicate check state
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false)
  const [duplicateInfo, setDuplicateInfo] = useState<{ date: string; content_preview: string } | null>(null)
  const [checkingDuplicate, setCheckingDuplicate] = useState(false)

  // Weather state
  const [weatherInfo, setWeatherInfo] = useState<{ location: string; weather: string; temperature: string; humidity: string } | null>(null)
  const [weatherLoading, setWeatherLoading] = useState(false)

  const {
    data: pagesData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['diaries'],
    queryFn: async ({ pageParam = 0 }) => {
      const res = await diaryApi.list(PAGE_SIZE, pageParam)
      return res.data
    },
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) return undefined
      return allPages.flat().length
    },
    initialPageParam: 0,
  })

  const diaries = pagesData?.pages.flat() || []

  const { data: diaryDates = [] } = useQuery({
    queryKey: ['diaryDates'],
    queryFn: async () => {
      const res = await diaryApi.dates()
      return res.data
    },
  })

  const { data: searchResults } = useQuery({
    queryKey: ['diarySearch', searchQuery],
    queryFn: async () => {
      const res = await diaryApi.search(searchQuery)
      return res.data
    },
    enabled: isSearching && !!searchQuery.trim(),
  })

  const { data: selectedDiary, isLoading: detailLoading } = useQuery({
    queryKey: ['diary', selectedDiaryId],
    queryFn: async () => {
      if (!selectedDiaryId) return null
      const res = await diaryApi.get(selectedDiaryId)
      return res.data
    },
    enabled: !!selectedDiaryId,
  })

  const createMutation = useMutation({
    mutationFn: () => diaryApi.create(editDate, editContent.trim(), weatherInfo ? {
      location: weatherInfo.location,
      weather: weatherInfo.weather,
      temperature: weatherInfo.temperature,
      humidity: weatherInfo.humidity,
    } : undefined),
    onSuccess: () => {
      setSaveSuccess(true)
      setEditContent('')
      setWeatherInfo(null)
      setTimeout(() => setSaveSuccess(false), 2000)
      queryClient.invalidateQueries({ queryKey: ['diaries'] })
      queryClient.invalidateQueries({ queryKey: ['diaryDates'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!selectedDiaryId) return
      await diaryApi.update(selectedDiaryId, { content: editingContent.trim() })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['diaries'] })
      queryClient.invalidateQueries({ queryKey: ['diary', selectedDiaryId] })
      // 保存后触发重新处理
      if (selectedDiaryId) {
        diaryApi.reprocess(selectedDiaryId)
      }
      setIsEditing(false)
    },
  })

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries
      if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage()
      }
    },
    [fetchNextPage, hasNextPage, isFetchingNextPage],
  )

  useEffect(() => {
    if (!sentinelRef.current) return
    const observer = new IntersectionObserver(handleObserver, { threshold: 0.1 })
    observer.observe(sentinelRef.current)
    return () => observer.disconnect()
  }, [handleObserver])

  const handleSearch = () => {
    const q = searchQuery.trim()
    if (!q) {
      setIsSearching(false)
      return
    }
    setIsSearching(true)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setIsSearching(false)
  }

  const handleSave = async () => {
    if (!editContent.trim()) return
    // Check for duplicates before creating
    setCheckingDuplicate(true)
    try {
      const res = await diaryApi.checkDuplicate([{ date: editDate, content: editContent.trim() }])
      const found = res.data?.duplicates || []
      if (found.length > 0) {
        setDuplicateInfo({ date: found[0].date, content_preview: found[0].content_preview })
        setShowDuplicateDialog(true)
        setCheckingDuplicate(false)
        return
      }
    } catch {
      // If check fails, proceed with save
    }
    setCheckingDuplicate(false)
    createMutation.mutate()
  }

  const handleForceSave = () => {
    setShowDuplicateDialog(false)
    setDuplicateInfo(null)
    createMutation.mutate()
  }

  const handleSelectDiary = (id: string) => {
    setSelectedDiaryId(id)
    setIsEditing(false)
  }

  const handleStartEdit = () => {
    if (selectedDiary) {
      setEditingContent(selectedDiary.content)
      setIsEditing(true)
    }
  }

  const handleCancelEdit = () => {
    setIsEditing(false)
    setEditingContent('')
  }

  const handleSaveEdit = () => {
    if (!editingContent.trim()) return
    updateMutation.mutate()
  }

  useEffect(() => {
    const diaryId = searchParams.get('id')
    if (diaryId && diaries.length > 0) {
      const match = diaries.find(d => d.id === diaryId)
      if (match) setSelectedDiaryId(match.id)
    }
  }, [searchParams, diaries])

  const handleDateSelect = (dateStr: string) => {
    const match = diaries.find(d => d.date === dateStr)
    if (match) {
      setSelectedDiaryId(match.id)
    } else {
      setSelectedDiaryId(null)
      setEditDate(dateStr)
    }
  }

  const displayDiaries = isSearching && searchResults ? searchResults : diaries

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
    })
  }

  const getPreview = (content: string) => {
    const firstLine = content.split('\n')[0]
    return firstLine.length > 40 ? firstLine.slice(0, 40) + '...' : firstLine
  }

  const parseTags = (tags: string | undefined): string[] => {
    if (!tags) return []
    try {
      const parsed = JSON.parse(tags)
      return Array.isArray(parsed) ? parsed : [tags]
    } catch {
      return tags.split(',').map(t => t.trim()).filter(Boolean)
    }
  }

  return (
    <PageContainer className="h-full flex flex-col !p-0 !max-w-none">
      <div className="flex h-full">
        {/* 左侧日记列表 */}
        <div className="w-72 flex flex-col bg-warm-sidebar/60 surface-frosted shrink-0 border-r border-warm-border/60">
          {/* 标题栏 */}
          <div className="flex items-center justify-between px-4 py-3 pb-2 mb-1">
            <h1 className="text-base font-semibold text-warm-accent">日记</h1>
            <button
              onClick={() => navigate('/portraits')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-warm-input text-warm-muted rounded-lg hover:bg-warm-accent/15 hover:text-warm-accent-deep transition-colors btn-press border border-warm-border/50"
            >
              <UserCircle size={14} />
              画像
            </button>
          </div>
          {/* 搜索框 */}
          <div className="px-3 pb-2 mb-1">
            <div className="relative group">
              <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-warm-faint group-focus-within:text-warm-accent transition-colors" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder=""
                className="w-full !pl-9 !pr-9 !py-2.5 rounded-xl bg-warm-input border border-warm-border text-sm text-warm-text focus:outline-none focus:border-warm-accent/50 focus:ring-4 focus:ring-warm-accent/10 transition-all input-enhanced"
              />
              {searchQuery && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 rounded-full bg-warm-border/50 hover:bg-warm-border flex items-center justify-center transition-colors"
                >
                  <X size={12} className="text-warm-muted" />
                </button>
              )}
            </div>
            {isSearching && (
              <div className="mt-2 flex items-center gap-2 px-1">
                <span className="text-xs text-warm-accent font-medium">
                  搜索: "{searchQuery}"
                </span>
                <button
                  onClick={handleClearSearch}
                  className="text-xs text-warm-faint hover:text-warm-muted transition-colors"
                >
                  清除
                </button>
              </div>
            )}
          </div>

          {/* 日历本 */}
          <div className="px-3 pt-3">
            <DiaryCalendar diaries={diaryDates} onSelectDate={handleDateSelect} />
          </div>

          {/* 日记列表 */}
          <div className="flex-1 overflow-y-auto px-2 py-1">
            {displayDiaries.map((diary, index) => (
              <button
                key={diary.id}
                onClick={() => handleSelectDiary(diary.id)}
                className={`w-full text-left mb-1 px-3 py-3 rounded-xl transition-all duration-200 relative group ${
                  selectedDiaryId === diary.id
                    ? 'bg-warm-highlight shadow-elevated-1'
                    : 'hover:bg-warm-overlay/50'
                }`}
                style={{ animationDelay: `${index * 30}ms` }}
              >
                {/* Active indicator */}
                {selectedDiaryId === diary.id && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 bg-warm-accent rounded-r-full" />
                )}
                <div className="flex items-center gap-2 mb-1">
                  <Calendar size={12} className={`shrink-0 ${selectedDiaryId === diary.id ? 'text-warm-accent' : 'text-warm-faint'}`} />
                  <span className={`text-xs font-medium font-heading ${
                    selectedDiaryId === diary.id ? 'text-warm-accent-deep' : 'text-warm-muted'
                  }`}>
                    {formatDate(diary.date)}
                  </span>
                </div>
                <p className={`text-sm truncate leading-relaxed ${
                  selectedDiaryId === diary.id ? 'text-warm-text' : 'text-warm-text/80'
                }`}>
                  {getPreview(diary.content)}
                </p>
              </button>
            ))}

            {!isSearching && (
              <div ref={sentinelRef} className="h-8 flex items-center justify-center">
                {isFetchingNextPage && <Loader2 size={14} className="text-warm-accent animate-spin" />}
              </div>
            )}

            {displayDiaries.length === 0 && (
              <div className="p-4 text-center text-warm-faint text-sm empty-state">
                {isSearching ? '未找到匹配日记' : '暂无日记'}
              </div>
            )}
          </div>
        </div>

        {/* 右侧内容区 */}
        <div className="flex-1 flex flex-col min-w-0">
          {selectedDiaryId && detailLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 size={24} className="text-warm-accent animate-spin" />
            </div>
          ) : selectedDiary ? (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-2xl mx-auto">
                <div className="flex items-center gap-2 mb-4">
                  <Calendar size={16} className="text-warm-accent" />
                  <h2 className="text-lg font-medium font-heading text-warm-text">
                    {formatDate(selectedDiary.date)}
                  </h2>
                  {(selectedDiary.location || selectedDiary.weather || selectedDiary.temperature || selectedDiary.humidity) && (
                    <div className="flex items-center gap-1.5 ml-2 flex-wrap">
                      {selectedDiary.location && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-slate-light text-warm-slate text-xs font-medium">
                          <MapPin size={10} /> {selectedDiary.location}
                        </span>
                      )}
                      {selectedDiary.weather && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-amber-light text-warm-amber text-xs font-medium">
                          <CloudSun size={10} /> {selectedDiary.weather}
                        </span>
                      )}
                      {selectedDiary.temperature && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-highlight text-warm-accent-deep text-xs font-medium">
                          <Thermometer size={10} /> {selectedDiary.temperature}°C
                        </span>
                      )}
                      {selectedDiary.humidity && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-sage-light text-warm-sage text-xs font-medium">
                          <Droplets size={10} /> {selectedDiary.humidity}%
                        </span>
                      )}
                    </div>
                  )}
                  {!isEditing ? (
                    <button
                      onClick={handleStartEdit}
                      className="ml-auto flex items-center gap-1 text-sm text-warm-accent hover:text-warm-accent-hover transition-colors"
                    >
                      <Pencil size={14} />
                      编辑
                    </button>
                  ) : (
                    <div className="ml-auto flex items-center gap-2">
                      <button
                        onClick={handleSaveEdit}
                        disabled={!editingContent.trim() || updateMutation.isPending}
                        className="flex items-center gap-1 px-3 py-1 rounded-lg bg-warm-accent hover:bg-warm-accent-hover text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm btn-primary"
                      >
                        <Save size={14} />
                        {updateMutation.isPending ? '保存中...' : '保存'}
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        className="flex items-center gap-1 px-3 py-1 rounded-lg bg-warm-input text-warm-muted hover:text-warm-text transition-colors text-sm"
                      >
                        <X size={14} />
                        取消
                      </button>
                    </div>
                  )}
                </div>

                {selectedDiary.extracted_summary && (
                  <div className="mb-4 p-4 rounded-xl section-card border border-warm-accent/30 surface-raised animate-fade-in">
                    <div
                      className="flex items-center gap-2 cursor-pointer select-none"
                      onClick={() => {
                        const el = document.getElementById('diary-ai-summary')
                        if (el) el.classList.toggle('hidden')
                      }}
                    >
                      <Sparkles size={14} className="text-warm-accent animate-pulse" />
                      <span className="text-sm font-medium text-warm-highlight-text">AI 摘要</span>
                      <span className="text-xs text-warm-muted ml-1">（点击展开/收起）</span>
                    </div>
                    <p id="diary-ai-summary" className="text-sm text-warm-text leading-relaxed mt-2">
                      {selectedDiary.extracted_summary}
                    </p>
                  </div>
                )}

                {selectedDiary.extracted_tags && parseTags(selectedDiary.extracted_tags).length > 0 && (
                  <div
                    className="mb-4 flex items-center gap-2 flex-wrap cursor-pointer select-none"
                    onClick={() => {
                      const el = document.getElementById('diary-tags')
                      if (el) el.classList.toggle('hidden')
                    }}
                  >
                    <Tag size={14} className="text-warm-faint" />
                    <span className="text-xs text-warm-muted">标签（点击展开/收起）</span>
                    <div id="diary-tags" className="hidden flex items-center gap-1.5 flex-wrap">
                      {parseTags(selectedDiary.extracted_tags).map((tag, i) => (
                        <span
                          key={i}
                          className="px-2.5 py-1 rounded-full bg-gradient-to-r from-warm-accent/10 to-warm-accent/10 text-warm-accent-deep text-xs font-medium"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="p-4 rounded-xl section-card surface-raised">
                  <h3 className="text-sm font-semibold font-heading text-warm-muted mb-3 section-title">原文</h3>
                  {isEditing ? (
                    <textarea
                      value={editingContent}
                      onChange={e => setEditingContent(e.target.value)}
                      className="w-full min-h-[200px] resize-y rounded-lg bg-warm-input border border-warm-border p-3 text-sm text-warm-text placeholder-warm-faint focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all leading-relaxed surface-inset focus-ring-enhanced input-enhanced"
                    />
                  ) : (
                    <p className="text-sm text-warm-text leading-relaxed whitespace-pre-wrap">
                      {selectedDiary.content}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col p-6">
              <div className="max-w-2xl mx-auto w-full flex flex-col flex-1">
                <div className="flex items-center gap-3 mb-4">
                  <DatePicker value={editDate} onChange={setEditDate} />
                  <button
                    onClick={handleSave}
                    disabled={!editContent.trim() || createMutation.isPending || checkingDuplicate}
                    className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-warm-accent hover:bg-warm-accent-hover text-white shadow-elevated-1 hover:shadow-elevated-2 disabled:opacity-40 disabled:cursor-not-allowed transition-all btn-primary btn-press text-sm font-medium"
                  >
                    {checkingDuplicate ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                    {checkingDuplicate ? '检测中...' : createMutation.isPending ? '保存中...' : '保存'}
                  </button>
                  {saveSuccess && (
                    <span className="text-sm text-green-500 animate-fade-in">保存成功</span>
                  )}
                </div>

                <textarea
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  placeholder="写下今天的日记..."
                  className="flex-1 w-full resize-none rounded-xl section-card p-4 text-sm text-warm-text placeholder-warm-faint focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all leading-relaxed surface-raised surface-inset focus-ring-enhanced input-enhanced"
                />

                <div className="flex items-center gap-2 mt-2 flex-wrap">
                  <button
                    onClick={() => {
                      const AMap = (window as any).AMap
                      if (!AMap) return
                      setWeatherLoading(true)
                      AMap.plugin(['AMap.Geolocation', 'AMap.Geocoder', 'AMap.Weather'], function() {
                        const geolocation = new AMap.Geolocation({
                          enableHighAccuracy: true,
                          timeout: 10000,
                        })
                        geolocation.getCurrentPosition(function(status: string, result: any) {
                          if (status === 'complete' && result && result.position) {
                            const lnglat = result.position
                            const geocoder = new AMap.Geocoder()
                            geocoder.getAddress(lnglat, function(geoStatus: string, geoResult: any) {
                              let location = ''
                              let adcode = ''
                              if (geoStatus === 'complete' && geoResult && geoResult.regeocode) {
                                location = geoResult.regeocode.formattedAddress || ''
                                adcode = geoResult.regeocode.addressComponent?.adcode || ''
                              }
                              if (adcode) {
                                const weather = new AMap.Weather()
                                weather.getLive(adcode, function(err: string, data: any) {
                                  if (!err && data) {
                                    setWeatherInfo({
                                      location,
                                      weather: data.weather || '',
                                      temperature: String(data.temperature || ''),
                                      humidity: String(data.humidity || ''),
                                    })
                                  } else {
                                    setWeatherInfo({ location, weather: '', temperature: '', humidity: '' })
                                  }
                                  setWeatherLoading(false)
                                })
                              } else {
                                setWeatherInfo({ location, weather: '', temperature: '', humidity: '' })
                                setWeatherLoading(false)
                              }
                            })
                          } else {
                            setWeatherInfo(null)
                            setWeatherLoading(false)
                          }
                        })
                      })
                    }}
                    disabled={weatherLoading}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs text-warm-muted hover:text-warm-accent hover:bg-warm-accent/5 transition-all disabled:opacity-40"
                  >
                    {weatherLoading ? <Loader2 size={12} className="animate-spin" /> : <MapPin size={12} />}
                    {weatherLoading ? '获取中...' : weatherInfo ? '重新获取' : '获取位置与天气'}
                  </button>
                  {weatherInfo && (
                    <>
                      {weatherInfo.location && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-slate-light text-warm-slate text-xs font-medium">
                          <MapPin size={10} /> {weatherInfo.location}
                        </span>
                      )}
                      {weatherInfo.weather && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-amber-light text-warm-amber text-xs font-medium">
                          <CloudSun size={10} /> {weatherInfo.weather}
                        </span>
                      )}
                      {weatherInfo.temperature && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-highlight text-warm-accent-deep text-xs font-medium">
                          <Thermometer size={10} /> {weatherInfo.temperature}°C
                        </span>
                      )}
                      {weatherInfo.humidity && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-warm-sage-light text-warm-sage text-xs font-medium">
                          <Droplets size={10} /> {weatherInfo.humidity}%
                        </span>
                      )}
                      <button onClick={() => setWeatherInfo(null)} className="w-5 h-5 rounded-full hover:bg-warm-input flex items-center justify-center text-warm-faint hover:text-warm-muted transition-colors">
                        <X size={12} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {showDuplicateDialog && duplicateInfo && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-warm-card rounded-xl p-6 max-w-md w-full mx-4 border border-warm-border shadow-xl">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle size={20} className="text-amber-400" />
                <h3 className="text-lg font-semibold text-warm-text">检测到重复日记</h3>
              </div>
              <p className="text-sm text-warm-muted mb-3">
                该日期已存在内容完全相同的日记：
              </p>
              <div className="bg-warm-input/50 rounded-lg p-3 mb-4">
                <div className="flex items-center gap-2 mb-1">
                  <Calendar size={12} className="text-warm-accent" />
                  <span className="text-sm text-warm-text font-medium">{duplicateInfo.date}</span>
                </div>
                <p className="text-xs text-warm-muted line-clamp-2">{duplicateInfo.content_preview}</p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={() => { setShowDuplicateDialog(false); setDuplicateInfo(null) }}
                  className="flex-1 py-2 bg-warm-input text-warm-muted rounded-lg hover:text-warm-text transition-colors text-sm"
                >
                  取消保存
                </button>
                <button
                  onClick={handleForceSave}
                  className="flex-1 py-2 bg-warm-accent hover:bg-warm-accent-hover text-white rounded-lg transition-colors text-sm btn-primary"
                >
                  仍然保存
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageContainer>
  )
}