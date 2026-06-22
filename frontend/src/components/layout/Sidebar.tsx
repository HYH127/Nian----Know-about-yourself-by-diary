import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  MessageSquare, BookOpen, Clock, BookMarked, Upload, Settings, Activity, Sparkles, ChevronLeft, ChevronRight, User, Users, StickyNote
} from 'lucide-react'

interface NavItem {
  to: string
  icon: React.ComponentType<{ size?: number; strokeWidth?: number; className?: string }>
  label: string
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    title: '核心',
    items: [
      { to: '/', icon: MessageSquare, label: '对话' },
      { to: '/diary', icon: BookOpen, label: '日记' },
      { to: '/quicknote', icon: StickyNote, label: '随手记' },
    ],
  },
  {
    title: '记忆',
    items: [
      { to: '/knowledge', icon: BookMarked, label: '实体' },
      { to: '/timeline', icon: Clock, label: '时间线' },
      { to: '/insight', icon: Sparkles, label: '洞察' },
      { to: '/import', icon: Upload, label: '导入' },
    ],
  },
  {
    title: '系统',
    items: [
      { to: '/monitor', icon: Activity, label: '监控' },
      { to: '/settings', icon: Settings, label: '设置' },
    ],
  },
]

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const location = useLocation()

  return (
    <motion.aside
      className="h-screen flex flex-col border-r border-warm-border/60 bg-warm-sidebar shrink-0 relative z-20"
      initial={false}
      animate={{ width: collapsed ? 72 : 256 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-5 border-b border-warm-border/50">
        <div className="w-9 h-9 rounded-xl bg-warm-accent/15 flex items-center justify-center shrink-0">
          <span className="text-lg font-bold font-heading text-warm-accent">念</span>
        </div>
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="ml-3 overflow-hidden"
            >
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Nav Groups */}
      <nav className="flex-1 py-5 px-3 space-y-6 overflow-y-auto">
        {navGroups.map((group) => (
          <div key={group.title}>
            {/* Group Title */}
            <AnimatePresence>
              {!collapsed && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden"
                >
                  <h3 className="px-3 mb-2 text-[11px] font-semibold tracking-wider text-warm-faint uppercase">
                    {group.title}
                  </h3>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Group Items */}
            <div className="space-y-0.5">
              {group.items.map(({ to, icon: Icon, label }) => {
                const isActive = location.pathname === to || (to !== '/' && location.pathname.startsWith(to))
                return (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    className={({ isActive: active }) =>
                      `flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 relative group ${
                        active
                          ? 'bg-warm-highlight text-warm-accent-deep shadow-elevated-1'
                          : 'text-warm-muted hover:bg-warm-overlay hover:text-warm-text'
                      }`
                    }
                  >
                    <div className="relative">
                      <Icon
                        size={20}
                        strokeWidth={isActive ? 2 : 1.5}
                        className="shrink-0"
                      />
                      {/* Active dot indicator for collapsed mode */}
                      {isActive && collapsed && (
                        <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-warm-accent" />
                      )}
                    </div>
                    <AnimatePresence>
                      {!collapsed && (
                        <motion.span
                          initial={{ opacity: 0, width: 0 }}
                          animate={{ opacity: 1, width: 'auto' }}
                          exit={{ opacity: 0, width: 0 }}
                          className="text-[13px] font-medium whitespace-nowrap overflow-hidden"
                        >
                          {label}
                        </motion.span>
                      )}
                    </AnimatePresence>
                    {/* Active pill indicator for expanded mode */}
                    {isActive && !collapsed && (
                      <motion.div
                        layoutId="activeNav"
                        className="absolute right-2 top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-warm-accent"
                        transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                      />
                    )}
                  </NavLink>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Collapse Toggle */}
      <div className="p-3 border-t border-warm-border/50">
        <button
          onClick={onToggle}
          className="w-full flex items-center justify-center py-2.5 rounded-xl text-warm-faint hover:bg-warm-overlay hover:text-warm-muted transition-all duration-200"
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
        >
          <motion.div
            animate={{ rotate: collapsed ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronLeft size={18} />
          </motion.div>
        </button>
      </div>
    </motion.aside>
  )
}
