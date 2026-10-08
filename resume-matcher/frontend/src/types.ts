export interface User {
  id: number
  username: string
  display_name: string
}

export interface Revision {
  id: number
  version: number
  note: string
  content_md: string
  created_at: string
  analysis_id: number | null
}

export interface AnalysisSummary {
  id: number
  resume_id: number
  // 岗位被删除后，分析记录保留，这个引用会变成 null（岗位名走 job_title 快照）
  job_id: number | null
  job_title: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  error_message: string | null
  model_name: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  item_count: number
  suggestion_count: number
  /** 三态计数，只读统计，用于工作台卡片顶部的匹配概览 */
  status_counts: Record<string, number>
  /** 本次分析里已被采纳的建议条数 */
  adopted_suggestion_count: number
}

export interface AnalysisItem {
  id: number
  position: number
  requirement_quote: string
  evidence_quote: string | null
  match_status: '已体现' | '未体现' | '需要补充确认'
  reason: string
  confirmation_question: string | null
  supplement: Supplement | null
  supplement_state: '未补充' | '待处理' | '已补充'
}

export interface Supplement {
  id: number
  analysis_id: number
  item_id: number
  user_input: string
  polished_text: string
  polish_reason: string
  section: string
  decision: '未处理' | '采纳' | '忽略'
  created_at: string
  applied_at: string | null
}

export interface Suggestion {
  id: number
  position: number
  section: string
  original_passage: string | null
  suggested_passage: string | null
  rewrite_reason: string
  is_question: boolean
  decision: '未处理' | '采纳' | '忽略'
  applied_at: string | null
}

export interface AnalysisDetail extends AnalysisSummary {
  resume_snapshot: string
  job_snapshot: string
  items: AnalysisItem[]
  suggestions: Suggestion[]
}

export interface ResumeSummary {
  id: number
  title: string
  created_at: string
  original_text: string
  draft_content: string
  revision_count: number
  latest_revision: Revision | null
  analyses?: AnalysisSummary[]
  revisions?: Revision[]
}

export interface Job {
  id: number
  title: string
  description: string
  created_at: string
}

export interface ExportPayload {
  filename: string
  content: string
  revision_version: number
  saved_at: string
  draft_dirty: boolean
}

/** 删除简历的二次确认弹窗要展示的计数。 */
export interface ResumeDeletionPreview {
  title: string
  adopted_suggestions: number
  adopted_supplements: number
  analysis_count: number
  revision_count: number
  running_analysis_count: number
}

/** 删除岗位的二次确认弹窗要展示的计数。 */
export interface JobDeletionPreview {
  title: string
  analysis_count: number
  resume_count: number
}
