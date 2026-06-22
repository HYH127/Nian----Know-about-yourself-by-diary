import { useState, useCallback, useRef } from 'react'
import { Upload, CheckCircle, AlertCircle, Loader2, Calendar, X, ChevronDown, ChevronUp, Pencil, Copy } from 'lucide-react'
import { importApi, diaryApi } from '../api'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

export default function Import() {
  return (
    <PageContainer className="max-w-4xl">
      <PageHeader title="日记导入" icon={<Upload size={20} />} />
      <DiaryImportTab />
    </PageContainer>
  )
}

function DiaryImportTab() {
  const [entries, setEntries] = useState<{ date: string; content: string }[]>([])
  const [pasteText, setPasteText] = useState('')
  const [pasteDate, setPasteDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [editingIdx, setEditingIdx] = useState<number | null>(null)
  const [editDate, setEditDate] = useState('')
  const [editContent, setEditContent] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Duplicate check state
  const [duplicates, setDuplicates] = useState<{ index: number; date: string; content_preview: string; existing_id: string; existing_date: string }[]>([])
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false)
  const [checkingDuplicate, setCheckingDuplicate] = useState(false)

  const parseFiles = async (files: FileList) => {
    setError('')
    const newEntries: { date: string; content: string }[] = []
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const text = await file.text()
      const ext = file.name.split('.').pop()?.toLowerCase()

      if (ext === 'json') {
        try {
          const parsed = JSON.parse(text)
          const items = Array.isArray(parsed) ? parsed : (parsed?.diaries || parsed?.entries || [])
          if (!Array.isArray(items) || items.length === 0) {
            setError(`JSON 格式错误：${file.name}，需要数组格式 [{"date": "...", "content": "..."}]`)
            continue
          }
          let jsonCount = 0
          for (const item of items) {
            const d = item.date || item.time || item.日期 || item.created_at || ''
            const c = item.content || item.text || item.body || item.内容 || item.raw || ''
            if (d && c) {
              let dateStr = String(d).trim()
              const m = dateStr.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,3})$/)
              if (m) {
                const year = m[1]
                const month = parseInt(m[2]) || 1
                const day = parseInt(m[3]) || 1
                dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
              } else {
                const m2 = dateStr.match(/^(\d{4})(\d{2})(\d{2})$/)
                if (m2) {
                  dateStr = `${m2[1]}-${m2[2]}-${m2[3]}`
                } else {
                  dateStr = dateStr.slice(0, 10)
                }
              }
              const contentStr = String(c).replace(/\\n/g, '\n').trim()
              newEntries.push({ date: dateStr, content: contentStr })
              jsonCount++
            }
          }
          if (jsonCount === 0) {
            setError(`JSON 中未找到有效条目：${file.name}，每条需要 date 和 content 字段`)
          }
        } catch (e) {
          setError(`JSON 解析失败：${file.name}，${e instanceof Error ? e.message : '格式错误'}`)
          continue
        }
      } else {
        const nameMatch = file.name.match(/(\d{4}[-_]?(\d{2})[-_]?(\d{2}))/)
        const dateFromName = nameMatch ? nameMatch[1].replace(/[-_]/g, '-') : ''
        newEntries.push({
          date: dateFromName || new Date().toISOString().slice(0, 10),
          content: text.trim(),
        })
      }
    }
    setEntries(prev => [...prev, ...newEntries])
  }

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    if (e.dataTransfer.files.length > 0) {
      await parseFiles(e.dataTransfer.files)
    }
  }, [])

  const handleInputChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      await parseFiles(e.target.files)
    }
  }, [])

  const addFromPaste = () => {
    if (!pasteText.trim() || !pasteDate.trim()) return
    setEntries(prev => [...prev, { date: pasteDate, content: pasteText.trim() }])
    setPasteText('')
  }

  const removeEntry = (idx: number) => {
    setEntries(prev => prev.filter((_, i) => i !== idx))
  }

  const handleImport = async (skipDuplicates = false) => {
    if (entries.length === 0) return
    setLoading(true)
    setError('')
    try {
      if (!skipDuplicates) {
        setCheckingDuplicate(true)
        try {
          const res = await diaryApi.checkDuplicate(entries)
          const foundDuplicates = res.data?.duplicates || []
          if (foundDuplicates.length > 0) {
            setDuplicates(foundDuplicates)
            setShowDuplicateDialog(true)
            setCheckingDuplicate(false)
            setLoading(false)
            return
          }
        } catch {
          // If check fails, proceed with import anyway
        }
        setCheckingDuplicate(false)
      }

      const entriesToImport = skipDuplicates
        ? entries.filter((_, i) => !duplicates.some(d => d.index === i))
        : entries

      if (entriesToImport.length === 0) {
        setError('所有日记都是重复的，没有需要导入的内容')
        setLoading(false)
        return
      }

      await importApi.importDiary(entriesToImport)
      setSuccess(true)
      setEntries([])
      setPasteText('')
      setPasteDate('')
      setDuplicates([])
      setShowDuplicateDialog(false)
      setTimeout(() => setSuccess(false), 3000)
    } catch (e) {
      setError(`导入失败：${e instanceof Error ? e.message : '未知错误'}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      {success && (
        <div className="mb-4 flex items-center gap-2 bg-green-500/10 border border-green-500/30 rounded-lg p-3">
          <CheckCircle size={16} className="text-green-500 shrink-0" />
          <p className="text-green-300 text-sm">导入成功！日记将在后台自动处理。</p>
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 bg-red-400/15 border border-red-500/30 rounded-lg p-3">
          <AlertCircle size={16} className="text-red-500 shrink-0" />
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {/* File upload area */}
      <div
        onDrop={handleDrop}
        onDragOver={e => e.preventDefault()}
        onClick={() => fileInputRef.current?.click()}
        className="section-card border-2 border-dashed border-warm-border p-10 text-center cursor-pointer hover:border-warm-accent hover:bg-warm-highlight/40 transition-colors"
      >
        <Upload size={40} className="mx-auto mb-3 text-warm-muted" />
        <p className="text-warm-text mb-1">拖拽文件到此处，或点击选择</p>
        <p className="text-warm-faint text-sm">支持 .txt, .md, .json 格式，可多选</p>
        <p className="text-warm-faint text-xs mt-1">JSON 格式：[{"{"}"date": "2026-01-01", "content": "日记内容"{"}"}]</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.markdown,.json"
          multiple
          onChange={handleInputChange}
          className="hidden"
        />
      </div>

      {/* Direct paste area */}
      <div className="mt-4 section-card space-y-3">
        <h3 className="text-sm font-medium text-warm-text">直接粘贴</h3>
        <div className="flex gap-3">
          <input
            type="date"
            value={pasteDate}
            onChange={e => setPasteDate(e.target.value)}
            className="input-enhanced shrink-0"
          />
          <button
            onClick={addFromPaste}
            disabled={!pasteText.trim() || !pasteDate}
            className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed text-sm shrink-0"
          >
            添加
          </button>
        </div>
        <textarea
          value={pasteText}
          onChange={e => setPasteText(e.target.value)}
          placeholder="在此粘贴日记内容..."
          rows={4}
          className="w-full input-enhanced resize-none"
        />
      </div>

      {/* Preview parsed entries */}
      {entries.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-warm-text mb-3">待导入日记（{entries.length} 条）</h3>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {entries.map((entry, i) => (
              <div key={i} className="list-item">
                {editingIdx === i ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="date"
                        value={editDate}
                        onChange={e => setEditDate(e.target.value)}
                        className="bg-warm-input border border-warm-border rounded-lg px-3 py-1.5 text-warm-text text-sm focus:outline-none focus:ring-warm-accent/20 focus:border-warm-accent"
                      />
                      <div className="flex-1" />
                      <button
                        onClick={() => {
                          setEntries(prev => prev.map((e, idx) => idx === i ? { ...e, date: editDate, content: editContent } : e))
                          setEditingIdx(null)
                        }}
                        className="px-3 py-1 text-xs bg-warm-accent text-white rounded hover:bg-warm-accent-hover transition-colors"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditingIdx(null)}
                        className="px-3 py-1 text-xs bg-warm-input text-warm-muted rounded hover:text-warm-text transition-colors"
                      >
                        取消
                      </button>
                    </div>
                    <textarea
                      value={editContent}
                      onChange={e => setEditContent(e.target.value)}
                      rows={6}
                      className="w-full input-enhanced resize-none"
                    />
                  </div>
                ) : (
                  <div className="flex items-start gap-3">
                    <Calendar size={16} className="text-warm-accent mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-warm-text text-sm font-medium">{entry.date}</p>
                        <span className="text-warm-faint text-xs">({entry.content.length} 字)</span>
                      </div>
                      {expandedIdx === i ? (
                        <p className="text-warm-muted text-xs mt-1 whitespace-pre-wrap leading-relaxed">{entry.content}</p>
                      ) : (
                        <p className="text-warm-muted text-xs mt-1 line-clamp-2">{entry.content.slice(0, 100)}{entry.content.length > 100 ? '...' : ''}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                        className="text-warm-faint hover:text-warm-accent transition-colors p-1"
                        title={expandedIdx === i ? '收起' : '展开查看'}
                      >
                        {expandedIdx === i ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                      <button
                        onClick={() => {
                          setEditDate(entry.date)
                          setEditContent(entry.content)
                          setEditingIdx(i)
                          setExpandedIdx(i)
                        }}
                        className="text-warm-faint hover:text-warm-accent transition-colors p-1"
                        title="编辑"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => removeEntry(i)}
                        className="text-warm-faint hover:text-red-500 transition-colors p-1"
                        title="删除"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          <button
            onClick={() => handleImport()}
            disabled={loading || checkingDuplicate}
            className="mt-4 w-full btn-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {checkingDuplicate ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                <span>检测重复中...</span>
              </>
            ) : loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                <span>导入中...</span>
              </>
            ) : (
              <span>确认导入</span>
            )}
          </button>
        </div>
      )}

      {/* Duplicate confirmation dialog */}
      {showDuplicateDialog && duplicates.length > 0 && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-warm-card rounded-xl p-6 max-w-lg w-full mx-4 border border-warm-border shadow-xl">
            <div className="flex items-center gap-2 mb-4">
              <Copy size={20} className="text-amber-400" />
              <h3 className="text-lg font-heading font-semibold text-warm-text">检测到重复日记</h3>
            </div>
            <p className="text-sm text-warm-muted mb-3">
              以下 {duplicates.length} 条日记与已有日记内容完全相同：
            </p>
            <div className="max-h-48 overflow-y-auto space-y-2 mb-4">
              {duplicates.map((d, i) => (
                <div key={i} className="list-item">
                  <div className="flex items-center gap-2 mb-1">
                    <Calendar size={12} className="text-warm-accent" />
                    <span className="text-sm text-warm-text font-medium">{d.date}</span>
                  </div>
                  <p className="text-xs text-warm-muted line-clamp-2">{d.content_preview}</p>
                </div>
              ))}
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => handleImport(true)}
                className="flex-1 py-2 bg-amber-500/15 text-amber-300 rounded-lg hover:bg-amber-500/25 transition-colors text-sm"
              >
                跳过重复，导入其余 {entries.length - duplicates.length} 条
              </button>
              <button
                onClick={() => handleImport(false)}
                className="flex-1 btn-primary text-sm"
              >
                全部导入（含重复）
              </button>
            </div>
            <button
              onClick={() => { setShowDuplicateDialog(false); setDuplicates([]) }}
              className="w-full mt-2 py-2 text-warm-muted hover:text-warm-text transition-colors text-sm"
            >
              取消
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
