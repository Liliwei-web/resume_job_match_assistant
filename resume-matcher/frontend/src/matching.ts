/**
 * 原稿 / 修改稿与「分析条目、改写建议」之间的文本匹配与整行删除定位。
 *
 * 单独放一个模块的原因：这里的规则是纯文本逻辑，而且是「删除哪一行」的唯一依据，
 * 需要能脱离 React 直接验证（见项目文档中的验证步骤）。
 */
import type { AnalysisItem, Suggestion } from './types'

// 一行文字短于这个长度就不参与匹配：标题行、空白行、"## 技能" 这类不会被误当成证据句。
export const MIN_MATCH_LEN = 6

export const squeezed = (text: string) => text.replace(/\s+/g, '')

/** 两段文本的重叠长度：谁包含谁都算，取较短的那个。 */
export function overlapLength(a: string, b: string): number {
  if (a.includes(b)) return b.length
  if (b.includes(a)) return a.length
  return 0
}

/**
 * 这一行是不是某条要求的证据句？多条命中时取重叠最长的那条。
 * 双向包含：模型引用的可能是整行，也可能只是行里的一小段（早期只判单向，半句引用会漏配）。
 */
export function itemForLine(line: string, items: AnalysisItem[]): AnalysisItem | null {
  const text = squeezed(line)
  if (text.length < MIN_MATCH_LEN) return null
  let best: AnalysisItem | null = null
  let bestScore = 0
  items.forEach((item) => {
    const score = overlapLength(text, squeezed(item.evidence_quote ?? ''))
    if (score >= MIN_MATCH_LEN && score > bestScore) {
      bestScore = score
      best = item
    }
  })
  return best
}

/** 这一行是不是某条改写建议的原文？规则同上。 */
export function suggestionForLine(line: string, suggestions: Suggestion[]): Suggestion | null {
  const text = squeezed(line)
  if (text.length < MIN_MATCH_LEN) return null
  let best: Suggestion | null = null
  let bestScore = 0
  suggestions.forEach((suggestion) => {
    const score = overlapLength(text, squeezed(suggestion.original_passage ?? ''))
    if (score >= MIN_MATCH_LEN && score > bestScore) {
      bestScore = score
      best = suggestion
    }
  })
  return best
}

/** 这一行看起来是能被整行操作的正文吗（排除标题行与过短行）。 */
export function isDeletableLine(line: string): boolean {
  return squeezed(line).length >= MIN_MATCH_LEN && !line.trim().startsWith('#')
}

/** 在文本里找与 line 逐字相同（忽略空白）的那一行；0 次或多次都返回 -1，不做模糊匹配。 */
export function uniqueLineIndex(content: string, line: string): number {
  const needle = squeezed(line)
  if (!isDeletableLine(line)) return -1
  const hits: number[] = []
  content.split(/\r?\n/).forEach((current, index) => {
    if (squeezed(current) === needle) hits.push(index)
  })
  return hits.length === 1 ? hits[0] : -1
}

export function removeLineAt(content: string, index: number): string {
  const lines = content.split(/\r?\n/)
  lines.splice(index, 1)
  return lines.join('\n')
}

/**
 * 决定「删除这一行」该怎么做。
 * 悬停在**原稿**上、要删的是**修改稿**里的对应行，两者并非一一对应：
 * 逐字还在 → 直接删；已被采纳的改写替换掉 → 先退回该建议让原句回来，再删；其余不猜。
 */
export type DeletePlan =
  | { kind: 'remove'; index: number }
  | { kind: 'undo-then-remove'; suggestionId: number }
  | { kind: 'blocked'; reason: string }

export function planDelete(
  line: string,
  draftContent: string,
  suggestions: Suggestion[],
): DeletePlan {
  const index = uniqueLineIndex(draftContent, line)
  if (index >= 0) return { kind: 'remove', index }
  const adopted = suggestionForLine(line, suggestions)
  if (adopted && adopted.decision === '采纳' && adopted.original_passage) {
    return { kind: 'undo-then-remove', suggestionId: adopted.id }
  }
  if (line.trim().startsWith('#')) return { kind: 'blocked', reason: '章节标题不能整行删除' }
  if (squeezed(line).length < MIN_MATCH_LEN) {
    return { kind: 'blocked', reason: '这一行太短，无法唯一定位' }
  }
  return {
    kind: 'blocked',
    reason: '这一行在修改稿里找不到唯一对应（可能已被改写或删过），请到修改稿中手动处理',
  }
}
