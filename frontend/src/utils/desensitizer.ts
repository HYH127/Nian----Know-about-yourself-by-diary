const PATTERNS: [RegExp, string][] = [
  [/1[3-9]\d{9}/g, '[PHONE]'],
  [/\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]/g, '[ID_CARD]'],
  [/\d{16,19}/g, '[BANK_CARD]'],
  [/\S+@\S+\.\S+/g, '[EMAIL]'],
]

const ADDRESS_PATTERN = /[\u4e00-\u9fa5]{2,5}(?:省|市|自治区|特别行政区)[\u4e00-\u9fa5]{2,6}(?:市|区|县|镇)[\u4e00-\u9fa5]{2,8}(?:路|街|道|巷|弄)[\u4e00-\u9fa5\d]{0,10}(?:号|栋|幢|座|楼)?[\d\-]{0,6}(?:号|室|层)?/g

const PASSWORD_PATTERN = /(?:密码|pwd|pass|password|口令)\s*[：:=]\s*\S+/gi

export function desensitize(text: string): string {
  let result = text

  result = result.replace(ADDRESS_PATTERN, '[ADDRESS]')

  result = result.replace(PASSWORD_PATTERN, (match) => {
    const sepIndex = match.search(/[：:=]/)
    if (sepIndex === -1) return match
    return match.substring(0, sepIndex + 1) + ' [PASSWORD]'
  })

  for (const [pattern, replacement] of PATTERNS) {
    result = result.replace(pattern, replacement)
  }

  return result
}
