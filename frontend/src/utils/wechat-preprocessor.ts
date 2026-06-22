import { analyzeSentiment } from './sentiment'
import { desensitize } from './desensitizer'

export interface WechatMessage {
  timestamp: string
  sender: string
  content: string
  wordCount: number
  hasEmoji: boolean
  hasImage: boolean
  hasVoice: boolean
  sentimentScore: number
  topicCategory: string
  messageHash: string
  responseDelaySeconds: number | null
}

export interface WechatParseResult {
  contactName: string
  messages: WechatMessage[]
  stats: {
    totalMessages: number
    dateRange: { start: string; end: string }
    uniqueSenders: string[]
  }
}

const DATETIME_RE = /^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+(.+)$/
const SYSTEM_MSG_RE = /(撤回了一条消息|已过期|开启了朋友验证|添加了.*为好友|加入了群聊|修改群名为|邀请.*加入了群聊)/

const TOPIC_KEYWORDS: Record<string, string[]> = {
  '工作': ['工作', '上班', '加班', '开会', '项目', '领导', '同事', '公司', '客户', '方案', '汇报', '邮件'],
  '生活': ['吃饭', '睡觉', '做饭', '买菜', '打扫', '家务', '快递', '外卖', '超市'],
  '情感': ['想你', '喜欢', '爱', '在一起', '分手', '难过', '开心', '感动', '想念', '思念', '亲爱的'],
  '社交': ['聚会', '约', '一起', '出来', '见面', '朋友', '生日', '聚餐', '唱歌', 'KTV'],
  '健康': ['医院', '医生', '吃药', '身体', '不舒服', '感冒', '发烧', '体检', '锻炼', '运动'],
  '学习': ['学习', '考试', '读书', '课程', '培训', '笔记', '论文', '老师', '学校'],
  '娱乐': ['电影', '游戏', '音乐', '综艺', '追剧', '小说', '旅游', '出去玩', '看剧'],
  '财务': ['工资', '钱', '花', '买', '价格', '便宜', '贵', '转账', '红包', '付款'],
}

const EMOJI_RE = /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{FE00}-\u{FE0F}\u{1F900}-\u{1F9FF}\u{200D}]/u
const IMAGE_RE = /\[图片\]|\[表情\]|<img\s|\.jpg|\.png|\.gif|\.jpeg/i
const VOICE_RE = /\[语音\]|\[语音消息\]/i

async function computeHash(input: string): Promise<string> {
  const encoder = new TextEncoder()
  const data = encoder.encode(input)
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
}

function classifyTopic(content: string): string {
  let bestTopic = '其他'
  let bestScore = 0

  for (const [topic, keywords] of Object.entries(TOPIC_KEYWORDS)) {
    let score = 0
    for (const kw of keywords) {
      if (content.includes(kw)) score++
    }
    if (score > bestScore) {
      bestScore = score
      bestTopic = topic
    }
  }

  return bestTopic
}

function parseTxtFormat(text: string): Array<{ timestamp: string; sender: string; content: string }> {
  const results: Array<{ timestamp: string; sender: string; content: string }> = []
  const lines = text.split(/\r?\n/)
  let currentMsg: { timestamp: string; sender: string; content: string } | null = null

  for (const line of lines) {
    const match = line.match(DATETIME_RE)
    if (match) {
      if (currentMsg && currentMsg.content.trim()) {
        results.push(currentMsg)
      }
      currentMsg = {
        timestamp: match[1],
        sender: match[2].trim(),
        content: '',
      }
    } else if (currentMsg) {
      if (line.trim() === '') {
        if (currentMsg.content.trim()) {
          results.push(currentMsg)
          currentMsg = null
        }
      } else {
        currentMsg.content += (currentMsg.content ? '\n' : '') + line
      }
    }
  }

  if (currentMsg && currentMsg.content.trim()) {
    results.push(currentMsg)
  }

  return results
}

function parseCsvFormat(text: string): Array<{ timestamp: string; sender: string; content: string }> {
  const results: Array<{ timestamp: string; sender: string; content: string }> = []
  const lines = text.split(/\r?\n/)

  if (lines.length < 2) return results

  const header = lines[0].split(',').map(h => h.trim())
  const timeIdx = header.findIndex(h => /聊天时间|时间|timestamp|date/i.test(h))
  const senderIdx = header.findIndex(h => /发送者|发送人|昵称|sender|name/i.test(h))
  const contentIdx = header.findIndex(h => /消息内容|内容|消息|content|message/i.test(h))

  if (timeIdx === -1 || senderIdx === -1 || contentIdx === -1) return results

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim()
    if (!line) continue

    const parts: string[] = []
    let current = ''
    let inQuotes = false
    for (const ch of line) {
      if (ch === '"') {
        inQuotes = !inQuotes
      } else if (ch === ',' && !inQuotes) {
        parts.push(current.trim())
        current = ''
      } else {
        current += ch
      }
    }
    parts.push(current.trim())

    const timestamp = parts[timeIdx] || ''
    const sender = parts[senderIdx] || ''
    const content = parts[contentIdx] || ''

    if (timestamp && sender && content) {
      results.push({ timestamp, sender, content })
    }
  }

  return results
}

function parseHtmlFormat(text: string): Array<{ timestamp: string; sender: string; content: string }> {
  const results: Array<{ timestamp: string; sender: string; content: string }> = []
  const parser = new DOMParser()
  const doc = parser.parseFromString(text, 'text/html')

  const rows = doc.querySelectorAll('table tr, div.msg, div.message, div.chat-msg, div[class*="message"], div[class*="msg"]')

  for (const row of rows) {
    const cells = row.querySelectorAll('td, span, div, p')
    let timestamp = ''
    let sender = ''
    let content = ''

    for (const cell of cells) {
      const text = cell.textContent?.trim() || ''
      if (/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$/.test(text)) {
        timestamp = text
      } else if (!timestamp && /^\d{4}/.test(text)) {
        const m = text.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/)
        if (m) timestamp = m[1]
      }
    }

    const allText = row.textContent?.trim() || ''
    const dtMatch = allText.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/)
    if (dtMatch && !timestamp) {
      timestamp = dtMatch[1]
    }

    if (!timestamp) continue

    const remaining = allText.replace(timestamp, '').trim()
    const lines = remaining.split(/\n/).map(l => l.trim()).filter(Boolean)
    if (lines.length >= 2) {
      sender = lines[0]
      content = lines.slice(1).join('\n')
    } else if (lines.length === 1) {
      content = lines[0]
    }

    if (content) {
      results.push({ timestamp, sender, content })
    }
  }

  return results
}

export async function parseWechatFile(file: File, contactName: string): Promise<WechatParseResult> {
  const text = await file.text()
  const ext = file.name.split('.').pop()?.toLowerCase() || ''

  let rawMessages: Array<{ timestamp: string; sender: string; content: string }>

  switch (ext) {
    case 'csv':
      rawMessages = parseCsvFormat(text)
      break
    case 'html':
    case 'htm':
      rawMessages = parseHtmlFormat(text)
      break
    case 'txt':
    default:
      rawMessages = parseTxtFormat(text)
      break
  }

  const filtered = rawMessages.filter(msg => !SYSTEM_MSG_RE.test(msg.content))

  const messages: WechatMessage[] = []
  let prevTimestamp: Date | null = null

  for (const msg of filtered) {
    const currentTimestamp = new Date(msg.timestamp)
    let responseDelaySeconds: number | null = null

    if (prevTimestamp && !isNaN(currentTimestamp.getTime()) && !isNaN(prevTimestamp.getTime())) {
      const diff = (currentTimestamp.getTime() - prevTimestamp.getTime()) / 1000
      if (diff >= 0 && diff < 86400) {
        responseDelaySeconds = Math.round(diff)
      }
    }

    const sentimentScore = analyzeSentiment(msg.content)
    const topicCategory = classifyTopic(msg.content)
    const wordCount = [...msg.content].length
    const hasEmoji = EMOJI_RE.test(msg.content)
    const hasImage = IMAGE_RE.test(msg.content)
    const hasVoice = VOICE_RE.test(msg.content)
    const messageHash = await computeHash(`${msg.timestamp}:${msg.sender}:${msg.content}`)

    messages.push({
      timestamp: msg.timestamp,
      sender: msg.sender,
      content: msg.content,
      wordCount,
      hasEmoji,
      hasImage,
      hasVoice,
      sentimentScore,
      topicCategory,
      messageHash,
      responseDelaySeconds,
    })

    prevTimestamp = currentTimestamp
  }

  const uniqueSenders = [...new Set(messages.map(m => m.sender))]
  const timestamps = messages.map(m => m.timestamp).filter(Boolean).sort()

  return {
    contactName,
    messages,
    stats: {
      totalMessages: messages.length,
      dateRange: {
        start: timestamps[0] || '',
        end: timestamps[timestamps.length - 1] || '',
      },
      uniqueSenders,
    },
  }
}

export function toTier1Payload(messages: WechatMessage[]): Array<Record<string, unknown>> {
  return messages.map(({ timestamp, sender, wordCount, hasEmoji, hasImage, hasVoice, sentimentScore, topicCategory, messageHash, responseDelaySeconds }) => ({
    timestamp,
    sender,
    word_count: wordCount,
    has_emoji: hasEmoji,
    has_image: hasImage,
    has_voice: hasVoice,
    sentiment_score: Math.round(sentimentScore * 100) / 100,
    topic_category: topicCategory,
    message_hash: messageHash,
    response_delay_seconds: responseDelaySeconds,
  }))
}

export function toTier2Payload(messages: WechatMessage[]): Array<Record<string, unknown>> {
  return messages.map(({ timestamp, sender, content, wordCount, hasEmoji, hasImage, hasVoice, sentimentScore, topicCategory, messageHash, responseDelaySeconds }) => ({
    timestamp,
    sender,
    content: desensitize(content),
    word_count: wordCount,
    has_emoji: hasEmoji,
    has_image: hasImage,
    has_voice: hasVoice,
    sentiment_score: Math.round(sentimentScore * 100) / 100,
    topic_category: topicCategory,
    message_hash: messageHash,
    response_delay_seconds: responseDelaySeconds,
  }))
}

export function toTier3Payload(messages: WechatMessage[]): Array<Record<string, unknown>> {
  return messages.map(({ timestamp, sender, content, wordCount, hasEmoji, hasImage, hasVoice, sentimentScore, topicCategory, messageHash, responseDelaySeconds }) => ({
    timestamp,
    sender,
    content,
    word_count: wordCount,
    has_emoji: hasEmoji,
    has_image: hasImage,
    has_voice: hasVoice,
    sentiment_score: Math.round(sentimentScore * 100) / 100,
    topic_category: topicCategory,
    message_hash: messageHash,
    response_delay_seconds: responseDelaySeconds,
  }))
}
