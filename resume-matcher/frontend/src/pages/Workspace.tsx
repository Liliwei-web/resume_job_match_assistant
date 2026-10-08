import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import JobFormModal from '../components/JobFormModal'
import PreviewModal from '../components/PreviewModal'
import ResumeEditModal from '../components/ResumeEditModal'
import { downloadMarkdown } from '../markdown'
import type {
  AnalysisSummary,
  ExportPayload,
  Job,
  JobDeletionPreview,
  ResumeDeletionPreview,
  ResumeSummary,
} from '../types'

/** 简历卡片顶部的匹配概览：三段宽度直接按落库的三态计数等比分配，不是折算出来的分数。 */
function MatchOverview({ analysis }: { analysis: AnalysisSummary }) {
  const counts = analysis.status_counts || {}
  const shown = counts['已体现'] ?? 0
  const check = counts['需要补充确认'] ?? 0
  const absent = counts['未体现'] ?? 0
  const total = shown + check + absent

  if (total === 0) {
    return <div className="match-empty">这次分析没有产生可判断的条目</div>
  }

  return (
    <div className="match">
      <div
        className="match-bar"
        role="img"
        aria-label={`已体现 ${shown} 条、需要补充确认 ${check} 条、未体现 ${absent} 条`}
      >
        {shown > 0 && <span className="match-seg ok" style={{ flexGrow: shown }} />}
        {check > 0 && <span className="match-seg chk" style={{ flexGrow: check }} />}
        {absent > 0 && <span className="match-seg no" style={{ flexGrow: absent }} />}
      </div>
      <div className="match-legend">
        <span className="lg ok">已体现 {shown}</span>
        <span className="lg chk">需确认 {check}</span>
        <span className="lg no">未体现 {absent}</span>
        <span className="lg">共 {total} 条</span>
      </div>
      <div className="match-meta">
        最近分析：{analysis.job_title} · {new Date(analysis.created_at).toLocaleString()}
        {analysis.adopted_suggestion_count > 0
          ? ` · 已采纳 ${analysis.adopted_suggestion_count} 条`
          : ''}
      </div>
    </div>
  )
}

export default function Workspace() {
  const [resumes, setResumes] = useState<ResumeSummary[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const [resumeTitle, setResumeTitle] = useState('')
  const [resumeText, setResumeText] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [jobDescription, setJobDescription] = useState('')
  const [busy, setBusy] = useState('')
  // 「新建」是动作而不是页面，所以做成工作台里的按钮 + 弹窗，不占侧栏导航。
  const [newOpen, setNewOpen] = useState(false)
  const [newTab, setNewTab] = useState<'resume' | 'job'>('resume')
  // 素材管理：预览（只读）与编辑（改标题/原稿、改岗位）都在工作台就地完成。
  const [previewResume, setPreviewResume] = useState<ResumeSummary | null>(null)
  const [editResume, setEditResume] = useState<ResumeSummary | null>(null)
  const [editJob, setEditJob] = useState<Job | null>(null)
  const [pending, setPending] = useState<
    | { kind: 'resume'; id: number; preview: ResumeDeletionPreview }
    | { kind: 'job'; id: number; preview: JobDeletionPreview }
    | null
  >(null)
  const [deleteBusy, setDeleteBusy] = useState<'' | 'delete' | 'export'>('')
  const [deleteError, setDeleteError] = useState('')

  const reload = useCallback(async () => {
    setError('')
    try {
      const [resumeList, jobList, analysisList] = await Promise.all([
        api.get<ResumeSummary[]>('/api/resumes'),
        api.get<Job[]>('/api/jobs'),
        api.get<AnalysisSummary[]>('/api/analyses'),
      ])
      setResumes(resumeList)
      setJobs(jobList)
      setAnalyses(analysisList)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  async function createResume(event: FormEvent) {
    event.preventDefault()
    if (!resumeTitle.trim() || !resumeText.trim()) {
      setError('请填写简历名称和简历正文')
      return
    }
    setBusy('resume')
    setError('')
    try {
      await api.post('/api/resumes', { title: resumeTitle, original_text: resumeText })
      setResumeTitle('')
      setResumeText('')
      setNewOpen(false)
      setMessage('简历已保存')
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function createJob(event: FormEvent) {
    event.preventDefault()
    if (!jobTitle.trim() || !jobDescription.trim()) {
      setError('请填写岗位名称和岗位描述')
      return
    }
    setBusy('job')
    setError('')
    try {
      await api.post('/api/jobs', { title: jobTitle, description: jobDescription })
      setJobTitle('')
      setJobDescription('')
      setNewOpen(false)
      setMessage('岗位已保存')
      await reload()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  if (loading) {
    return (
      <div className="page-loading">
        <span className="spinner" />
        正在加载简历与岗位…
      </div>
    )
  }

  async function askDeleteResume(resume: ResumeSummary) {
    setError('')
    setMessage('')
    try {
      const preview = await api.get<ResumeDeletionPreview>(
        `/api/resumes/${resume.id}/deletion-preview`,
      )
      setDeleteError('')
      setPending({ kind: 'resume', id: resume.id, preview })
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function askDeleteJob(job: Job) {
    setError('')
    setMessage('')
    try {
      const preview = await api.get<JobDeletionPreview>(`/api/jobs/${job.id}/deletion-preview`)
      setDeleteError('')
      setPending({ kind: 'job', id: job.id, preview })
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function confirmDelete() {
    if (!pending) return
    setDeleteBusy('delete')
    setDeleteError('')
    const path =
      pending.kind === 'resume' ? `/api/resumes/${pending.id}` : `/api/jobs/${pending.id}`
    try {
      await api.del(path)
      setMessage(
        pending.kind === 'resume'
          ? '简历及其分析记录、修改稿版本已删除'
          : '岗位已删除；用它跑过的分析记录保留，岗位名仍显示当时的快照',
      )
      setPending(null)
      await reload()
    } catch (err) {
      setDeleteError(errorMessage(err))
    } finally {
      setDeleteBusy('')
    }
  }

  /** 推荐路径：先按最新的修改稿导出 Markdown，导出成功后再删除。 */
  async function exportThenDelete() {
    if (!pending || pending.kind !== 'resume') return
    setDeleteBusy('export')
    setDeleteError('')
    try {
      const payload = await api.get<ExportPayload>(`/api/resumes/${pending.id}/export`)
      downloadMarkdown(payload.filename, payload.content)
      await api.del(`/api/resumes/${pending.id}`)
      setMessage(`已导出 v${payload.revision_version}（${payload.filename}），简历已删除`)
      setPending(null)
      await reload()
    } catch (err) {
      setDeleteError(errorMessage(err))
    } finally {
      setDeleteBusy('')
    }
  }

  function deleteDialog() {
    if (!pending) return { lines: [] as string[], warning: undefined as string | undefined }
    if (pending.kind === 'job') {
      const { title, analysis_count, resume_count } = pending.preview
      const lines = [`将删除岗位《${title}》。此操作不可恢复。`]
      if (analysis_count > 0) {
        lines.push(
          `有 ${analysis_count} 条分析用过这个岗位（涉及 ${resume_count} 份简历）；` +
            '这些分析记录会保留，岗位名继续显示当时的快照内容。',
        )
      }
      return { lines }
    }
    const { title, adopted_suggestions, analysis_count, revision_count, running_analysis_count } =
      pending.preview
    const lines = [`将删除《${title}》。`]
    lines.push(
      adopted_suggestions > 0
        ? `此操作不可恢复，已采纳 ${adopted_suggestions} 条建议的修改稿将一并删除。`
        : '此操作不可恢复。',
    )
    if (analysis_count > 0 || revision_count > 0) {
      lines.push(`同时删除 ${analysis_count} 条分析记录、${revision_count} 版已保存的修改稿。`)
    }
    return {
      lines,
      warning:
        running_analysis_count > 0
          ? `这份简历还有 ${running_analysis_count} 个分析任务正在进行，等它结束再删除。`
          : undefined,
    }
  }

  /** 卡片顶部只展示最近一次成功的分析，避免「一份简历跑过多次」时显示哪一次的歧义。 */
  function latestSucceeded(resumeId: number): AnalysisSummary | null {
    let best: AnalysisSummary | null = null
    for (const row of analyses) {
      if (row.resume_id !== resumeId || row.status !== 'succeeded') continue
      if (!best || row.id > best.id) best = row
    }
    return best
  }

  const dialog = deleteDialog()

  return (
    <>
      <div className="page-head">
        <div>
          <h1>工作台</h1>
          <div className="sub">
            {resumes.length} 份简历 · {jobs.length} 个目标岗位
          </div>
        </div>
        <button className="primary" onClick={() => setNewOpen(true)}>
          ＋ 新建
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}

      <div className="card">
        <h2>我的简历</h2>
        {resumes.length === 0 ? (
          <div className="empty">还没有简历。点右上角的「＋ 新建」粘贴一份简历正文即可创建。</div>
        ) : (
          <div className="tile-grid">
            {resumes.map((resume) => {
              const latest = latestSucceeded(resume.id)
              return (
                <article className="tile card-lift" key={resume.id}>
                  <div className="tile-head">
                    <Link to={`/resumes/${resume.id}`} className="tile-title">
                      {resume.title}
                    </Link>
                    <span className="tile-meta">
                      修改稿 {resume.revision_count} 版
                      {resume.latest_revision ? ` · v${resume.latest_revision.version}` : ''}
                    </span>
                  </div>
                  {latest ? (
                    <MatchOverview analysis={latest} />
                  ) : (
                    <div className="match-empty">还没有分析记录 · 打开后选择岗位即可发起分析</div>
                  )}
                  <div className="tile-foot">
                    <span className="tile-meta">
                      创建于 {new Date(resume.created_at).toLocaleDateString()}
                    </span>
                    <span className="row">
                      <button className="ghost" onClick={() => setPreviewResume(resume)}>
                        预览
                      </button>
                      <button className="ghost" onClick={() => setEditResume(resume)}>
                        编辑
                      </button>
                      <Link to={`/resumes/${resume.id}`}>
                        <button className="secondary">打开并分析</button>
                      </Link>
                      <button className="ghost danger-text" onClick={() => askDeleteResume(resume)}>
                        删除
                      </button>
                    </span>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>

      <div className="card">
        <h2>我的目标岗位</h2>
        <p className="muted">
          岗位是账号级的素材池，不与某份简历绑定：打开任意一份简历后，在下拉框里选择要匹配的岗位即可。
        </p>
        {jobs.length === 0 ? (
          <div className="empty">还没有岗位。粘贴岗位描述后即可用于匹配分析。</div>
        ) : (
          <div className="tile-grid">
            {jobs.map((job) => {
              const used = analyses.filter((row) => row.job_id === job.id).length
              return (
                <article className="tile card-lift" key={job.id}>
                  <div className="tile-head">
                    <strong className="tile-title">{job.title}</strong>
                    <span className="tile-meta">
                      {used > 0 ? `已用于 ${used} 次分析` : '未跑过分析'}
                    </span>
                  </div>
                  <details className="job-desc">
                    <summary>查看岗位描述</summary>
                    <div className="quote">{job.description}</div>
                  </details>
                  <div className="tile-foot">
                    <span className="tile-meta">
                      创建于 {new Date(job.created_at).toLocaleDateString()}
                    </span>
                    <span className="row">
                      <button className="ghost" onClick={() => setEditJob(job)}>
                        编辑
                      </button>
                      <button className="ghost danger-text" onClick={() => askDeleteJob(job)}>
                        删除
                      </button>
                    </span>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>

      {newOpen && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal" style={{ maxWidth: 620 }}>
            <div className="row between">
              <h3>新建素材</h3>
              <button className="ghost" onClick={() => setNewOpen(false)}>
                关闭
              </button>
            </div>
            <div className="segmented" role="tablist" aria-label="新建类型">
              <button
                className={`seg-btn ${newTab === 'resume' ? 'active' : ''}`}
                role="tab"
                aria-selected={newTab === 'resume'}
                onClick={() => setNewTab('resume')}
              >
                简历（原稿）
              </button>
              <button
                className={`seg-btn ${newTab === 'job' ? 'active' : ''}`}
                role="tab"
                aria-selected={newTab === 'job'}
                onClick={() => setNewTab('job')}
              >
                目标岗位
              </button>
            </div>

            {newTab === 'resume' ? (
              <form onSubmit={createResume}>
                <div className="field">
                  <label>简历名称</label>
                  <input
                    value={resumeTitle}
                    onChange={(e) => setResumeTitle(e.target.value)}
                    placeholder="例如：陈曦-前端工程师简历"
                  />
                </div>
                <div className="field">
                  <label>简历正文（纯文本，建议包含教育背景、技能、项目经历）</label>
                  <textarea
                    rows={12}
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    placeholder="粘贴简历正文…"
                  />
                </div>
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="primary" type="submit" disabled={busy === 'resume'}>
                    {busy === 'resume' ? '保存中…' : '保存简历'}
                  </button>
                  <button type="button" onClick={() => setNewOpen(false)}>
                    取消
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={createJob}>
                <div className="field">
                  <label>岗位名称</label>
                  <input
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="例如：后端开发工程师（初级）"
                  />
                </div>
                <div className="field">
                  <label>岗位描述</label>
                  <textarea
                    rows={12}
                    value={jobDescription}
                    onChange={(e) => setJobDescription(e.target.value)}
                    placeholder="粘贴岗位职责与任职要求…"
                  />
                </div>
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="primary" type="submit" disabled={busy === 'job'}>
                    {busy === 'job' ? '保存中…' : '保存岗位'}
                  </button>
                  <button type="button" onClick={() => setNewOpen(false)}>
                    取消
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {pending && (
        <ConfirmDeleteModal
          title={pending.kind === 'resume' ? '删除这份简历？' : '删除这个岗位？'}
          lines={dialog.lines}
          warning={dialog.warning}
          error={deleteError}
          busy={deleteBusy}
          onCancel={() => {
            setPending(null)
            setDeleteError('')
          }}
          onConfirm={confirmDelete}
          exportLabel={pending.kind === 'resume' ? '先导出再删' : undefined}
          onExportAndDelete={pending.kind === 'resume' ? exportThenDelete : undefined}
        />
      )}

      {previewResume && (
        <PreviewModal
          title={`${previewResume.title} · 预览`}
          onClose={() => setPreviewResume(null)}
          tabs={[
            { key: 'original', label: '原始简历', content: previewResume.original_text },
            { key: 'draft', label: '修改稿', content: previewResume.draft_content },
          ]}
        />
      )}

      {editResume && (
        <ResumeEditModal
          resume={editResume}
          onClose={() => setEditResume(null)}
          onSaved={async (saved) => {
            // 只改名称时说「原稿已保存」容易让人以为正文动了，这里分开写。
            const bodyChanged = saved.original_text.trim() !== editResume.original_text.trim()
            setEditResume(null)
            setMessage(
              bodyChanged
                ? '简历已更新：标题与原稿已保存，历史分析快照不受影响'
                : '简历已更新：只改了名称，原稿与修改稿都没动',
            )
            await reload()
          }}
        />
      )}

      {editJob && (
        <JobFormModal
          job={editJob}
          onClose={() => setEditJob(null)}
          onSaved={async () => {
            setEditJob(null)
            setMessage('岗位已更新：之后的「新建分析任务」会用新描述，历史记录不变')
            await reload()
          }}
        />
      )}
    </>
  )
}
