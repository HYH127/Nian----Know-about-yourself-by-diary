import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

/* ════════════════════════════════════════════════════════
 *  Welcome.tsx — 《晨日手记》v2
 *  温暖人文主义 · 一本手边的日记本
 *  动画时序：
 *    idle      → 初始静止，书本合起
 *    opening   → 缓慢翻开一点（~55度），2000ms
 *    peek      → 停在翻开状态，书脊光慢慢透出，1500ms
 *    opened    → 淡出并转跳主页面，600ms
 * ════════════════════════════════════════════════════════ */

interface WelcomeProps {
  onDismiss: () => void
}

function formatChineseDate(date: Date): string {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  const day = date.getDate()
  const weekDay = ['日', '一', '二', '三', '四', '五', '六'][date.getDay()]
  const digits = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九']

  const toChineseNum = (n: number): string => {
    if (n < 10) return digits[n]
    if (n < 20) return '十' + (n % 10 === 0 ? '' : digits[n % 10])
    if (n < 100) {
      const tens = Math.floor(n / 10)
      const ones = n % 10
      return digits[tens] + '十' + (ones === 0 ? '' : digits[ones])
    }
    return n.toString()
  }

  const yearStr = year.toString().split('').map(d => digits[parseInt(d)] ?? d).join('')
  return yearStr + '年' + toChineseNum(month) + '月' + toChineseNum(day) + '日'
}

function formatWeekday(date: Date): string {
  const weekDay = ['日', '一', '二', '三', '四', '五', '六'][date.getDay()]
  return '星期' + weekDay
}

function getTimeOfDay(hour: number): string {
  if (hour >= 5 && hour < 11) return '清晨'
  if (hour >= 11 && hour < 14) return '中午'
  if (hour >= 14 && hour < 18) return '下午'
  if (hour >= 18 && hour < 22) return '傍晚'
  return '夜深'
}

function Welcome({ onDismiss }: WelcomeProps) {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<'idle' | 'opening' | 'peek' | 'opened'>('idle')
  const [greetingText, setGreetingText] = useState('记录今天的想法')
  const [dateText, setDateText] = useState('')
  const [weekdayText, setWeekdayText] = useState('')
  const [timeOfDay, setTimeOfDay] = useState('')
  const [reducedMotion, setReducedMotion] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)

  // 初始化问候语和日期
  useEffect(() => {
    const now = new Date()
    const hour = now.getHours()
    setDateText(formatChineseDate(now))
    setWeekdayText(formatWeekday(now))
    setTimeOfDay(getTimeOfDay(hour))
    if (hour >= 5 && hour < 12) {
      setGreetingText('早上好 · 记录今日所思')
    } else if (hour >= 12 && hour < 18) {
      setGreetingText('下午好 · 记录今日所思')
    } else if (hour >= 18 && hour < 23) {
      setGreetingText('晚上好 · 记录今日所思')
    } else {
      setGreetingText('夜深了 · 记录今日所思')
    }
  }, [])

  // 减少运动支持
  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReducedMotion(mql.matches)
    const handler = (e: MediaQueryListEvent) => setReducedMotion(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [])

  // 键盘支持
  const handleEnter = useCallback(() => {
    if (phase !== 'idle') return
    setPhase('opening')
  }, [phase])

  const handleSkip = useCallback(() => {
    if (phase !== 'idle') return
    setPhase('opening')
  }, [phase])

  // 动画时序驱动：opening → peek → opened
  useEffect(() => {
    if (phase === 'opening') {
      // 页面翻开阶段（2000ms）→ 进入 peek 阶段
      const toPeek = setTimeout(() => setPhase('peek'), reducedMotion ? 500 : 2000)
      return () => clearTimeout(toPeek)
    }
    if (phase === 'peek') {
      // 停顿 + 光透出 + 笔迹可见（2400ms）→ 进入 opened 并转跳
      const toOpened = setTimeout(() => {
        setPhase('opened')
      }, reducedMotion ? 600 : 2400)
      return () => clearTimeout(toOpened)
    }
    if (phase === 'opened') {
      // 淡出 + 导航
      const navTimer = setTimeout(() => {
        onDismiss()
        navigate('/')
      }, reducedMotion ? 300 : 700)
      return () => clearTimeout(navTimer)
    }
  }, [phase, onDismiss, navigate, reducedMotion])

  const isOpening = phase === 'opening' || phase === 'peek' || phase === 'opened'
  const inPeek = phase === 'peek'
  const isOpened = phase === 'opened'

  // 预计算过渡时长变量（避免 JSX 内 template literal）
  const tPageFlip = reducedMotion ? '500ms ease-out' : '2200ms cubic-bezier(0.25, 0.1, 0.3, 1)'
  const tPageFlipDelay = reducedMotion ? '0ms' : '100ms'
  const tSpineGlow = reducedMotion ? '400ms ease-in' : '1500ms ease-in'
  const tSpineGlowDelay = reducedMotion ? '0ms' : '1200ms'
  const tContentFade = reducedMotion ? '300ms ease-out' : '800ms ease-out'
  const tContentDelay = reducedMotion ? '0ms' : '200ms'
  const tBookLift = reducedMotion ? '400ms ease-out' : '1600ms cubic-bezier(0.25, 0.1, 0.3, 1)'
  const tBtnFade = reducedMotion ? '200ms ease-out' : '400ms ease-out'
  const tShadow = reducedMotion ? '300ms ease-out' : '1400ms ease-out'
  const tOpacityFast = reducedMotion ? '200ms ease-out' : '500ms ease-out'
  const tOuterFade = reducedMotion ? '300ms ease-out' : '700ms ease-out'
  const tInnerLight = reducedMotion ? '500ms ease-in' : '1400ms ease-in'
  const tInnerLightDelay = reducedMotion ? '0ms' : '800ms'
  // 笔迹动画（比 tInnerLight 更慢一点，让纸张先亮起来再出现笔迹）
  const tWriting = reducedMotion ? '400ms ease-out' : '900ms ease-out'

  return (
    <div
      ref={wrapperRef}
      className="fixed inset-0 flex items-center justify-center overflow-hidden"
      style={{
        background: '#FAF7F4',
        opacity: isOpened ? 0 : 1,
        transition: isOpened ? 'opacity ' + tOuterFade : 'none',
      }}
      onClick={handleEnter}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          handleEnter()
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          handleSkip()
        }
      }}
      role="presentation"
    >
      {/* 纸页舞台 */}
      <div
        className="relative"
        style={{
          perspective: '2200px',
          cursor: phase === 'idle' ? 'pointer' : 'default',
        }}
      >
        {/* 纸页舞台容器 — 水平放置，翻开时略微上升 */}
        <div
          style={{
            width: 'min(1200px, 90vw)',
            height: 'min(700px, 82vh)',
            transformStyle: 'preserve-3d',
            transform: isOpening ? 'translateY(-4px)' : 'translateY(0)',
            transition: isOpening
              ? 'transform ' + tBookLift
              : 'none',
          }}
        >
          {/* 底纸 — 翻开后露出的日记本主体，从翻开开始就慢慢变亮 */}
          <div
            className="absolute inset-0"
            style={{
              background: 'linear-gradient(180deg, #FFFCF8 0%, #F6EFE5 50%, #F2E8DB 100%)',
              borderRadius: '2px',
              opacity: isOpening ? 1 : 0.85,
              transition: 'opacity ' + tInnerLight,
              transitionDelay: tInnerLightDelay,
            }}
          >
            {/* 纸面纹理 */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                backgroundImage:
                  'radial-gradient(ellipse at 25% 20%, rgba(212, 133, 106, 0.04) 0%, transparent 45%), radial-gradient(ellipse at 75% 80%, rgba(212, 133, 106, 0.05) 0%, transparent 45%)',
                borderRadius: '2px',
              }}
            />
            {/* 纸边缘厚度描边 */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                boxShadow: 'inset 0 0 0 1px rgba(212, 133, 106, 0.1)',
                borderRadius: '2px',
              }}
            />

            {/* —— 翻开后露出的笔迹 —— */}
            {/* 左页笔迹 —— 左上角区域 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '12%',
                left: '8%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '15px',
                color: '#A08B78',
                fontStyle: 'italic',
                letterSpacing: '0.02em',
                opacity: isOpening ? 0.82 : 0,
                transform: isOpening ? 'translateY(0) rotate(-1.5deg)' : 'translateY(4px) rotate(-1.5deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '500ms',
                lineHeight: 1.9,
              }}
            >
              清晨 · 微雨
            </div>

            {/* 左页笔迹 —— 中上区 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '24%',
                left: '10%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '13px',
                color: '#9C8B78',
                fontStyle: 'italic',
                opacity: isOpening ? 0.75 : 0,
                transform: isOpening ? 'translateY(0) rotate(0.5deg)' : 'translateY(4px) rotate(0.5deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '650ms',
                lineHeight: 2,
                maxWidth: '180px',
              }}
            >
              她今天说：
            </div>

            {/* 左页笔迹 —— 中段两条小横线 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '32%',
                left: '10%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '12px',
                color: '#8B7A68',
                fontStyle: 'italic',
                opacity: isOpening ? 0.6 : 0,
                transform: isOpening ? 'translateY(0)' : 'translateY(4px)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '750ms',
                lineHeight: 2.2,
                maxWidth: '200px',
              }}
            >
              窗外好像有蝉声了。<br/>
              春天真的过去了。
            </div>

            {/* 左页笔迹 —— 页码（左下） */}
            <div
              className="absolute pointer-events-none"
              style={{
                bottom: '10%',
                left: '42%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '10px',
                color: '#B5A99E',
                opacity: isOpening ? 0.55 : 0,
                transition: 'opacity ' + tWriting,
                transitionDelay: '850ms',
                letterSpacing: '0.2em',
              }}
            >
              · 047 ·
            </div>

            {/* 左页笔迹 —— 右下处一条轻描 */}
            <div
              className="absolute pointer-events-none"
              style={{
                bottom: '18%',
                right: '6%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '12px',
                color: '#9C8B78',
                fontStyle: 'italic',
                opacity: isOpening ? 0.55 : 0,
                transform: isOpening ? 'translateY(0) rotate(2deg)' : 'translateY(4px) rotate(2deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '800ms',
                textAlign: 'right',
              }}
            >
              想起来了
            </div>

            {/* 右页笔迹 —— 日期行 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '12%',
                left: '56%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '14px',
                color: '#A08B78',
                fontStyle: 'italic',
                letterSpacing: '0.03em',
                opacity: isOpening ? 0.78 : 0,
                transform: isOpening ? 'translateY(0) rotate(-0.8deg)' : 'translateY(4px) rotate(-0.8deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '550ms',
                lineHeight: 1.9,
              }}
            >
              六月，十七日
            </div>

            {/* 右页笔迹 —— 第一条 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '26%',
                left: '56%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '13px',
                color: '#8B7A68',
                fontStyle: 'italic',
                opacity: isOpening ? 0.65 : 0,
                transform: isOpening ? 'translateY(0) rotate(0.3deg)' : 'translateY(4px) rotate(0.3deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '700ms',
                lineHeight: 2.2,
                maxWidth: '220px',
              }}
            >
              今天翻开这本本子，<br/>
              想把最近的一些事<br/>
              轻轻地记下来。
            </div>

            {/* 右页笔迹 —— 中段轻描 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '52%',
                left: '60%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '12px',
                color: '#A89888',
                fontStyle: 'italic',
                opacity: isOpening ? 0.45 : 0,
                transform: isOpening ? 'translateY(0) rotate(-1deg)' : 'translateY(4px) rotate(-1deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '800ms',
                lineHeight: 2.1,
                maxWidth: '200px',
              }}
            >
              （一些已经过去了的事。）
            </div>

            {/* 右页笔迹 —— 分隔线 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '68%',
                left: '56%',
                width: '70px',
                height: '1px',
                background: 'rgba(212, 133, 106, 0.25)',
                opacity: isOpening ? 0.7 : 0,
                transition: 'opacity ' + tWriting,
                transitionDelay: '850ms',
              }}
            />

            {/* 右页笔迹 —— 最后一句轻描 */}
            <div
              className="absolute pointer-events-none"
              style={{
                top: '74%',
                left: '56%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '12px',
                color: '#9C8B78',
                fontStyle: 'italic',
                opacity: isOpening ? 0.55 : 0,
                transform: isOpening ? 'translateY(0) rotate(1.2deg)' : 'translateY(4px) rotate(1.2deg)',
                transition: 'opacity ' + tWriting + ', transform ' + tWriting,
                transitionDelay: '880ms',
                lineHeight: 2,
              }}
            >
              —— 不过没关系。
            </div>

            {/* 右页笔迹 —— 右下页码 */}
            <div
              className="absolute pointer-events-none"
              style={{
                bottom: '10%',
                right: '42%',
                fontFamily: "'Source Serif 4', Georgia, serif",
                fontSize: '10px',
                color: '#B5A99E',
                opacity: isOpening ? 0.55 : 0,
                transition: 'opacity ' + tWriting,
                transitionDelay: '900ms',
                letterSpacing: '0.2em',
                textAlign: 'right',
              }}
            >
              · 048 ·
            </div>
          </div>

          {/* 书脊深度线 — 翻开后慢慢加深 */}
          <div
            className="absolute pointer-events-none"
            style={{
              top: '4%',
              bottom: '4%',
              left: '50%',
              width: '18px',
              transform: 'translateX(-50%)',
              background:
                'linear-gradient(to right, transparent 0%, rgba(62, 48, 37, 0.18) 25%, rgba(62, 48, 37, 0.3) 50%, rgba(62, 48, 37, 0.18) 75%, transparent 100%)',
              opacity: isOpening ? 0.7 : 0.3,
              transition: 'opacity ' + tSpineGlow,
              transitionDelay: '400ms',
              filter: 'blur(0.3px)',
            }}
          />

          {/* 书脊暖光 — 从书脊中缝透出的柔和暖光 */}
          <div
            className="absolute pointer-events-none"
            style={{
              top: '3%',
              bottom: '3%',
              left: '50%',
              width: '180px',
              transform: 'translateX(-50%)',
              background: 'radial-gradient(ellipse at center, rgba(255, 235, 210, 0.3) 0%, rgba(255, 220, 185, 0.15) 25%, rgba(255, 210, 170, 0.06) 50%, transparent 75%)',
              opacity: isOpening ? 1 : 0,
              transition: 'opacity ' + tSpineGlow,
              transitionDelay: '600ms',
              filter: 'blur(6px)',
            }}
          />

          {/* 书脊向上扩散的暖光晕 */}
          <div
            className="absolute pointer-events-none"
            style={{
              top: '-10%',
              bottom: '-10%',
              left: '50%',
              width: '420px',
              transform: 'translateX(-50%)',
              background: 'linear-gradient(to top, transparent 0%, rgba(255, 228, 200, 0.12) 20%, rgba(255, 220, 185, 0.15) 40%, rgba(255, 210, 170, 0.1) 60%, transparent 100%)',
              opacity: isOpening ? 0.85 : 0,
              transition: 'opacity ' + tSpineGlow,
              transitionDelay: '750ms',
              filter: 'blur(12px)',
            }}
          />

          {/* 左翻页（向左侧翻开一点）*/}
          <div
            className="absolute"
            style={{
              top: 0,
              left: 0,
              width: '50%',
              height: '100%',
              transformOrigin: 'left center',
              transform: isOpening
                ? 'rotateY(-55deg)'
                : 'rotateY(0deg)',
              transition: 'transform ' + tPageFlip,
              transitionDelay: '0ms',
              transformStyle: 'preserve-3d',
              backfaceVisibility: 'hidden',
            }}
          >
            {/* 正面 — 纸色 */}
            <div
              className="absolute inset-0"
              style={{
                borderRadius: '2px 0 0 2px',
                background: 'linear-gradient(90deg, #FBF7F0 0%, #F7F0E4 50%, #F2E9DB 100%)',
                backfaceVisibility: 'hidden',
                boxShadow: 'inset -2px 0 6px rgba(80, 60, 45, 0.06), 2px 0 0 rgba(44, 36, 32, 0.03)',
              }}
            >
              {/* 右边缘装订痕（靠近中缝）*/}
              <div
                className="absolute pointer-events-none"
                style={{
                  top: '6%',
                  bottom: '6%',
                  right: '1px',
                  width: '1px',
                  background: 'rgba(212, 133, 106, 0.15)',
                  opacity: isOpening ? 0 : 1,
                  transition: 'opacity 400ms ease-out',
                }}
              />
              {/* 纸纹 */}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  backgroundImage: 'radial-gradient(ellipse at 70% 40%, rgba(212, 133, 106, 0.04) 0%, transparent 50%)',
                  borderRadius: '2px 0 0 2px',
                }}
              />
              {/* 翻开过程中纸面受书脊光影响 — 内边缘微微变亮 */}
              <div
                className="absolute pointer-events-none"
                style={{
                  top: 0,
                  bottom: 0,
                  right: 0,
                  width: '30%',
                  background: 'linear-gradient(to right, transparent 0%, rgba(255, 230, 200, 0.12) 50%, rgba(255, 220, 185, 0.06) 100%)',
                  opacity: isOpening ? 1 : 0,
                  transition: 'opacity ' + tInnerLight,
                  transitionDelay: tInnerLightDelay,
                  borderRadius: '0 2px 2px 0',
                }}
              />
            </div>

            {/* 背面 — 稍深米色 */}
            <div
              className="absolute inset-0"
              style={{
                borderRadius: '2px 0 0 2px',
                background: 'linear-gradient(90deg, rgba(210, 190, 165, 0.98) 0%, rgba(225, 208, 185, 0.92) 50%, rgba(235, 220, 200, 0.85) 100%)',
                transform: 'rotateY(180deg)',
                backfaceVisibility: 'hidden',
                boxShadow: 'inset 2px 0 6px rgba(80, 60, 45, 0.12), inset -1px 0 0 rgba(212, 133, 106, 0.15)',
              }}
            />

            {/* 左页内容区 — 印章 + 标题 + 分隔线 + 副标题 + 页码 */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: isOpening ? 0 : 1,
                transform: isOpening ? 'translateY(10px)' : 'translateY(0)',
                transition: 'opacity ' + tContentFade + ', transform ' + tContentFade,
                transitionDelay: tContentDelay,
              }}
            >
              {/* 小印章 */}
              <div
                style={{
                  fontFamily: "'Source Serif 4', Georgia, serif",
                  fontSize: 'clamp(12px, 1.1vw, 14px)',
                  color: '#B85C3E',
                  letterSpacing: '0.15em',
                  fontWeight: 600,
                  padding: '6px 14px',
                  border: '1px solid rgba(184, 92, 62, 0.3)',
                  borderRadius: '2px',
                  marginBottom: 'clamp(32px, 5vh, 60px)',
                  opacity: 0.7,
                }}
              >
                念
              </div>

              {/* 主标题 */}
              <div
                style={{
                  fontFamily: "'Source Serif 4', Georgia, serif",
                  fontSize: 'clamp(48px, 5.8vw, 84px)',
                  fontWeight: 500,
                  color: '#2C2420',
                  letterSpacing: '0.06em',
                  lineHeight: 1,
                  marginBottom: 'clamp(16px, 2.2vh, 24px)',
                }}
              >
                念 · 念
              </div>

              {/* 分隔线 */}
              <div
                style={{
                  width: 'clamp(120px, 18vw, 200px)',
                  height: '1px',
                  background: 'rgba(212, 133, 106)',
                  opacity: 0.3,
                  marginBottom: 'clamp(16px, 2.2vh, 28px)',
                }}
              />

              {/* 副标题 */}
              <div
                style={{
                  fontFamily: "'DM Sans', -apple-system, sans-serif",
                  fontSize: 'clamp(11px, 0.9vw, 13px)',
                  color: '#7A6E64',
                  letterSpacing: '0.15em',
                  textAlign: 'center',
                  marginBottom: 'clamp(60px, 8vh, 120px)',
                }}
              >
                数字生活的记录
              </div>

              {/* 页码 */}
              <div
                style={{
                  fontFamily: "'Source Serif 4', Georgia, serif",
                  fontSize: 'clamp(10px, 0.8vw, 11px)',
                  color: '#B5A99E',
                  letterSpacing: '0.15em',
                  textAlign: 'center',
                  opacity: 0.7,
                }}
              >
                001 / ∞
              </div>
            </div>
          </div>

          {/* 右翻页（向右侧翻开一点） */}
          <div
            className="absolute"
            style={{
              top: 0,
              right: 0,
              width: '50%',
              height: '100%',
              transformOrigin: 'right center',
              transform: isOpening
                ? 'rotateY(55deg)'
                : 'rotateY(0deg)',
              transition: 'transform ' + tPageFlip,
              transitionDelay: tPageFlipDelay,
              transformStyle: 'preserve-3d',
              backfaceVisibility: 'hidden',
            }}
          >
            {/* 正面 — 纸色 */}
            <div
              className="absolute inset-0"
              style={{
                borderRadius: '0 2px 2px 0',
                background: 'linear-gradient(270deg, #FBF7F0 0%, #F7F0E4 50%, #F2E9DB 100%)',
                backfaceVisibility: 'hidden',
                boxShadow: 'inset 2px 0 4px rgba(80, 60, 45, 0.06), -2px 0 0 rgba(44, 36, 32, 0.03)',
              }}
            >
              {/* 左边缘装订痕 */}
              <div
                className="absolute pointer-events-none"
                style={{
                  top: '6%',
                  bottom: '6%',
                  left: '1px',
                  width: '1px',
                  background: 'rgba(212, 133, 106, 0.15)',
                  opacity: isOpening ? 0 : 1,
                  transition: 'opacity 400ms ease-out',
                }}
              />
              {/* 纸纹 */}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{
                  backgroundImage: 'radial-gradient(ellipse at 30% 60%, rgba(212, 133, 106, 0.04) 0%, transparent 50%)',
                  borderRadius: '0 2px 2px 0',
                }}
              />
              {/* 翻开过程中纸面受书脊光影响 — 内边缘微微变亮 */}
              <div
                className="absolute pointer-events-none"
                style={{
                  top: 0,
                  bottom: 0,
                  left: 0,
                  width: '30%',
                  background: 'linear-gradient(to left, transparent 0%, rgba(255, 230, 200, 0.12) 50%, rgba(255, 220, 185, 0.06) 100%)',
                  opacity: isOpening ? 1 : 0,
                  transition: 'opacity ' + tInnerLight,
                  transitionDelay: tInnerLightDelay,
                  borderRadius: '2px 0 0 2px',
                }}
              />
            </div>

            {/* 右页内容区 — 日期 + 引导语 + 书写横线 + 底部提示 */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                opacity: isOpening ? 0 : 1,
                transform: isOpening ? 'translateY(10px)' : 'translateY(0)',
                transition: 'opacity ' + tContentFade + ', transform ' + tContentFade,
                transitionDelay: tContentDelay,
              }}
            >
              {/* 顶部：日期 + 星期 */}
              <div
                style={{
                  position: 'absolute',
                  top: '10%',
                  left: '10%',
                  right: '10%',
                  textAlign: 'left',
                }}
              >
                <div
                  style={{
                    fontFamily: "'Source Serif 4', Georgia, serif",
                    fontSize: 'clamp(12px, 1.1vw, 14px)',
                    color: '#8B7355',
                    letterSpacing: '0.12em',
                    marginBottom: '6px',
                  }}
                >
                  {dateText}
                </div>
                <div
                  style={{
                    fontFamily: "'Source Serif 4', Georgia, serif",
                    fontSize: 'clamp(10px, 0.9vw, 12px)',
                    color: '#B5A99E',
                    letterSpacing: '0.12em',
                  }}
                >
                  {weekdayText} · {timeOfDay}
                </div>
                <div
                  style={{
                    width: '60px',
                    height: '1px',
                    background: 'rgba(212, 133, 106, 0.25)',
                    marginTop: '14px',
                  }}
                />
              </div>

              {/* 中部：引导语 + 书写横线区域 */}
              <div
                style={{
                  position: 'absolute',
                  top: '28%',
                  left: '10%',
                  right: '10%',
                  bottom: '22%',
                }}
              >
                {/* 引导语 */}
                <div
                  style={{
                    fontFamily: "'Source Serif 4', Georgia, serif",
                    fontSize: 'clamp(13px, 1.1vw, 15px)',
                    color: '#A08B78',
                    letterSpacing: '0.05em',
                    lineHeight: 1.8,
                    marginBottom: '24px',
                    fontStyle: 'italic',
                    opacity: 0.75,
                  }}
                >
                  今天想记录的是...
                </div>

                {/* 书写横线区域 */}
                <div
                  style={{
                    backgroundImage: 'repeating-linear-gradient(to top, transparent 0px, transparent 34px, rgba(212, 133, 106, 0.12) 34px, rgba(212, 133, 106, 0.12) 35px)',
                    height: '240px',
                    width: '100%',
                    borderRadius: '1px',
                  }}
                />
              </div>

              {/* 底部的提示 */}
              <div
                style={{
                  position: 'absolute',
                  bottom: '12%',
                  left: '10%',
                  right: '10%',
                  textAlign: 'center',
                  paddingTop: '10px',
                  borderTop: '1px solid rgba(212, 133, 106, 0.15)',
                }}
              >
                <span
                  style={{
                    fontFamily: "'DM Sans', -apple-system, sans-serif",
                    fontSize: 'clamp(11px, 0.9vw, 13px)',
                    color: '#7A6E64',
                    letterSpacing: '0.12em',
                  }}
                >
                  {greetingText}
                </span>
              </div>
            </div>

            {/* 右页 — 纸背阴影 */}
            <div
              className="absolute inset-0"
              style={{
                borderRadius: '0 2px 2px 0',
                background: 'linear-gradient(270deg, rgba(210, 190, 165, 0.98) 0%, rgba(225, 208, 185, 0.92) 50%, rgba(235, 220, 200, 0.85) 100%)',
                transform: 'rotateY(-180deg)',
                backfaceVisibility: 'hidden',
                boxShadow: 'inset -2px 0 6px rgba(80, 60, 45, 0.12), inset 1px 0 0 rgba(212, 133, 106, 0.15)',
              }}
            />
          </div>
        </div>

        {/* 书本主投影 — 翻开时加深 */}
        <div
          className="absolute left-1/2 pointer-events-none"
          style={{
            bottom: '-18px',
            width: '85%',
            height: '40px',
            transform: 'translate(-50%, 0)',
            opacity: isOpening ? 0.65 : 0.45,
            transition: 'opacity ' + tShadow,
            background: 'radial-gradient(ellipse at center, rgba(44, 36, 32, 0.15) 0%, rgba(44, 36, 32, 0.08) 35%, transparent 70%)',
            filter: 'blur(16px)',
          }}
        />
      </div>

      {/* 底部胶囊按钮 — 主交互焦点 */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          handleEnter()
        }}
        tabIndex={0}
        className="welcome-btn"
        style={{
          position: 'absolute',
          bottom: '6%',
          left: '50%',
          transform: isOpening ? 'translate(-50%, 8px)' : 'translate(-50%, 0)',
          opacity: isOpening ? 0 : 1,
          transition: 'opacity ' + tBtnFade + ', transform ' + tBtnFade,
          fontFamily: "'DM Sans', -apple-system, sans-serif",
          fontSize: '13px',
          letterSpacing: '0.15em',
          color: '#2C2420',
          background: '#FFFFFF',
          border: '1px solid rgba(212, 133, 106, 0.25)',
          padding: '10px 24px',
          borderRadius: '999px',
          cursor: 'pointer',
          boxShadow: '0 2px 8px rgba(44, 36, 32, 0.06), 0 1px 2px rgba(44, 36, 32, 0.03)',
          animation: !isOpening && !reducedMotion ? 'welcome-btn-pulse 2.4s ease-in-out infinite' : 'none',
        }}
      >
        翻开日记本
      </button>

      {/* 右上角 — 跳过按钮 */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          handleSkip()
        }}
        tabIndex={0}
        className="welcome-skip"
        style={{
          position: 'absolute',
          top: '24px',
          right: '24px',
          opacity: isOpening ? 0 : 1,
          transition: 'opacity 300ms ease-out',
          fontFamily: "'DM Sans', -apple-system, sans-serif",
          fontSize: '12px',
          color: '#9B8E82',
          letterSpacing: '0.1em',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          padding: '6px 14px',
          borderRadius: '999px',
        }}
      >
        跳过
      </button>

      {/* 内联 CSS：按钮交互样式 + 动画 */}
      <style>{`
        .welcome-btn {
          transition: background 300ms ease-out, color 300ms ease-out, border-color 300ms ease-out, box-shadow 300ms ease-out, transform 300ms ease-out, opacity 300ms ease-out !important;
        }
        .welcome-btn:hover {
          background: #FBF5EF;
          border-color: rgba(212, 133, 106, 0.4);
          box-shadow: 0 4px 12px rgba(44, 36, 32, 0.08);
        }
        .welcome-btn:focus-visible {
          outline: none;
          box-shadow: 0 0 0 3px rgba(212, 133, 106, 0.2), 0 0 0 1px rgba(212, 133, 106, 0.4) !important;
          background: #FBF5EF;
        }
        .welcome-skip {
          transition: background 300ms ease-out, color 300ms ease-out;
        }
        .welcome-skip:hover {
          color: #7A6E64;
          background: rgba(212, 133, 106, 0.08);
        }
        .welcome-skip:focus-visible {
          outline: 1px solid #D4856A;
          outline-offset: 2px;
        }
        @keyframes welcome-btn-pulse {
          0%, 100% {
            transform: translate(-50%, 0) scale(1);
            box-shadow: 0 2px 8px rgba(44, 36, 32, 0.06), 0 1px 2px rgba(44, 36, 32, 0.03);
          }
          50% {
            transform: translate(-50%, -2px) scale(1.02);
            box-shadow: 0 6px 16px rgba(44, 36, 32, 0.1), 0 2px 4px rgba(44, 36, 32, 0.05);
          }
        }
      `}</style>
    </div>
  )
}

export default Welcome
