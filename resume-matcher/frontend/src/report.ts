import { statusLabel } from './labels'
import type { AnalysisDetail } from './types'

/** 三态在报告里的固定顺序：不管模型返回的顺序如何，报告读起来都是同一套。 */
const STATUS_ORDER = ['已体现', '需要补充确认', '未体现']

/**
 * 把一条分析记录拼成可下载的 Markdown 报告。
 *
 * 只搬运这条记录自己的快照与结论：不重新调模型、不补写任何原文里没有的内容。
 * 输出刻意只用标题、加粗、列表这些本项目 Markdown 渲染器支持的语法，
 * 这样报告粘回系统里也能正常显示。
 */
export function buildAnalysisReport(analysis: AnalysisDetail, resumeTitle: string): string {
  const lines: string[] = []
  const finishedAt = analysis.finished_at || analysis.created_at

  lines.push('# 简历 × 岗位匹配分析报告', '')
  lines.push(`- 分析记录：#${analysis.id}`)
  lines.push(`- 岗位：${analysis.job_title}`)
  lines.push(`- 简历：${resumeTitle || `#${analysis.resume_id}`}`)
  lines.push(`- 模型：${analysis.model_name || '未知'}`)
  lines.push(`- 时间：${new Date(finishedAt).toLocaleString()}`)
  lines.push(`- 状态：${statusLabel(analysis.status)}`, '')

  lines.push('## 结果概览', '')
  const counts = analysis.status_counts || {}
  const ordered = STATUS_ORDER.filter((status) => counts[status] !== undefined).concat(
    Object.keys(counts).filter((status) => !STATUS_ORDER.includes(status)),
  )
  if (ordered.length === 0) {
    lines.push('这次分析没有返回条目。', '')
  } else {
    ordered.forEach((status) => lines.push(`- ${status}：${counts[status]}`))
    lines.push('')
  }

  lines.push('## 岗位描述（发起分析时的快照）', '')
  lines.push(analysis.job_snapshot || '（空）', '')

  lines.push('## 要求—证据—判断', '')
  if (analysis.items.length === 0) {
    lines.push('（无条目）', '')
  } else {
    analysis.items.forEach((item, index) => {
      lines.push(`### ${index + 1}. ${item.match_status}`, '')
      lines.push(`**岗位要求**：${item.requirement_quote}`, '')
      lines.push(`**简历原文**：${item.evidence_quote || '（原文中无对应内容）'}`, '')
      lines.push(`**判断理由**：${item.reason}`, '')
      if (item.confirmation_question) {
        lines.push(`**需要确认**：${item.confirmation_question}`, '')
      }
    })
  }

  lines.push('## 逐条修改建议', '')
  if (analysis.suggestions.length === 0) {
    lines.push('（无建议）', '')
  } else {
    analysis.suggestions.forEach((suggestion, index) => {
      const kind = suggestion.is_question
        ? '需要补充的信息'
        : `改写建议 · ${suggestion.section || '其他'}`
      lines.push(`### ${index + 1}. ${kind}（当前：${suggestion.decision}）`, '')
      if (suggestion.original_passage) {
        lines.push('**原文**', '', suggestion.original_passage, '')
      }
      if (suggestion.suggested_passage) {
        lines.push('**建议文本**', '', suggestion.suggested_passage, '')
      }
      lines.push(`**改写理由**：${suggestion.rewrite_reason}`, '')
    })
  }

  lines.push('---', '')
  lines.push('本报告由「简历与岗位匹配助手」导出，内容全部来自该次分析记录的快照与结论。')
  return lines.join('\n')
}

/** 导出文件名：带上岗位与记录号，多次导出不会互相覆盖。 */
export function analysisReportFilename(analysis: AnalysisDetail): string {
  const safeJob = (analysis.job_title || '岗位').replace(/[\\/:*?"<>|]/g, '_')
  return `匹配分析报告-${safeJob}-${analysis.id}.md`
}
