import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, MessageSquare, PanelLeftClose, PanelLeft, Send, Loader2, AlertTriangle, X, MessageCircle, Globe, ChevronDown, Wrench } from 'lucide-react'
import PageContainer from '../components/layout/PageContainer'
import PageHeader from '../components/layout/PageHeader'
import { chatApi, profileApi, type RetrievalMode } from '../api'
import type { Message, ProfileChange, ChangeType, ContextLabel, WebSearchResult, ToolCallRecord } from '../types'

const RETRIEVAL_MODE_STORAGE_KEY = 'nn_retrieval_mode'
const WEB_SEARCH_STORAGE_KEY = 'nn_web_search'

const RETRIEVAL_MODE_LABELS: Record<RetrievalMode, string> = {
  rag: '仅 RAG',
  entity: '仅实体图',
  both: 'RAG + 实体图',
}

const CHANGE_TYPE_LABELS: Record<ChangeType, string> = {
  habit_fading: '习惯消退',
  trait_shift: '特质转变',
  preference_change: '偏好变化',
  decision_pattern: '决策模式',
}

const CONTEXT_ICONS: Record<string, string> = {
  family: '家庭',
  work: '工作',
  decision: '决策',
  social: '社交',
  health: '健康',
  learning: '学习',
  emotion: '情感',
  daily: '日常',
}

export default function Chat() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [streamingMessages, setStreamingMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sending, setSending] = useState(false)
  const [dismissedChanges, setDismissedChanges] = useState<Set<string>>(new Set())
  const [currentContext, setCurrentContext] = useState<ContextLabel | null>(null)
  const [contextMenu, setContextMenu] = useState<{ sessionId: string; x: number; y: number } | null>(null)
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>(() => {
    try {
      const saved = localStorage.getItem(RETRIEVAL_MODE_STORAGE_KEY) as RetrievalMode | null
      return saved && ['rag', 'entity', 'both'].includes(saved) ? saved : 'both'
    } catch {
      return 'both'
    }
  })
  const [webSearchEnabled, setWebSearchEnabled] = useState<boolean>(() => {
    try {
      return localStorage.getItem(WEB_SEARCH_STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })
  const renameInputRef = useRef<HTMLInputElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: sessions = [] } = useQuery({
    queryKey: ['sessions'],
    queryFn: async () => {
      try {
        const res = await chatApi.getSessions()
        return Array.isArray(res.data) ? res.data : ((res.data as any)?.sessions || [])
      } catch {
        return []
      }
    },
  })

  const effectiveSessionId = currentSessionId || (sessions.length > 0 ? sessions[0].session_id : null)

  const { data: sessionMessages = [] } = useQuery({
    queryKey: ['messages', effectiveSessionId],
    queryFn: async () => {
      if (!effectiveSessionId) return []
      try {
        const res = await chatApi.getMessages(effectiveSessionId)
        return Array.isArray(res.data) ? res.data : []
      } catch {
        return []
      }
    },
    enabled: !!effectiveSessionId,
  })

  const { data: unacknowledgedChanges = [] } = useQuery({
    queryKey: ['profile-changes-unack'],
    queryFn: async () => {
      try {
        const res = await profileApi.getChanges()
        return ((res.data as ProfileChange[]) || []).filter(c => !c.is_acknowledged)
      } catch {
        return []
      }
    },
    refetchInterval: 30000,
  })

  const visibleChanges = useMemo(() =>
    unacknowledgedChanges.filter(c => !dismissedChanges.has(c.id))
  , [unacknowledgedChanges, dismissedChanges])

  const createSessionMutation = useMutation({
    mutationFn: () => chatApi.createSession(),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      setCurrentSessionId(res.data.session_id || res.data.id)
    },
  })

  const displayMessages = useMemo(() =>
    streamingMessages.length > 0
      ? [...sessionMessages, ...streamingMessages]
      : sessionMessages
  , [sessionMessages, streamingMessages])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [displayMessages, scrollToBottom])

  useEffect(() => {
    if (!contextMenu) return
    const close = () => setContextMenu(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [contextMenu])

  useEffect(() => {
    if (renamingSessionId && renameInputRef.current) {
      renameInputRef.current.focus()
      renameInputRef.current.select()
    }
  }, [renamingSessionId])

  // 监听全局检索模式变化（来自 Monitor 页面设置）
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === RETRIEVAL_MODE_STORAGE_KEY && e.newValue) {
        const mode = e.newValue as RetrievalMode
        if (['rag', 'entity', 'both'].includes(mode)) {
          setRetrievalMode(mode)
        }
      }
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  const handleCreateSession = () => {
    setStreamingMessages([])
    setDismissedChanges(new Set())
    setCurrentContext(null)
    createSessionMutation.mutate()
  }

  const handleSwitchSession = (sessionId: string) => {
    if (sending) return
    setStreamingMessages([])
    setDismissedChanges(new Set())
    setCurrentContext(null)
    setCurrentSessionId(sessionId)
  }

  const handleContextMenu = (e: React.MouseEvent, sessionId: string) => {
    e.preventDefault()
    setContextMenu({ sessionId, x: e.clientX, y: e.clientY })
  }

  const handleStartRename = (sessionId: string, currentTitle: string) => {
    setContextMenu(null)
    setRenamingSessionId(sessionId)
    setRenameValue(currentTitle || '新会话')
  }

  const handleRenameSubmit = async (sessionId: string) => {
    const trimmed = renameValue.trim()
    if (!trimmed) {
      setRenamingSessionId(null)
      return
    }
    try {
      await chatApi.renameSession(sessionId, trimmed)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } catch {}
    setRenamingSessionId(null)
  }

  const handleRenameCancel = () => {
    setRenamingSessionId(null)
  }

  const handleDeleteSession = async (sessionId: string) => {
    setContextMenu(null)
    if (!confirm('确定要删除该会话吗？')) return
    try {
      await chatApi.deleteSession(sessionId)
      if (effectiveSessionId === sessionId) {
        setCurrentSessionId(null)
        setStreamingMessages([])
      }
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    } catch {}
  }

  useEffect(() => {
    const sessionParam = searchParams.get('session')
    if (sessionParam && sessions.length > 0) {
      const match = sessions.find(s => s.session_id === sessionParam || s.id === sessionParam)
      if (match) setCurrentSessionId(match.session_id)
    }
  }, [searchParams, sessions])

  const handleDismissChange = (changeId: string) => {
    setDismissedChanges(prev => new Set(prev).add(changeId))
    profileApi.acknowledgeChange(changeId).catch(() => {})
  }

  const sendMessage = async (content: string) => {
    if (!content.trim() || sending) return

    let sessionId = effectiveSessionId
    if (!sessionId) {
      try {
        const res = await chatApi.createSession()
        sessionId = res.data.session_id || res.data.id
        queryClient.invalidateQueries({ queryKey: ['sessions'] })
        setCurrentSessionId(sessionId)
      } catch {
        return
      }
    }

    const userMessage: Message = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: content.trim(),
      mode: 'chat',
      session_id: sessionId,
      created_at: new Date().toISOString(),
    }

    const assistantMessage: Message = {
      id: `temp-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      mode: 'chat',
      session_id: sessionId,
      created_at: new Date().toISOString(),
    }

    setStreamingMessages([userMessage, assistantMessage])
    setInput('')
    setSending(true)

    try {
      const response = await chatApi.sendMessage(sessionId, content.trim(), retrievalMode, webSearchEnabled)

      const reader = response.body?.getReader()
      if (!reader) return

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.done) {
                // 流式传输完成
              } else if (data.content) {
                setStreamingMessages(prev => {
                  const updated = [...prev]
                  const lastMsg = updated[updated.length - 1]
                  if (lastMsg && lastMsg.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...lastMsg,
                      content: lastMsg.content + data.content,
                    }
                  }
                  return updated
                })
              }
              if (data.context) {
                setCurrentContext(data.context as ContextLabel)
              }
              if (data.data_confirmation) {
                setStreamingMessages(prev => {
                  const updated = [...prev]
                  const lastMsg = updated[updated.length - 1]
                  if (lastMsg && lastMsg.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...lastMsg,
                      showDataConfirmation: true,
                    }
                  }
                  return updated
                })
              }
              if (data.tool_call) {
                const tc = data.tool_call as ToolCallRecord
                // 收集所有工具调用记录
                setStreamingMessages(prev => {
                  const updated = [...prev]
                  const lastMsg = updated[updated.length - 1]
                  if (lastMsg && lastMsg.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...lastMsg,
                      toolCalls: [...(lastMsg.toolCalls || []), tc],
                    }
                  }
                  return updated
                })
                // web_search 结果同时存入 webSearchResults 用于展示搜索来源卡片
                if (tc.name === 'web_search') {
                  const searchResults: WebSearchResult[] = (tc.result as { results?: WebSearchResult[] })?.results || []
                  if (searchResults.length > 0) {
                    setStreamingMessages(prev => {
                      const updated = [...prev]
                      const lastMsg = updated[updated.length - 1]
                      if (lastMsg && lastMsg.role === 'assistant') {
                        updated[updated.length - 1] = {
                          ...lastMsg,
                          webSearchResults: [...(lastMsg.webSearchResults || []), ...searchResults],
                        }
                      }
                      return updated
                    })
                  }
                }
              }
              if (data.retrieval_source) {
                setStreamingMessages(prev => {
                  const updated = [...prev]
                  const lastMsg = updated[updated.length - 1]
                  if (lastMsg && lastMsg.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...lastMsg,
                      retrievalSource: data.retrieval_source as string,
                    }
                  }
                  return updated
                })
              }
            } catch {
              // 解析失败跳过
            }
          }
        }
      }

      if (buffer.startsWith('data: ')) {
        try {
          const data = JSON.parse(buffer.slice(6))
          if (data.content) {
            setStreamingMessages(prev => {
              const updated = [...prev]
              const lastMsg = updated[updated.length - 1]
              if (lastMsg && lastMsg.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...lastMsg,
                  content: lastMsg.content + data.content,
                }
              }
              return updated
            })
          }
          if (data.context) {
            setCurrentContext(data.context as ContextLabel)
          }
        } catch {
          // 解析失败跳过
        }
      }
    } catch {
      setStreamingMessages(prev => {
        const updated = [...prev]
        const lastMsg = updated[updated.length - 1]
        if (lastMsg && lastMsg.role === 'assistant') {
          updated[updated.length - 1] = {
            ...lastMsg,
            content: '消息发送失败，请重试',
          }
        }
        return updated
      })
    } finally {
      setSending(false)
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
      queryClient.invalidateQueries({ queryKey: ['messages', effectiveSessionId] }).then(() => {
        setStreamingMessages([])
      })
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const isToday = date.toDateString() === now.toDateString()
    if (isToday) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
  }

  return (
    <PageContainer className="h-full flex flex-col !p-0 !max-w-none">
      <div className="flex h-full">
        {/* 左侧会话列表 */}
        {sidebarOpen && (
          <div className="w-64 flex flex-col bg-warm-sidebar shrink-0 border-r border-warm-border/60">
            <div className="p-3 pb-2">
              <button
                onClick={handleCreateSession}
                className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-warm-accent hover:bg-warm-accent-hover text-white shadow-elevated-1 btn-primary btn-press transition-all text-sm font-medium"
              >
                <Plus size={16} />
                新建会话
              </button>
            </div>
            <div className="flex-1 overflow-y-auto stagger-enter px-2">
              {sessions.map(session => (
                renamingSessionId === session.session_id ? (
                  <div className="my-1 px-3 py-2.5 rounded-xl" key={session.session_id}>
                    <input
                      ref={renameInputRef}
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRenameSubmit(session.session_id)
                        if (e.key === 'Escape') handleRenameCancel()
                      }}
                      onBlur={() => handleRenameSubmit(session.session_id)}
                      className="w-full px-2 py-1 rounded-lg bg-warm-input text-sm text-warm-text border border-warm-accent/50 outline-none focus:ring-2 focus:ring-warm-accent/20 focus:border-warm-accent transition-all surface-inset focus-ring-enhanced"
                    />
                  </div>
                ) : (
                <button
                  key={session.session_id}
                  onClick={() => handleSwitchSession(session.session_id)}
                  onContextMenu={(e) => handleContextMenu(e, session.session_id)}
                  className={`w-full text-left my-1 px-3 py-2.5 rounded-xl transition-all duration-200 btn-press relative overflow-hidden list-item ${
                    effectiveSessionId === session.session_id
                      ? 'bg-warm-highlight text-warm-accent-deep border-warm-accent/20'
                      : 'text-warm-text hover:bg-warm-overlay/40'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {effectiveSessionId === session.session_id && (
                      <span className="w-1.5 h-1.5 rounded-full bg-warm-accent shrink-0" />
                    )}
                    <span className="truncate text-sm font-medium">
                      {session.title && session.title !== '新会话'
                        ? session.title.length > 8 ? session.title.slice(0, 8) + '…' : session.title
                        : '…'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-warm-faint">
                      {session.last_message_at ? formatTime(session.last_message_at) : ''}
                    </span>
                    <span className="text-xs text-warm-faint ml-auto">{session.message_count || 0}轮</span>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-warm-border/20 rounded-full">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${effectiveSessionId === session.session_id ? 'bg-warm-accent/60' : 'bg-warm-accent/30'}`}
                      style={{ width: `${Math.min(100, ((session.message_count || 0) / 20) * 100)}%` }}
                    />
                  </div>
                </button>
              )))}
              {sessions.length === 0 && (
                <div className="p-4 text-center text-warm-faint text-sm empty-state">
                  暂无会话
                </div>
              )}
            </div>
            {contextMenu && (
              <div
                className="fixed z-50 bg-warm-card border border-warm-border rounded-xl shadow-elevated-3 py-1 min-w-[120px] animate-fade-in"
                style={{ left: contextMenu.x, top: contextMenu.y }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => handleStartRename(contextMenu.sessionId,
                    sessions.find(s => s.session_id === contextMenu.sessionId)?.title || '新会话')}
                  className="w-full text-left px-4 py-2 text-sm text-warm-text hover:bg-warm-input transition-colors rounded-t-xl"
                >
                  重命名
                </button>
                <button
                  onClick={() => handleDeleteSession(contextMenu.sessionId)}
                  className="w-full text-left px-4 py-2 text-sm text-red-500 hover:bg-warm-input transition-colors rounded-b-xl"
                >
                  删除会话
                </button>
              </div>
            )}
          </div>
        )}

        {/* 右侧对话主区域 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 顶部栏 */}
          <div className="flex items-center gap-3 px-6 py-3 border-b border-warm-border/50 bg-warm-bg/80 backdrop-blur-sm">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 rounded-lg hover:bg-warm-input text-warm-muted hover:text-warm-text transition-colors btn-press"
            >
              {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
            </button>
            <span className="text-sm font-heading font-medium text-warm-text">
              {sessions.find(s => s.id === effectiveSessionId)?.title || '对话'}
            </span>
          </div>

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {displayMessages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center animate-fade-in">
                  <div className="w-20 h-20 rounded-full bg-gradient-to-br from-warm-accent/15 to-warm-accent/10 flex items-center justify-center mx-auto mb-4 shadow-elevated-2">
                    <MessageCircle size={36} className="text-warm-accent/60" />
                  </div>
                  <p className="text-lg text-warm-accent font-heading font-medium">开始和念念对话</p>
                  <p className="text-sm mt-1.5 text-warm-faint">输入消息，记录你的想法</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4 max-w-3xl mx-auto">
                {visibleChanges.length > 0 && (
                  <div className="space-y-2 animate-fade-in">
                    <div
                      className="flex items-center gap-2 px-3 py-2.5 rounded-xl card-base border border-orange-400/30 cursor-pointer select-none surface-raised hover:shadow-elevated-2 transition-all"
                      onClick={() => {
                        const el = document.getElementById('chat-changes-detail')
                        if (el) el.classList.toggle('hidden')
                      }}
                    >
                      <AlertTriangle size={14} className="text-orange-500 shrink-0" />
                      <span className="text-xs text-warm-text font-medium">
                        {visibleChanges.length} 条画像变化提醒（点击展开/收起）
                      </span>
                    </div>
                    <div id="chat-changes-detail" className="hidden space-y-2">
                      {visibleChanges.map(change => (
                        <div
                          key={change.id}
                          className="flex items-start gap-3 p-3 rounded-xl card-base border border-orange-500/30 animate-fade-in"
                        >
                          <AlertTriangle size={16} className="text-orange-500 shrink-0 mt-0.5" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-xs font-medium text-warm-text">
                                {CHANGE_TYPE_LABELS[change.change_type] || change.change_type}
                              </span>
                            </div>
                            <p className="text-sm text-warm-text">{change.description}</p>
                          </div>
                          <button
                            onClick={() => handleDismissChange(change.id)}
                            className="shrink-0 p-1 rounded-lg hover:bg-orange-500/20 text-orange-500/60 hover:text-orange-500 transition-colors btn-press"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {displayMessages.map(msg => (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                  >
                    <div
                      className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words ${
                        msg.role === 'user'
                          ? 'bg-gradient-to-br from-[#B8D4E3] to-[#A8C8DB] text-warm-text rounded-br-md whitespace-pre-wrap shadow-elevated-1 surface-inset'
                          : 'bg-warm-card border border-warm-border/60 text-warm-text rounded-bl-md shadow-elevated-1 surface-inset'
                      }`}
                    >
                      {msg.role === 'assistant' ? (
                        <ChatMessageContent
                          content={msg.content}
                          webSearchResults={msg.webSearchResults}
                          toolCalls={msg.toolCalls}
                          retrievalSource={msg.retrievalSource}
                        />
                      ) : (
                        msg.content || <Loader2 size={16} className="animate-spin inline" />
                      )}
                    </div>
                    {msg.role === 'assistant' && msg.showDataConfirmation && (
                      <div className="mt-1 flex items-center gap-2">
                        <button
                          onClick={() => {
                            setStreamingMessages(prev => {
                              const updated = [...prev]
                              const idx = updated.findIndex(m => m.id === msg.id)
                              if (idx >= 0) {
                                updated[idx] = { ...updated[idx], showDataConfirmation: false }
                              }
                              return updated
                            })
                            sendMessage('这些数据对吗？帮我确认一下')
                          }}
                          className="text-xs px-3 py-1 rounded-full bg-warm-accent/15 text-warm-accent hover:bg-warm-accent/25 border border-warm-accent/30 transition-colors"
                        >
                          这些数据对吗？
                        </button>
                        <button
                          onClick={() => {
                            setStreamingMessages(prev => {
                              const updated = [...prev]
                              const idx = updated.findIndex(m => m.id === msg.id)
                              if (idx >= 0) {
                                updated[idx] = { ...updated[idx], showDataConfirmation: false }
                              }
                              return updated
                            })
                          }}
                          className="text-xs px-2 py-1 rounded-full bg-warm-input text-warm-muted hover:text-warm-text transition-colors"
                        >
                          忽略
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* 底部输入区 */}
          <div className="bg-warm-bg/50 px-6 py-3 border-t border-warm-border/50">
            <div className="max-w-3xl mx-auto">
              {currentContext && (
                <div className="flex items-center gap-2 mb-2 animate-fade-in">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium card-base text-warm-highlight-text border border-warm-accent/30 surface-raised">
                    {CONTEXT_ICONS[currentContext.label] || currentContext.label}
                  </span>
                </div>
              )}

              {/* 检索模式切换 */}
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-[11px] text-warm-faint mr-1">检索模式</span>
                {(Object.keys(RETRIEVAL_MODE_LABELS) as RetrievalMode[]).map(mode => (
                  <button
                    key={mode}
                    onClick={() => {
                      setRetrievalMode(mode)
                      try { localStorage.setItem(RETRIEVAL_MODE_STORAGE_KEY, mode) } catch {}
                    }}
                    className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${
                      retrievalMode === mode
                        ? 'bg-warm-accent text-white shadow-elevated-1'
                        : 'bg-warm-input text-warm-muted hover:text-warm-text border border-warm-border/50'
                    }`}
                  >
                    {RETRIEVAL_MODE_LABELS[mode]}
                  </button>
                ))}
              </div>

              {/* 联网搜索开关 */}
              <div className="flex items-center gap-1.5 mb-2">
                <Globe size={12} className="text-warm-faint" />
                <span className="text-[11px] text-warm-faint mr-1">联网搜索</span>
                <button
                  onClick={() => {
                    const next = !webSearchEnabled
                    setWebSearchEnabled(next)
                    try { localStorage.setItem(WEB_SEARCH_STORAGE_KEY, String(next)) } catch {}
                  }}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${
                    webSearchEnabled
                      ? 'bg-warm-accent text-white shadow-elevated-1'
                      : 'bg-warm-input text-warm-muted hover:text-warm-text border border-warm-border/50'
                  }`}
                >
                  {webSearchEnabled ? '已开启' : '已关闭'}
                </button>
              </div>

              <div className="flex items-end gap-2">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息..."
                  rows={1}
                  className="flex-1 resize-none rounded-xl bg-warm-input border border-warm-border px-4 py-2.5 text-sm text-warm-text placeholder-warm-muted focus:outline-none focus:border-warm-accent focus:ring-2 focus:ring-warm-accent/20 transition-all surface-inset focus-ring-enhanced input-enhanced"
                  style={{ maxHeight: '120px' }}
                  onInput={e => {
                    const target = e.target as HTMLTextAreaElement
                    target.style.height = 'auto'
                    target.style.height = Math.min(target.scrollHeight, 120) + 'px'
                  }}
                />
                <button
                  onClick={() => sendMessage(input)}
                  disabled={!input.trim() || sending}
                  className="shrink-0 p-2.5 rounded-xl bg-warm-accent hover:bg-warm-accent-hover text-white shadow-elevated-1 hover:shadow-elevated-2 disabled:opacity-40 disabled:cursor-not-allowed transition-all btn-primary btn-press fab"
                >
                  <Send size={18} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </PageContainer>
  )
}

/** Render assistant chat message with lightweight markdown support */
function ChatMessageContent({
  content,
  webSearchResults,
  toolCalls,
  retrievalSource,
}: {
  content: string
  webSearchResults?: WebSearchResult[]
  toolCalls?: ToolCallRecord[]
  retrievalSource?: string
}) {
  const [showProcess, setShowProcess] = useState(false)

  const hasProcess = (toolCalls && toolCalls.length > 0) || retrievalSource

  if (!content && !hasProcess) return <Loader2 size={16} className="animate-spin inline" />

  const blocks = content ? parseChatContent(content) : []
  return (
    <div className="space-y-2">
      {/* 调用过程面板（可折叠） */}
      {hasProcess && (
        <CallProcessPanel
          toolCalls={toolCalls}
          retrievalSource={retrievalSource}
          expanded={showProcess}
          onToggle={() => setShowProcess(!showProcess)}
        />
      )}
      {blocks.map((block, i) => {
        if (block.type === 'quote') {
          return (
            <div key={i} className="pl-3 border-l-2 border-warm-accent/40 text-warm-muted text-sm">
              <InlineMarkdown text={block.text} />
            </div>
          )
        }
        if (block.type === 'list') {
          return (
            <div key={i} className="space-y-1">
              {block.items.map((item, j) => (
                <div key={j} className="flex items-start gap-2 text-sm">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-warm-accent/50 mt-1.5 shrink-0" />
                  <InlineMarkdown text={item} />
                </div>
              ))}
            </div>
          )
        }
        // paragraph
        return (
          <p key={i} className="text-sm">
            <InlineMarkdown text={block.text} />
          </p>
        )
      })}
      {webSearchResults && webSearchResults.length > 0 && (
        <div className="mt-2 pt-2 border-t border-warm-border/40">
          <div className="flex items-center gap-1.5 mb-1.5">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-warm-accent/60">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
            <span className="text-[11px] text-warm-muted font-medium">搜索来源</span>
          </div>
          <div className="space-y-1.5">
            {webSearchResults.slice(0, 3).map((result, idx) => (
              <a
                key={idx}
                href={result.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block px-2.5 py-1.5 rounded-lg bg-warm-bg/50 hover:bg-warm-accent/10 border border-warm-border/30 hover:border-warm-accent/30 transition-all group"
              >
                <div className="flex items-start gap-2">
                  <span className="text-[10px] text-warm-faint mt-0.5 shrink-0">{idx + 1}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium text-warm-text group-hover:text-warm-accent transition-colors truncate">
                      {result.title}
                    </div>
                    {result.content && (
                      <div className="text-[11px] text-warm-muted mt-0.5 line-clamp-2 leading-relaxed">
                        {result.content.slice(0, 120)}{result.content.length > 120 ? '…' : ''}
                      </div>
                    )}
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

type ChatBlock = { type: 'paragraph'; text: string } | { type: 'list'; items: string[] } | { type: 'quote'; text: string }

// 检索来源标签映射
const RETRIEVAL_SOURCE_LABELS: Record<string, string> = {
  entity_graph: '实体图谱',
  profile_rag: '画像检索',
  timeline_rag: '时间线检索',
  rag: 'RAG 检索',
}

// 工具名称标签映射
const TOOL_LABELS: Record<string, string> = {
  web_search: '联网搜索',
  get_current_date: '获取时间',
}

/** 调用过程面板：展示模型使用的检索来源和工具调用 */
function CallProcessPanel({
  toolCalls,
  retrievalSource,
  expanded,
  onToggle,
}: {
  toolCalls?: ToolCallRecord[]
  retrievalSource?: string
  expanded: boolean
  onToggle: () => void
}) {
  const tags: string[] = []
  if (retrievalSource) tags.push(RETRIEVAL_SOURCE_LABELS[retrievalSource] || retrievalSource)
  if (toolCalls) {
    for (const tc of toolCalls) {
      const label = TOOL_LABELS[tc.name] || tc.name
      if (!tags.includes(label)) tags.push(label)
    }
  }

  return (
    <div className="rounded-lg bg-warm-bg/40 border border-warm-border/40 overflow-hidden">
      {/* 折叠标题栏 */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-warm-bg/60 transition-colors"
      >
        <Wrench size={11} className="text-warm-accent/60 shrink-0" />
        <span className="text-[11px] text-warm-muted font-medium shrink-0">调用过程</span>
        <div className="flex items-center gap-1 flex-wrap">
          {tags.map((tag, i) => (
            <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-warm-accent/10 text-warm-accent/80 border border-warm-accent/20">
              {tag}
            </span>
          ))}
        </div>
        <ChevronDown
          size={12}
          className={`text-warm-faint ml-auto transition-transform shrink-0 ${expanded ? 'rotate-180' : ''}`}
        />
      </button>

      {/* 展开内容 */}
      {expanded && (
        <div className="px-3 pb-2.5 pt-0.5 space-y-1.5 border-t border-warm-border/30">
          {/* 检索来源 */}
          {retrievalSource && (
            <div className="flex items-start gap-2 pt-1.5">
              <span className="text-[10px] text-warm-faint mt-0.5 shrink-0 w-10">检索</span>
              <span className="text-[11px] text-warm-muted">
                {RETRIEVAL_SOURCE_LABELS[retrievalSource] || retrievalSource}
              </span>
            </div>
          )}
          {/* 工具调用详情 */}
          {toolCalls?.map((tc, i) => (
            <div key={i} className="flex items-start gap-2 pt-1.5">
              <span className="text-[10px] text-warm-faint mt-0.5 shrink-0 w-10">工具</span>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] text-warm-text font-medium">
                  {TOOL_LABELS[tc.name] || tc.name}
                </div>
                {tc.args && Object.keys(tc.args).length > 0 && (
                  <div className="text-[10px] text-warm-muted mt-0.5 font-mono break-all">
                    {JSON.stringify(tc.args)}
                  </div>
                )}
                {tc.result && (
                  <div className="text-[10px] text-warm-faint mt-0.5">
                    {tc.name === 'web_search' && typeof tc.result === 'object' && tc.result !== null && 'result_count' in tc.result
                      ? `返回 ${(tc.result as { result_count: number }).result_count} 条结果`
                      : tc.name === 'get_current_date' && typeof tc.result === 'object' && tc.result !== null && 'date' in tc.result
                        ? `${(tc.result as { date: string; weekday: string }).date} ${(tc.result as { weekday: string }).weekday}`
                        : '已返回结果'}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function parseChatContent(text: string): ChatBlock[] {
  const blocks: ChatBlock[] = []
  const lines = text.split('\n')
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // Empty line - skip
    if (!line.trim()) {
      i++
      continue
    }

    // Quote block: > text
    if (line.trimStart().startsWith('> ')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trimStart().startsWith('> ')) {
        quoteLines.push(lines[i].trimStart().slice(2))
        i++
      }
      blocks.push({ type: 'quote', text: quoteLines.join('') })
      continue
    }

    // List block: - text or * text
    if (/^[\s]*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[\s]*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[\s]*[-*]\s+/, ''))
        i++
      }
      blocks.push({ type: 'list', items })
      continue
    }

    // Paragraph - collect consecutive non-empty, non-special lines
    const paraLines: string[] = []
    while (i < lines.length) {
      const pLine = lines[i]
      if (!pLine.trim() || /^[\s]*[-*]\s+/.test(pLine) || pLine.trimStart().startsWith('> ')) break
      paraLines.push(pLine)
      i++
    }
    if (paraLines.length > 0) {
      // Smart join: no space between CJK characters, space otherwise
      const joined = paraLines.map((line, idx) => {
        if (idx === 0) return line
        const prevLast = paraLines[idx - 1].slice(-1)
        const currFirst = line[0]
        const isCJK = (c: string) => /[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u2000-\u206f]/.test(c)
        if (isCJK(prevLast) && isCJK(currFirst)) return line
        return ' ' + line
      }).join('')
      blocks.push({ type: 'paragraph', text: joined })
    }
  }

  return blocks
}

/** Inline markdown: **bold**, *italic*, `code` */
function InlineMarkdown({ text }: { text: string }) {
  // Split by inline patterns: **bold**, *italic*, `code`
  const parts = text.split(/(\*\*.+?\*\*|\*.+?\*|`.+?`)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('*') && part.endsWith('*') && !part.startsWith('**')) {
      return <em key={i}>{part.slice(1, -1)}</em>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="px-1 py-0.5 rounded bg-warm-accent/10 text-warm-accent text-xs">{part.slice(1, -1)}</code>
    }
    return <span key={i}>{part}</span>
  })
}
