import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export type RetrievalMode = 'rag' | 'entity' | 'both'

export const chatApi = {
  sendMessage: (
    sessionId: string,
    message: string,
    retrievalMode: RetrievalMode = 'both',
    enableWebSearch: boolean = false,
  ) =>
    fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        message,
        retrieval_mode: retrievalMode,
        enable_web_search: enableWebSearch,
      }),
    }),

  getSessions: () => api.get<import('../types').Session[]>('/sessions'),

  createSession: () => api.post<import('../types').Session>('/sessions'),

  getMessages: (sessionId: string) =>
    api.get<import('../types').Message[]>(`/sessions/${sessionId}/messages`),

  deleteSession: (sessionId: string) =>
    api.delete(`/sessions/${sessionId}`),

  renameSession: (sessionId: string, title: string) =>
    api.patch(`/sessions/${sessionId}`, { title }),
}

export const diaryApi = {
  create: (date: string, content: string, extra?: { location?: string; weather?: string; temperature?: string; humidity?: string }) =>
    api.post<import('../types').Diary>('/diary', { date, content, ...extra }),

  list: (limit = 200, offset = 0) =>
    api.get<import('../types').Diary[]>('/diary', { params: { limit, offset } }),

  get: (id: string) => api.get<import('../types').Diary>(`/diary/${id}`),

  update: (id: string, data: { content: string; date?: string }) =>
    api.put<import('../types').Diary>(`/diary/${id}`, data),

  reprocess: (id: string) =>
    api.post<{ ok: boolean; message: string }>(`/diary/${id}/reprocess`),

  search: (query: string) =>
    api.get<import('../types').Diary[]>('/diary/search', { params: { q: query } }),

  dates: () =>
    api.get<import('../types').DiaryDateItem[]>('/diary/dates/list'),

  checkDuplicate: (entries: { date: string; content: string }[]) =>
    api.post<{ duplicates: { index: number; date: string; content_preview: string; existing_id: string; existing_date: string }[] }>('/diary/check-duplicate', { entries }),

  getWeather: (latitude: number, longitude: number) =>
    api.get<{ location: string; weather: string; temperature: string; humidity: string }>('/diary/weather', { params: { latitude, longitude } }),
}

export const profileApi = {
  getProfiles: () => api.get<import('../types').ProfileFragment[]>('/profile'),

  getProfile: (id: string) => api.get<import('../types').ProfileFragment>(`/profile/${id}`),

  getCharacterSummary: () =>
    api.get<import('../types').CharacterSummary>('/profile/character/summary'),

  exportProfiles: () => api.get('/profile/export'),

  deleteAllProfiles: () => api.delete('/profile/all'),

  getChanges: () =>
    api.get<import('../types').ProfileChange[]>('/profile/changes'),

  acknowledgeChange: (changeId: string) =>
    api.put(`/profile/changes/${changeId}/acknowledge`),

  generateDetailedPortrait: () =>
    api.post<import('../types').PortraitResult>('/profile/generate/detailed'),

  generateDeepPortrait: () =>
    api.post<import('../types').PortraitResult>('/profile/generate/deep'),

  getPortraitRecords: (type?: string) =>
    api.get<import('../types').PortraitRecord[]>('/profile/records', { params: { type } }),

  getPortraitVersions: (type: string) =>
    api.get<import('../types').PortraitVersionItem[]>('/profile/versions', { params: { type } }),

  getPortraitVersion: (versionId: string) =>
    api.get<import('../types').PortraitRecord>(`/profile/versions/${versionId}`),

  submitFeedback: (data: { target_type: string; target_slug: string; error_type: string; correction_text?: string }) =>
    api.post<{ status: string; id: string }>('/profile/feedback', data),

  listFeedback: (params?: { target_type?: string; is_active?: number }) =>
    api.get<unknown[]>('/profile/feedback', { params }),

  reactivateFeedback: (feedbackId: string) =>
    api.post<{ status: string }>(`/profile/feedback/${feedbackId}/reactivate`),

  deleteFeedback: (feedbackId: string) =>
    api.delete<{ status: string }>(`/profile/feedback/${feedbackId}`),

  getConflicts: (status?: string) =>
    api.get<unknown[]>('/profile/conflicts', { params: { status } }),

  resolveConflict: (conflictId: string) =>
    api.post<{ status: string }>(`/profile/conflicts/${conflictId}/resolve`),

  dismissConflict: (conflictId: string) =>
    api.post<{ status: string }>(`/profile/conflicts/${conflictId}/dismiss`),
}

export const timelineApi = {
  getEvents: (params?: { event_type?: string; start_date?: string; end_date?: string; min_importance?: number; limit?: number; offset?: number }) =>
    api.get<import('../types').TimelineEvent[]>('/timeline', { params }),

  getEvent: (id: string) => api.get<import('../types').TimelineEvent>(`/timeline/${id}`),

  getSentimentStats: (period: 'week' | 'month' | 'all') =>
    api.get<Array<{ date: string; avg_sentiment: number; count: number }>>('/timeline/sentiment-stats', { params: { period } }),

  getOverviewStats: () =>
    api.get<{ total: number; type_counts: Record<string, number>; sentiment: { pos_count: number; neg_count: number; neutral_count: number; no_sentiment: number } }>('/timeline/overview-stats'),

  confirmEvent: (eventId: string) =>
    api.put<import('../types').TimelineEvent>(`/timeline/events/${eventId}/confirm`),

  updateEvent: (eventId: string, data: { summary?: string; content?: string; event_type?: string; timestamp?: string; importance_score?: number; is_milestone?: boolean; sentiment?: number }) =>
    api.put<import('../types').TimelineEvent>(`/timeline/events/${eventId}`, data),
}

export const importApi = {
  importWechat: (contactName: string, messages: Record<string, unknown>[], privacyTier: import('../types').PrivacyTier) =>
    api.post<import('../types').WechatImportResponse>('/import/wechat', {
      contact_name: contactName,
      messages,
      privacy_tier: privacyTier,
    }),

  importWechatTier2: (contactName: string, messages: Record<string, unknown>[]) =>
    api.post<import('../types').WechatImportResponse>('/import/wechat/tier2', {
      contact_name: contactName,
      messages,
    }),

  importWechatTier3: (contactName: string, messages: Record<string, unknown>[]) =>
    api.post<import('../types').WechatImportResponse>('/import/wechat/tier3', {
      contact_name: contactName,
      messages,
    }),

  getBatches: () =>
    api.get<import('../types').ImportBatch[]>('/import/batches'),

  deleteBatch: (batchId: string) =>
    api.delete(`/import/${batchId}`),

  getPrivacy: (contactName: string) =>
    api.get<import('../types').WechatPrivacyInfo>(`/import/privacy/${encodeURIComponent(contactName)}`),

  updatePrivacy: (contactName: string, data: { privacy_tier: import('../types').PrivacyTier; tier2_authorized?: boolean; tier3_authorized?: boolean }) =>
    api.put(`/import/privacy/${encodeURIComponent(contactName)}`, data),

  importMedia: (data: import('../types').MediaImportRequest) =>
    api.post<import('../types').MediaImportResponse>('/import/media', data),

  listMedia: (params?: { media_type?: string; q?: string }) =>
    api.get<import('../types').MediaRecord[]>('/import/media', { params }),

  importConsumption: (csvContent: string, source: string) =>
    api.post<{ items: import('../types').ConsumptionItem[]; inferred_habits: import('../types').ConsumptionHabit[] }>('/import/consumption', {
      csv_content: csvContent,
      source,
    }),

  confirmConsumption: (items: import('../types').ConsumptionItem[], habits: import('../types').ConsumptionHabit[]) =>
    api.post<{ written_count: number; habit_count: number }>('/import/consumption/confirm', {
      items,
      habits,
    }),

  importDiary: (entries: { date: string; content: string }[]) =>
    api.post<{ imported_count: number; message: string }>('/import/diary', {
      entries,
    }),
}

export const knowledgeApi = {
  search: (query: string) =>
    api.post<import('../types').KnowledgeItem[]>('/knowledge/search', { query }),

  list: (type?: string) =>
    api.get<import('../types').KnowledgeItem[]>('/knowledge', { params: { type } }),

  get: (kbId: string) =>
    api.get<import('../types').KnowledgeDetail>(`/knowledge/${kbId}`),

  deepen: (kbId: string) =>
    api.post<import('../types').KnowledgeDetail>(`/knowledge/${kbId}/deepen`),
}

export const gbrainApi = {
  listPages: (params?: { type?: string; sort?: string; limit?: number; offset?: number }) =>
    api.get<{ items: import('../types').PageListItem[]; total: number }>('/knowledge/pages', { params }),

  getPage: (slug: string) =>
    api.get<import('../types').PageDetail>(`/knowledge/pages/${encodeURIComponent(slug)}`),

  createPage: (data: { title: string; type?: string; compiled_truth?: string; timeline?: import('../types').TimelineEntry[] }) =>
    api.post<import('../types').PageDetail>('/knowledge/pages', data),

  updatePage: (slug: string, data: import('../types').PageUpdateRequest) =>
    api.put<import('../types').PageDetail>(`/knowledge/pages/${encodeURIComponent(slug)}`, data),

  deletePage: (slug: string) =>
    api.delete(`/knowledge/pages/${encodeURIComponent(slug)}`),

  search: (query: string, options?: { mode?: import('../types').SearchMode; limit?: number; sources?: string[]; rerank?: boolean; graph?: boolean }) => {
    const body: Record<string, unknown> = { query }
    if (options?.mode) body.mode = options.mode
    if (options?.limit) body.limit = options.limit
    if (options?.sources) body.sources = options.sources
    if (options?.rerank !== undefined) body.rerank = options.rerank
    if (options?.graph !== undefined) body.graph = options.graph
    return api.post<{ results: import('../types').SearchResult[]; mode: string }>('/knowledge/search', body)
  },

  getBacklinks: (slug: string) =>
    api.get<{ slug: string; backlinks: import('../types').BacklinkEntry[] }>(`/knowledge/backlinks/${encodeURIComponent(slug)}`),

  getBacklinksIndex: () =>
    api.get<Record<string, import('../types').BacklinkEntry[]>>('/knowledge/backlinks'),

  getGraph: (params?: { type?: string; slug?: string; depth?: number }) =>
    api.get<import('../types').KnowledgeGraph>('/knowledge/graph', { params }),

  ingest: (directory: string) =>
    api.post<{ imported: number; skipped: number; errors: string[] }>('/knowledge/ingest', { directory }),

  health: () =>
    api.get<import('../types').HealthReport>('/knowledge/health'),

  stats: () =>
    api.get<import('../types').StatsResponse>('/knowledge/stats'),

  compile: (entityTag: string) =>
    api.post<{ status: string }>('/knowledge/compile', { entity_tag: entityTag }),

  generateWeeklyProfile: () => api.post('/knowledge/profile/weekly'),
  getWeeklyProfile: () =>
    api.get<{ compiled_truth: string; title: string; updated_at: string; slug: string; versions: { id: number; version_number: number; compiled_truth_snapshot: string; created_at: string }[] }>('/knowledge/profile/weekly'),
  generateMonthlyProfile: () => api.post('/knowledge/profile/monthly'),
  getMonthlyProfile: () =>
    api.get<{ compiled_truth: string; title: string; updated_at: string; slug: string; versions: { id: number; version_number: number; compiled_truth_snapshot: string; created_at: string }[] }>('/knowledge/profile/monthly'),
  generateOverallProfile: (strategy?: string) => api.post('/knowledge/profile/overall', null, { params: { strategy: strategy || 'time_weighted' } }),
  getOverallProfile: () =>
    api.get<{ compiled_truth: string; title: string; updated_at: string; versions: { id: number; version_number: number; compiled_truth_snapshot: string; created_at: string }[] }>('/knowledge/profile/overall'),

  // Memory endpoints (pre-aggregation layer)
  generateMonthlyMemory: (yearMonth?: string) => api.post('/knowledge/memory/monthly', null, { params: yearMonth ? { year_month: yearMonth } : {} }),
  getMonthlyMemory: (yearMonth?: string) =>
    api.get<{ compiled_truth: string; title: string; updated_at: string; slug: string; frontmatter: Record<string, unknown> }>('/knowledge/memory/monthly', { params: yearMonth ? { year_month: yearMonth } : {} }),
  generateYearlyMemory: (year?: number) => api.post('/knowledge/memory/yearly', null, { params: year ? { year } : {} }),
  getYearlyMemory: (year?: number) =>
    api.get<{ compiled_truth: string; title: string; updated_at: string; slug: string; frontmatter: Record<string, unknown> }>('/knowledge/memory/yearly', { params: year ? { year } : {} }),

  lint: () => api.get('/knowledge/lint'),

  mergePages: (targetSlug: string, sourceSlugs: string[]) =>
    api.post<import('../types').PageDetail & { merge_snapshot_id?: string }>('/knowledge/pages/merge', {
      target_slug: targetSlug,
      source_slugs: sourceSlugs,
    }),

  undoMerge: (snapshotId: string) =>
    api.post<{ ok: boolean; message: string; target_slug: string }>('/knowledge/pages/merge/undo', {
      snapshot_id: snapshotId,
    }),

  getMergeSuggestions: () =>
    api.get<{ suggestions: { target_slug: string; target_title: string; source_slugs: string[]; source_titles: string[]; reason: string; type: string }[] }>('/knowledge/merge-suggestions'),
}

export const monitorApi = {
  getStatus: () =>
    api.get<import('../types').MonitorStatus>('/monitor/status'),

  getPending: () =>
    api.get<import('../types').MonitorPending>('/monitor/pending'),

  getFailedDiaries: () =>
    api.get<{ failed_count: number; failed_diaries: { id: string; date: string; content_preview: string }[] }>('/monitor/failed-diaries'),

  retryFailed: () =>
    api.post<{ retried: number; succeeded: number; still_failed: number }>('/monitor/retry-failed'),

  deleteEvent: (eventId: string) =>
    api.delete<{ ok: boolean; deleted_id: string }>(`/monitor/events/${eventId}`),

  updateEvent: (eventId: string, data: { summary?: string; event_type?: string; timestamp?: string; importance_score?: number }) =>
    api.put<import('../types').TimelineEvent>(`/monitor/events/${eventId}`, data),
}

export const settingsApi = {
  exportProfiles: () => api.get('/profile/export'),
  deleteAllProfiles: () => api.delete('/profile/all'),
  getPrivacyTier: (contactName: string) => api.get(`/import/privacy/${encodeURIComponent(contactName)}`),
  updatePrivacyTier: (contactName: string, tier: string) => api.put(`/import/privacy/${encodeURIComponent(contactName)}`, { privacy_tier: tier }),
}

export const insightApi = {
  getEmotionSeason: (params?: { year?: number; month?: number }) =>
    api.get<{ daily: import('../types').EmotionSeasonDay[]; monthly_avg: Record<string, number> }>('/insight/emotion-season', { params }),
}

export const quicknoteApi = {
  // Quick Note
  create: (content: string) =>
    api.post<import('../types').QuickNote>('/quicknote', { content }),

  list: (limit = 50, offset = 0) =>
    api.get<import('../types').QuickNote[]>('/quicknote', { params: { limit, offset } }),

  get: (id: string) =>
    api.get<import('../types').QuickNote>(`/quicknote/${id}`),

  update: (id: string, content: string) =>
    api.put<import('../types').QuickNote>(`/quicknote/${id}`, { content }),

  delete: (id: string) =>
    api.delete(`/quicknote/${id}`),

  reprocess: (id: string) =>
    api.post<{ ok: boolean; message: string }>(`/quicknote/${id}/reprocess`),

  // Expense Records
  createExpense: (data: { amount: number; category: string; description?: string; note?: string; expense_date: string }) =>
    api.post<import('../types').ExpenseRecord>('/quicknote/expense', data),

  listExpenses: (params?: { expense_date?: string; category?: string; start_date?: string; end_date?: string; limit?: number; offset?: number }) =>
    api.get<import('../types').ExpenseRecord[]>('/quicknote/expense', { params }),

  updateExpense: (id: string, data: { amount?: number; category?: string; description?: string; note?: string; expense_date?: string }) =>
    api.put<import('../types').ExpenseRecord>(`/quicknote/expense/${id}`, data),

  deleteExpense: (id: string) =>
    api.delete(`/quicknote/expense/${id}`),

  getExpenseStats: (params?: { start_date?: string; end_date?: string }) =>
    api.get<import('../types').ExpenseStats>('/quicknote/expense/stats', { params }),
}

export default api
