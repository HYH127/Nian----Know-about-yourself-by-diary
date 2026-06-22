import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { EmotionSeasonDay } from '../../types'

interface Props {
  daily: EmotionSeasonDay[]
  monthlyAvg: Record<string, number>
  year: number
  onPrevYear: () => void
  onNextYear: () => void
  availableYears: number[]
}

const SERIF_FONT = "'Source Serif 4', Georgia, serif"
const MONO_FONT = "'JetBrains Mono', monospace"

const COLOR_PRIMARY = '#2C2420'
const COLOR_SECONDARY = '#7A6E64'
const COLOR_TERTIARY = '#B5A99E'
const COLOR_ACCENT = '#D4856A'
const COLOR_BG_CARD = '#FFFFFF'
const COLOR_BG_SOFT = '#FAF7F4'
const COLOR_BORDER = '#E8E0D8'
const COLOR_EMPTY_CELL = '#F5F0EA'

function sentimentColor(t: number): string {
  const stops: [number, number, number, number][] = [
    [-1,   196, 107, 107],
    [-0.5, 212, 133, 106],
    [-0.2, 196, 149, 106],
    [ 0,   181, 169, 158],
    [ 0.2, 169, 185, 171],
    [ 0.5, 143, 168, 154],
    [ 1,   111, 156, 128],
  ]
  const clamped = Math.max(-1, Math.min(1, t))
  for (let i = 0; i < stops.length - 1; i++) {
    if (clamped <= stops[i + 1][0]) {
      const p = (clamped - stops[i][0]) / (stops[i + 1][0] - stops[i][0])
      const r = Math.round(stops[i][1] + (stops[i + 1][1] - stops[i][1]) * p)
      const g = Math.round(stops[i][2] + (stops[i + 1][2] - stops[i][2]) * p)
      const b = Math.round(stops[i][3] + (stops[i + 1][3] - stops[i][3]) * p)
      return `rgb(${r},${g},${b})`
    }
  }
  return `rgb(143,168,154)`
}

export default function EmotionSeason({ daily, monthlyAvg, year, onPrevYear, onNextYear, availableYears }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const calendarRef = useRef<SVGSVGElement>(null)
  const barRef = useRef<SVGSVGElement>(null)
  const tooltipRef = useRef<d3.Selection<HTMLDivElement, unknown, HTMLElement, any> | null>(null)
  const [containerWidth, setContainerWidth] = useState(800)
  const [renderTick, setRenderTick] = useState(0)

  useEffect(() => {
    if (!containerRef.current) return
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        const w = Math.floor(entry.contentRect.width)
        if (w > 100) {
          setContainerWidth(w)
        }
      }
    })
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const el = d3.select('body').append('div').attr('class', 'insight-tooltip')
    tooltipRef.current = el
    el.style('position', 'absolute')
      .style('visibility', 'hidden')
      .style('background', COLOR_BG_CARD)
      .style('border', `1px solid ${COLOR_BORDER}`)
      .style('border-radius', '10px')
      .style('padding', '8px 12px')
      .style('box-shadow', '0 4px 16px rgba(44,36,32,0.08)')
      .style('font-size', '12px')
      .style('line-height', '1.6')
      .style('color', COLOR_PRIMARY)
      .style('pointer-events', 'none')
      .style('max-width', '280px')
      .style('z-index', '1000')
    return () => {
      el.remove()
      tooltipRef.current = null
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => setRenderTick(v => v + 1), 0)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (!calendarRef.current) return
    const svg = d3.select(calendarRef.current)
    svg.selectAll('*').remove()

    const cellSize = 20
    const gap = 5
    const step = cellSize + gap
    const margin = { top: 28, right: 12, bottom: 8, left: 32 }

    const start = new Date(year, 0, 1)
    const end = new Date(year, 11, 31)
    const days: Date[] = []
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      days.push(new Date(d))
    }

    const weekFormat = d3.timeFormat('%U')
    const dayFormat = d3.timeFormat('%w')
    const isoFormat = d3.timeFormat('%Y-%m-%d')

    const dateMap = new Map(daily.map(d => [d.date, d.avg_sentiment]))
    const countMap = new Map(daily.map(d => [d.date, d.count]))

    const maxWeek = Math.max(...days.map(d => parseInt(weekFormat(d))))

    const innerW = (maxWeek + 1) * step
    const innerH = 7 * step

    const svgW = innerW + margin.left + margin.right
    const svgH = innerH + margin.top + margin.bottom

    svg.attr('width', svgW).attr('height', svgH)
    svg.attr('viewBox', `0 0 ${svgW} ${svgH}`)

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const weekDayLabels = ['日', '一', '二', '三', '四', '五', '六']
    g.selectAll('.weekday-label')
      .data(weekDayLabels)
      .enter()
      .append('text')
      .attr('class', 'weekday-label')
      .attr('x', -8)
      .attr('y', (_d, i) => i * step + cellSize / 2)
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', 11)
      .attr('font-family', SERIF_FONT)
      .attr('fill', COLOR_SECONDARY)
      .text(d => d)

    const months = d3.timeMonths(new Date(year, 0, 1), new Date(year + 1, 0, 1))
    g.selectAll('.month-label')
      .data(months)
      .enter()
      .append('text')
      .attr('class', 'month-label')
      .attr('x', d => parseInt(weekFormat(d)) * step)
      .attr('y', -6)
      .attr('text-anchor', 'start')
      .attr('font-size', 11)
      .attr('font-family', SERIF_FONT)
      .attr('fill', COLOR_SECONDARY)
      .text(d => `${d.getMonth() + 1}月`)

    g.selectAll('.day-cell')
      .data(days)
      .enter()
      .append('rect')
      .attr('class', 'day-cell')
      .attr('width', cellSize)
      .attr('height', cellSize)
      .attr('x', d => parseInt(weekFormat(d)) * step)
      .attr('y', d => parseInt(dayFormat(d)) * step)
      .attr('rx', 4)
      .attr('fill', d => {
        const iso = isoFormat(d)
        const val = dateMap.get(iso)
        return val !== undefined ? sentimentColor(val) : COLOR_EMPTY_CELL
      })
      .attr('opacity', 0)
      .style('cursor', d => (dateMap.get(isoFormat(d)) !== undefined ? 'pointer' : 'default'))
      .transition()
      .duration(150)
      .delay((_d, i) => i * 2)
      .attr('opacity', 1)

    g.selectAll('.day-cell')
      .on('mouseenter', function (event: MouseEvent, d: Date) {
        const iso = isoFormat(d)
        const val = dateMap.get(iso)
        const cnt = countMap.get(iso)
        if (val !== undefined) {
          d3.select(this).attr('stroke', COLOR_PRIMARY).attr('stroke-width', 1.5)
        }
        if (tooltipRef.current) {
          let html = `<div style="font-size:13px;font-weight:600;font-family:${SERIF_FONT};color:${COLOR_ACCENT};margin-bottom:4px">${iso}</div>`
          if (val !== undefined) {
            html += `<div style="font-size:11px;font-family:${MONO_FONT};font-weight:600;color:${COLOR_SECONDARY}">情绪值: ${val.toFixed(2)}</div>`
            html += `<div style="font-size:11px;font-family:${MONO_FONT};font-weight:600;color:${COLOR_SECONDARY}">记录数: ${cnt}</div>`
          } else {
            html += `<div style="font-size:11px;color:${COLOR_SECONDARY};font-family:${MONO_FONT}">无数据</div>`
          }
          tooltipRef.current
            .style('visibility', 'visible')
            .html(html)
            .style('left', `${event.pageX + 12}px`)
            .style('top', `${event.pageY - 12}px`)
        }
      })
      .on('mousemove', (event: MouseEvent) => {
        if (tooltipRef.current) {
          tooltipRef.current
            .style('left', `${event.pageX + 12}px`)
            .style('top', `${event.pageY - 12}px`)
        }
      })
      .on('mouseleave', function () {
        d3.select(this).attr('stroke', null).attr('stroke-width', null)
        if (tooltipRef.current) {
          tooltipRef.current.style('visibility', 'hidden')
        }
      })

  }, [daily, year, containerWidth, renderTick])

  useEffect(() => {
    if (!barRef.current || !monthlyAvg || Object.keys(monthlyAvg).length === 0) return
    const svg = d3.select(barRef.current)
    svg.selectAll('*').remove()

    const entries = Object.entries(monthlyAvg).sort((a, b) => a[0].localeCompare(b[0]))
    if (entries.length === 0) return

    const margin = { top: 16, right: 12, bottom: 28, left: 32 }
    const barGap = 8
    const barContainerW = Math.max(160, containerWidth - 88)
    const innerW = barContainerW - margin.left - margin.right
    const barWidth = Math.max(20, (innerW - (entries.length - 1) * barGap) / entries.length)
    const innerH = 150
    const svgW = innerW + margin.left + margin.right
    const svgH = innerH + margin.top + margin.bottom

    svg.attr('width', svgW).attr('height', svgH)
    svg.attr('viewBox', `0 0 ${svgW} ${svgH}`)

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const yScale = d3.scaleLinear().domain([-1, 1]).range([innerH, 0])
    const zeroY = yScale(0)

    const yTicks = [-1, -0.5, 0, 0.5, 1]
    yTicks.forEach(tick => {
      const y = yScale(tick)
      g.append('line')
        .attr('x1', 0)
        .attr('x2', innerW)
        .attr('y1', y)
        .attr('y2', y)
        .attr('stroke', COLOR_BORDER)
        .attr('stroke-width', 1)
    })

    g.selectAll('.y-label')
      .data(yTicks)
      .enter()
      .append('text')
      .attr('class', 'y-label')
      .attr('x', -8)
      .attr('y', d => yScale(d))
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', 11)
      .attr('font-family', MONO_FONT)
      .attr('fill', COLOR_TERTIARY)
      .text(d => d.toFixed(1))

    g.append('line')
      .attr('x1', 0)
      .attr('x2', innerW)
      .attr('y1', zeroY)
      .attr('y2', zeroY)
      .attr('stroke', COLOR_TERTIARY)
      .attr('stroke-width', 1)

    entries.forEach(([month, val], i) => {
      const x = i * (barWidth + barGap)
      const targetBarY = val >= 0 ? yScale(val) : zeroY
      const targetBarH = Math.abs(yScale(val) - zeroY)
      const color = sentimentColor(val)

      const bar = g.append('rect')
        .attr('x', x)
        .attr('y', zeroY)
        .attr('width', barWidth)
        .attr('height', 0)
        .attr('rx', 4)
        .attr('fill', color)

      bar.transition()
        .duration(600)
        .delay(i * 40)
        .ease(d3.easeCubicOut)
        .attr('y', targetBarY)
        .attr('height', Math.max(targetBarH, 1))

      const label = g.append('text')
        .attr('x', x + barWidth / 2)
        .attr('y', innerH + 18)
        .attr('text-anchor', 'middle')
        .attr('font-size', 12)
        .attr('font-family', SERIF_FONT)
        .attr('fill', COLOR_SECONDARY)
        .attr('opacity', 0)
        .text(month.slice(5) + '月')

      label.transition()
        .duration(400)
        .delay(400 + i * 40)
        .attr('opacity', 1)

      const valLabel = g.append('text')
        .attr('x', x + barWidth / 2)
        .attr('y', val >= 0 ? targetBarY - 6 : targetBarY + targetBarH + 14)
        .attr('text-anchor', 'middle')
        .attr('font-size', 11)
        .attr('font-family', MONO_FONT)
        .attr('fill', COLOR_SECONDARY)
        .attr('opacity', 0)
        .text(val.toFixed(2))

      valLabel.transition()
        .duration(400)
        .delay(500 + i * 40)
        .attr('opacity', 1)
    })

  }, [monthlyAvg, renderTick, containerWidth])

  if (daily.length === 0 && Object.keys(monthlyAvg).length === 0) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', minHeight: 320, color: COLOR_SECONDARY,
        fontSize: 13, fontFamily: SERIF_FONT, background: COLOR_BG_CARD, borderRadius: 14,
        border: `1px solid ${COLOR_BORDER}`,
      }}>
        暂无情绪数据
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        background: COLOR_BG_CARD,
        borderRadius: 14,
        border: `1px solid ${COLOR_BORDER}`,
        padding: 16,
      }}
    >
      <div style={{ marginBottom: 20, padding: '0 8px 8px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}>
          <div style={{
            fontSize: 14,
            fontFamily: SERIF_FONT,
            fontWeight: 500,
            color: COLOR_PRIMARY,
          }}>
            情绪日历
          </div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <button
              onClick={onPrevYear}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                borderRadius: 8,
                border: `1px solid ${COLOR_BORDER}`,
                background: COLOR_BG_SOFT,
                cursor: 'pointer',
                color: COLOR_SECONDARY,
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = COLOR_BORDER }}
              onMouseLeave={(e) => { e.currentTarget.style.background = COLOR_BG_SOFT }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6" /></svg>
            </button>
            <span style={{
              fontSize: 14,
              fontFamily: MONO_FONT,
              fontWeight: 600,
              color: COLOR_PRIMARY,
              minWidth: 48,
              textAlign: 'center',
            }}>
              {year}
            </span>
            <button
              onClick={onNextYear}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 28,
                height: 28,
                borderRadius: 8,
                border: `1px solid ${COLOR_BORDER}`,
                background: COLOR_BG_SOFT,
                cursor: 'pointer',
                color: COLOR_SECONDARY,
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = COLOR_BORDER }}
              onMouseLeave={(e) => { e.currentTarget.style.background = COLOR_BG_SOFT }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
            </button>
          </div>
        </div>
        <div style={{ overflowX: 'auto', background: COLOR_BG_SOFT, borderRadius: 10, padding: '8px 8px 4px' }}>
          <svg ref={calendarRef} />
        </div>
        <div style={{
          marginTop: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          background: COLOR_BG_SOFT,
          borderRadius: 8,
          padding: '8px 16px',
        }}>
          <span style={{ fontSize: 11, color: '#C46B6B', fontFamily: SERIF_FONT }}>消极</span>
          <div style={{
            width: 120,
            height: 8,
            borderRadius: 4,
            background: 'linear-gradient(90deg, #C46B6B, #C4956A, #8FA89A)',
          }} />
          <span style={{ fontSize: 11, color: '#8FA89A', fontFamily: SERIF_FONT }}>积极</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'stretch' }}>
        {Object.keys(monthlyAvg).length > 0 && (
          <div style={{
            flex: '1 1 300px',
            minWidth: 300,
            background: COLOR_BG_SOFT,
            borderRadius: 10,
            padding: 16,
          }}>
            <div style={{
              fontSize: 13,
              fontFamily: SERIF_FONT,
              fontWeight: 500,
              color: COLOR_PRIMARY,
              marginBottom: 10,
              textAlign: 'center',
            }}>
              月度情绪
            </div>
            <svg ref={barRef} />
          </div>
        )}
      </div>
    </div>
  )
}
