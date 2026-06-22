const POSITIVE_WORDS: Record<string, number> = {
  '开心': 0.8, '高兴': 0.8, '喜欢': 0.7, '爱': 0.9, '棒': 0.7,
  '好': 0.5, '赞': 0.7, '哈哈': 0.6, '嘻嘻': 0.6, '嘿嘿': 0.5,
  '快乐': 0.8, '幸福': 0.9, '满足': 0.6, '感谢': 0.6, '谢谢': 0.5,
  '期待': 0.6, '希望': 0.5, '美好': 0.7, '不错': 0.5, '厉害': 0.7,
  '优秀': 0.7, '完美': 0.9, '精彩': 0.7, '温暖': 0.6, '感动': 0.7,
  '惊喜': 0.7, '欣赏': 0.6, '享受': 0.6, '舒服': 0.5, '安心': 0.6,
  '甜蜜': 0.8, '可爱': 0.6, '漂亮': 0.6, '帅': 0.6, '酷': 0.5,
  '加油': 0.6, '支持': 0.5, '鼓励': 0.6, '勇敢': 0.6, '坚强': 0.5,
  '想念': 0.4, '思念': 0.4, '珍惜': 0.6, '感恩': 0.7, '祝福': 0.6,
}

const NEGATIVE_WORDS: Record<string, number> = {
  '难过': -0.8, '伤心': -0.8, '讨厌': -0.7, '恨': -0.9, '烦': -0.6,
  '累': -0.5, '哭': -0.7, '痛苦': -0.9, '失望': -0.7, '生气': -0.7,
  '愤怒': -0.9, '焦虑': -0.6, '担心': -0.5, '害怕': -0.6, '恐惧': -0.8,
  '孤独': -0.7, '寂寞': -0.6, '无聊': -0.4, '郁闷': -0.6, '沮丧': -0.7,
  '绝望': -0.9, '崩溃': -0.8, '烦躁': -0.6, '无奈': -0.5, '委屈': -0.6,
  '后悔': -0.7, '遗憾': -0.5, '抱歉': -0.4, '对不起': -0.4, '尴尬': -0.4,
  '压力': -0.5, '疲惫': -0.6, '厌烦': -0.6, '厌恶': -0.7, '恶心': -0.7,
}

const POSITIVE_EMOJIS: Record<string, number> = {
  '😊': 0.6, '😄': 0.7, '😁': 0.7, '😆': 0.7, '😂': 0.6,
  '🤣': 0.6, '😍': 0.8, '🥰': 0.8, '😘': 0.7, '😗': 0.5,
  '😋': 0.5, '🤗': 0.6, '🤩': 0.7, '🥳': 0.7, '😎': 0.5,
  '👍': 0.6, '👏': 0.6, '💪': 0.5, '❤️': 0.8, '💕': 0.7,
  '💖': 0.8, '💗': 0.7, '✨': 0.5, '🎉': 0.7, '🎊': 0.6,
  '🙏': 0.5, '🌹': 0.5, '🌸': 0.4, '☀️': 0.4, '⭐': 0.4,
}

const NEGATIVE_EMOJIS: Record<string, number> = {
  '😢': -0.7, '😭': -0.8, '😡': -0.8, '😠': -0.7, '😤': -0.6,
  '😞': -0.6, '😔': -0.5, '😟': -0.5, '🙁': -0.4, '😣': -0.5,
  '😖': -0.6, '😫': -0.6, '😩': -0.6, '🥺': -0.4, '😓': -0.4,
  '💔': -0.8, '👎': -0.6, '😱': -0.7, '😨': -0.6,
}

const NEGATION_WORDS = new Set(['不', '没', '没有', '别', '非', '未', '无', '莫'])

export function analyzeSentiment(text: string): number {
  let score = 0
  let count = 0

  const chars = [...text]
  for (let i = 0; i < chars.length; i++) {
    for (const [emoji, weight] of Object.entries(NEGATIVE_EMOJIS)) {
      if (text.substring(i).startsWith(emoji)) {
        score += weight
        count++
      }
    }
    for (const [emoji, weight] of Object.entries(POSITIVE_EMOJIS)) {
      if (text.substring(i).startsWith(emoji)) {
        score += weight
        count++
      }
    }
  }

  for (const [word, weight] of Object.entries(NEGATIVE_WORDS)) {
    let idx = text.indexOf(word)
    while (idx !== -1) {
      let effective = weight
      if (idx > 0) {
        const before = text.substring(Math.max(0, idx - 2), idx)
        for (const neg of NEGATION_WORDS) {
          if (before.includes(neg)) {
            effective = -weight * 0.5
            break
          }
        }
      }
      score += effective
      count++
      idx = text.indexOf(word, idx + word.length)
    }
  }

  for (const [word, weight] of Object.entries(POSITIVE_WORDS)) {
    let idx = text.indexOf(word)
    while (idx !== -1) {
      let effective = weight
      if (idx > 0) {
        const before = text.substring(Math.max(0, idx - 2), idx)
        for (const neg of NEGATION_WORDS) {
          if (before.includes(neg)) {
            effective = -weight * 0.5
            break
          }
        }
      }
      score += effective
      count++
      idx = text.indexOf(word, idx + word.length)
    }
  }

  if (count === 0) return 0

  const normalized = score / count
  return Math.max(-1, Math.min(1, normalized))
}
