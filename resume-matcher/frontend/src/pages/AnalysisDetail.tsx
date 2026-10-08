import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api'
import AnalysisResult from '../components/AnalysisResult'
import { statusLabel } from '../labels'
import { downloadMarkdown } from '../markdown'
import { analysisReportFilename, buildAnalysisReport } from '../report'
import type { AnalysisDetail as AnalysisDetailData, ResumeSummary } from '../types'

/**
 * 一条历史分析记录的只读回放页。
 *
 * 显示的是当初那次分析的输入快照（岗位描述 + 简历快照）与当时的结论。
 * 刻意只读：采纳建议、补充经历都会写到「当前修改稿」上，
 * 从历史记录里操作会让人误以为改的是当时那一份，所以这里只提供查看与导出。
 */
export default function AnalysisDetail() {
  const { analysisId } = useParams()
  const id = Number(analysisId)

  const [analysis, setAnalysis] = useState<AnalysisDetailData | null>(null)
  const [resume, setResume] = useState<ResumeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await api.get<AnalysisDetailData>(`/api/analyses/${id}`)
        if (cancelled) return
        setAnalysis(data)
        // 简历标题只用于标题栏与导出文件里的「简历：xxx」，取不到就退回 #id。
        try {
          const resumeData = await api.get<ResumeSummary>(`/api/resumes/${data.resume_id}`)
          if (!cancelled) setResume(resumeData)
        } catch {
          /* 简历被删掉了也不影响查看这条分析记录 */
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) {
    return (
      <div className="page-loading">
        <span className="spinner" />
        正在加载分析记录…
      </div>
    )
  }

  if (!analysis) {
    return (
      <>
        <div className="error-box">{error || '分析记录不存在或无权访问'}</div>
        <Link to="/history">返回历史记录</Link>
      </>
    )
  }

  function exportReport() {
    if (!analysis) return
    setError('')
    try {
      downloadMarkdown(
        analysisReportFilename(analysis),
        buildAnalysisReport(analysis, resume?.title || ''),
      )
      setMessage('已导出这次分析的 Markdown 报告')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>分析记录 #{analysis.id}</h1>
          <div className="sub">
            岗位：{analysis.job_title} · 模型：{analysis.model_name || '未知'} ·{' '}
            {new Date(analysis.finished_at || analysis.created_at).toLocaleString()} ·{' '}
            {statusLabel(analysis.status)}
          </div>
        </div>
        <button className="secondary" onClick={exportReport}>
          导出本次分析报告
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}

      <div className="card">
        <div className="card-head">
          <h2>这次分析的输入快照</h2>
          <span className="spacer" />
          {resume && (
            <Link to={`/resumes/${resume.id}`}>
              <button className="secondary">打开这份简历</button>
            </Link>
          )}
        </div>
        <p className="muted">
          历史记录是<strong>只读回放</strong>：下面是发起这次分析时冻结的岗位描述与简历内容，
          不会随之后的修改而变化。要采纳建议或补充经历，请到工作台的当前修改稿里操作。
        </p>
        <details className="job-desc">
          <summary>岗位描述（{analysis.job_title}）</summary>
          <div className="quote">{analysis.job_snapshot || '（空）'}</div>
        </details>
        <details className="job-desc">
          <summary>简历快照{resume ? `（${resume.title}）` : ''}</summary>
          <div className="quote scroll">{analysis.resume_snapshot || '（空）'}</div>
        </details>
      </div>

      <AnalysisResult analysis={analysis} readOnly numbered={false} />
    </>
  )
}
