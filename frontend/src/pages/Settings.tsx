import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Save, Download, Trash2, Shield, AlertTriangle, ChevronDown, ChevronRight, Check, Settings as SettingsIcon } from 'lucide-react'
import { settingsApi, importApi, profileApi } from '../api'
import type { WechatPrivacyInfo, PrivacyTier } from '../types'
import PageHeader from '../components/layout/PageHeader'
import PageContainer from '../components/layout/PageContainer'

const PRIVACY_TIERS: Record<PrivacyTier, { label: string; desc: string; color: string }> = {
  tier1: { label: 'Tier 1', desc: '仅基础事实（姓名、事件）', color: 'text-warm-sage' },
  tier2: { label: 'Tier 2', desc: '行为模式与互动频率', color: 'text-warm-amber' },
  tier3: { label: 'Tier 3', desc: '深层情感与心理推断', color: 'text-warm-danger' },
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [dashscopeKey, setDashscopeKey] = useState(() => localStorage.getItem('dashscope_api_key') || '')
  const [tavilyKey, setTavilyKey] = useState(() => localStorage.getItem('tavily_api_key') || '')
  const [showDashscope, setShowDashscope] = useState(false)
  const [showTavily, setShowTavily] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [downgradeConfirm, setDowngradeConfirm] = useState<{ contactName: string; fromTier: PrivacyTier; toTier: PrivacyTier } | null>(null)

  const { data: batches = [] } = useQuery({
    queryKey: ['import-batches'],
    queryFn: async () => {
      const res = await importApi.getBatches()
      return res.data
    },
  })

  const contactNames = [...new Set(batches.map(b => b.contact_name))]

  const handleSaveKeys = () => {
    if (dashscopeKey) localStorage.setItem('dashscope_api_key', dashscopeKey)
    else localStorage.removeItem('dashscope_api_key')
    if (tavilyKey) localStorage.setItem('tavily_api_key', tavilyKey)
    else localStorage.removeItem('tavily_api_key')
    setSaveMsg('API Key 已保存')
    setTimeout(() => setSaveMsg(''), 2000)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const res = await profileApi.exportProfiles()
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `profile_export_${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      alert('导出失败，请重试')
    } finally {
      setExporting(false)
    }
  }

  const handleDeleteAll = async () => {
    setDeleting(true)
    try {
      await profileApi.deleteAllProfiles()
      setDeleteConfirmOpen(false)
      queryClient.clear()
      alert('所有数据已删除')
    } catch {
      alert('删除失败，请重试')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <PageContainer className="max-w-2xl">
      <PageHeader title="设置" icon={<SettingsIcon size={20} />} />

      <div className="space-y-6 stagger-enter">
        {/* API Key 配置 */}
        <section className="section-card space-y-4">
          <h2 className="section-title flex items-center gap-2 border-b border-warm-border/50 pb-3">
            <div className="w-7 h-7 rounded-lg bg-warm-accent/15 flex items-center justify-center">
              <Shield size={14} className="text-warm-accent" />
            </div>
            API Key 配置
          </h2>

          <div className="space-y-3">
            <div>
              <label className="block text-xs text-warm-muted mb-1.5 font-medium">DashScope API Key</label>
              <div className="relative">
                <input
                  type={showDashscope ? 'text' : 'password'}
                  value={dashscopeKey}
                  onChange={e => setDashscopeKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full input-enhanced pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowDashscope(!showDashscope)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-warm-muted hover:text-warm-text transition-colors"
                >
                  {showDashscope ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs text-warm-muted mb-1.5 font-medium">Tavily API Key</label>
              <div className="relative">
                <input
                  type={showTavily ? 'text' : 'password'}
                  value={tavilyKey}
                  onChange={e => setTavilyKey(e.target.value)}
                  placeholder="tvly-..."
                  className="w-full input-enhanced pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowTavily(!showTavily)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-warm-muted hover:text-warm-text transition-colors"
                >
                  {showTavily ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleSaveKeys}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-warm-accent hover:bg-warm-accent-hover text-white text-sm font-medium btn-primary"
            >
              <Save size={14} />
              保存
            </button>
            {saveMsg && <span className="text-xs text-green-500 animate-fade-in flex items-center gap-1"><Check size={12} /> {saveMsg}</span>}
          </div>
        </section>

        {/* 隐私设置 */}
        <section className="section-card space-y-4">
          <h2 className="section-title flex items-center gap-2 border-b border-warm-border/50 pb-3">
            <div className="w-7 h-7 rounded-lg bg-blue-500/15 flex items-center justify-center">
              <Shield size={14} className="text-blue-400" />
            </div>
            隐私分级设置
          </h2>

          <div className="space-y-2 text-xs text-warm-muted bg-warm-input/40 rounded-xl p-3 border border-warm-border/30">
            <p><span className="text-warm-sage font-medium">Tier 1</span> — 仅提取基础事实信息（姓名、事件时间等）</p>
            <p><span className="text-warm-amber font-medium">Tier 2</span> — 提取行为模式与互动频率（需授权）</p>
            <p><span className="text-warm-danger font-medium">Tier 3</span> — 提取深层情感与心理推断（需授权，有时效）</p>
          </div>

          <div className="text-xs text-warm-faint flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-warm-success/60" />
            数据使用范围：所有数据仅存储在本地，不会上传至第三方服务。
          </div>

          {contactNames.length > 0 && (
            <div className="space-y-2 mt-3">
              <h3 className="text-xs font-medium text-warm-muted uppercase tracking-wider">联系人隐私分级</h3>
              {contactNames.map(name => (
                <div key={name} className="list-item">
                  <ContactPrivacyRow
                    contactName={name}
                    onDowngradeConfirm={setDowngradeConfirm}
                  />
                </div>
              ))}
            </div>
          )}
        </section>

        {/* 数据管理 */}
        <section className="section-card space-y-4">
          <h2 className="section-title flex items-center gap-2 border-b border-warm-border/50 pb-3">
            <div className="w-7 h-7 rounded-lg bg-orange-500/15 flex items-center justify-center">
              <Shield size={14} className="text-orange-500" />
            </div>
            数据管理
          </h2>

          <div className="space-y-3">
            <button
              onClick={handleExport}
              disabled={exporting}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-warm-input text-warm-muted hover:text-warm-text text-sm transition-all btn-press disabled:opacity-50"
            >
              <Download size={14} className="text-warm-accent" />
              {exporting ? '导出中...' : '导出画像数据'}
            </button>

            <button
              onClick={() => setDeleteConfirmOpen(true)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/15 text-red-500 text-sm border border-red-500/20 hover:border-red-500/30 transition-all btn-press"
            >
              <Trash2 size={14} />
              删除所有数据
            </button>
          </div>

          {/* 导入历史 */}
          {batches.length > 0 && (
            <div className="mt-4">
              <h3 className="text-xs font-medium text-warm-muted uppercase tracking-wider mb-2">导入历史</h3>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {batches.map(batch => (
                  <div key={batch.id} className="list-item flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-warm-text font-medium">{batch.contact_name}</span>
                      <span className={`px-1.5 py-0.5 rounded-md text-[10px] font-medium ${PRIVACY_TIERS[batch.privacy_tier]?.color || 'text-warm-muted'} bg-current/10`}>
                        {batch.privacy_tier}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-warm-faint">
                      <span>{batch.message_count} 条</span>
                      <span>{new Date(batch.created_at).toLocaleDateString('zh-CN')}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      {/* 删除确认弹窗 */}
      {deleteConfirmOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-warm-card rounded-2xl border border-warm-border p-6 max-w-sm w-full mx-4 space-y-4 shadow-2xl animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-red-500/15 flex items-center justify-center">
                <AlertTriangle size={20} className="text-red-500" />
              </div>
              <h3 className="font-semibold text-warm-text">确认删除</h3>
            </div>
            <p className="text-sm text-warm-text leading-relaxed">
              此操作将删除所有画像数据，且不可恢复。确定要继续吗？
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setDeleteConfirmOpen(false)}
                className="px-4 py-2 rounded-xl bg-warm-input text-warm-muted hover:text-warm-text text-sm transition-all btn-press"
              >
                取消
              </button>
              <button
                onClick={handleDeleteAll}
                disabled={deleting}
                className="px-4 py-2 rounded-xl bg-red-500 hover:bg-red-600 text-white text-sm font-medium shadow-sm shadow-red-500/20 transition-all btn-press disabled:opacity-50"
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 降级确认弹窗 */}
      {downgradeConfirm && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
          <div className="bg-warm-card rounded-2xl border border-warm-border p-6 max-w-sm w-full mx-4 space-y-4 shadow-2xl animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-yellow-500/15 flex items-center justify-center">
                <AlertTriangle size={20} className="text-yellow-600" />
              </div>
              <h3 className="font-semibold text-warm-text">隐私降级确认</h3>
            </div>
            <p className="text-sm text-warm-text leading-relaxed">
              将 <span className="text-warm-text font-medium">{downgradeConfirm.contactName}</span> 从{' '}
              <span className={PRIVACY_TIERS[downgradeConfirm.fromTier]?.color}>
                {PRIVACY_TIERS[downgradeConfirm.fromTier]?.label}
              </span> 降级为{' '}
              <span className={PRIVACY_TIERS[downgradeConfirm.toTier]?.color}>
                {PRIVACY_TIERS[downgradeConfirm.toTier]?.label}
              </span>
            </p>
            <p className="text-xs text-yellow-600/80 bg-yellow-500/10 rounded-lg p-2.5 border border-yellow-500/20 flex items-start gap-1.5">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <span>降级将清除该联系人高层级的数据，此操作不可恢复。</span>
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setDowngradeConfirm(null)}
                className="px-4 py-2 rounded-xl bg-warm-input text-warm-muted hover:text-warm-text text-sm transition-all btn-press"
              >
                取消
              </button>
              <button
                onClick={async () => {
                  try {
                    await settingsApi.updatePrivacyTier(downgradeConfirm.contactName, downgradeConfirm.toTier)
                    queryClient.invalidateQueries({ queryKey: ['privacy', downgradeConfirm.contactName] })
                    queryClient.invalidateQueries({ queryKey: ['import-batches'] })
                  } catch {
                    alert('更新失败')
                  }
                  setDowngradeConfirm(null)
                }}
                className="px-4 py-2 rounded-xl bg-yellow-600 hover:bg-yellow-700 text-white text-sm font-medium shadow-sm shadow-yellow-600/20 transition-all btn-press"
              >
                确认降级
              </button>
            </div>
          </div>
        </div>
      )}
    </PageContainer>
  )
}

const TIER_ORDER: PrivacyTier[] = ['tier1', 'tier2', 'tier3']

function ContactPrivacyRow({ contactName, onDowngradeConfirm }: { contactName: string; onDowngradeConfirm: (v: { contactName: string; fromTier: PrivacyTier; toTier: PrivacyTier } | null) => void }) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)

  const { data: privacyInfo } = useQuery({
    queryKey: ['privacy', contactName],
    queryFn: async () => {
      const res = await importApi.getPrivacy(contactName)
      return res.data as WechatPrivacyInfo
    },
  })

  const currentTier = privacyInfo?.privacy_tier || 'tier1'

  const handleTierChange = (newTier: PrivacyTier) => {
    const fromIdx = TIER_ORDER.indexOf(currentTier)
    const toIdx = TIER_ORDER.indexOf(newTier)
    if (toIdx < fromIdx) {
      onDowngradeConfirm({ contactName, fromTier: currentTier as PrivacyTier, toTier: newTier })
    } else {
      settingsApi.updatePrivacyTier(contactName, newTier).then(() => {
        queryClient.invalidateQueries({ queryKey: ['privacy', contactName] })
      }).catch(() => {
        alert('更新失败')
      })
    }
  }

  return (
    <div className="rounded-lg bg-warm-input/50 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm text-warm-text hover:bg-warm-input/80 transition-colors"
      >
        <span>{contactName}</span>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${PRIVACY_TIERS[currentTier as PrivacyTier]?.color || 'text-warm-muted'}`}>
            {PRIVACY_TIERS[currentTier as PrivacyTier]?.label || currentTier}
          </span>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {TIER_ORDER.map(tier => (
            <label key={tier} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name={`tier-${contactName}`}
                checked={currentTier === tier}
                onChange={() => handleTierChange(tier)}
                className="accent-warm-accent"
              />
              <span className={`text-xs ${PRIVACY_TIERS[tier].color}`}>{PRIVACY_TIERS[tier].label}</span>
              <span className="text-xs text-warm-faint">— {PRIVACY_TIERS[tier].desc}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
