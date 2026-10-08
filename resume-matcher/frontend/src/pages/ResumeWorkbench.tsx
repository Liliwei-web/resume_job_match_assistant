import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api'
import AnalysisResult from '../components/AnalysisResult'
import JobPicker from '../components/JobPicker'
import PreviewModal from '../components/PreviewModal'
import SupplementModal from '../components/SupplementModal'
import { IconExpand, IconEye, IconPencil, IconPlus, IconTrash } from '../components/icons'
import { downloadMarkdown, renderMarkdown } from '../markdown'
import {
  isDeletableLine,
  itemForLine,
  planDelete,
  removeLineAt,
  suggestionForLine,
  uniqueLineIndex,
} from '../matching'
import type {
  AnalysisDetail,
  AnalysisItem,
  ExportPayload,
  Job,
  ResumeSummary,
  Revision,
  Supplement,
} from '../types'

// 简历与岗位在系统里并不绑定（同一份简历可以分别对多个岗位分析）。
// 这里只按“标题的最长公共子串 + 公共子串个数”给下拉框挑一个贴近的默认值：
//   陈曦-前端工程师简历 × 高级前端工程师 -> 最长 5（“前端工程师”），稳赢；
//   刘洋-Go后端简历   × 后端开发工程师（Go）/（初级）-> 最长都是 2，
//                       但前者还多一个公共子串“Go”，所以能挑中 Go 岗。
function titleMatchScore(resumeTitle: string, jobTitle: string): { longest: number; shared: number } {
  const pieces = new Set<string>()
  let longest = 0
  for (let start = 0; start < resumeTitle.length; start += 1) {
    for (let end = start + 2; end <= resumeTitle.length; end += 1) {
      const piece = resumeTitle.slice(start, end)
      if (!jobTitle.includes(piece)) break
      longest = Math.max(longest, piece.length)
      pieces.add(piece)
    }
  }
  return { longest, shared: pieces.size }
}

const MIN_TITLE_MATCH = 2

export default function ResumeWorkbench() {
  const { resumeId } = useParams()
  const id = Number(resumeId)

  const [resume, setResume] = useState<ResumeSummary | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null)
  const [draft, setDraft] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [jobId, setJobId] = useState<number | ''>('')
  const [suggestedJobId, setSuggestedJobId] = useState<number | ''>('')
  const [supplementItem, setSupplementItem] = useState<AnalysisItem | null>(null)
  const [deleted, setDeleted] = useState<{ content: string; line: string } | null>(null)
  const [flash, setFlash] = useState('')
  // 刚被采纳进修改稿的文本：用来给对应行做一次 0.5s 的高亮淡出。
  const [justChanged, setJustChanged] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState('')

  // 修改稿一栏在「预览」（渲染后可悬停操作）与「编辑」（纯文本框）之间切换，默认先看结果。
  const [draftView, setDraftView] = useState<'preview' | 'edit'>('preview')

  // 「放大」视图：预览的只读大字版，弹窗展示，用来核对长段落。
  const [zoomOpen, setZoomOpen] = useState(false)
  // 点版本列表里的小眼睛：只读预览那一版，可切到当前工作稿对照。
  const [previewRevision, setPreviewRevision] = useState<Revision | null>(null)

  const dirty = draft !== savedContent

  const loadResume = useCallback(async () => {
    const data = await api.get<ResumeSummary>(`/api/resumes/${id}`)
    setResume(data)
    setDraft(data.draft_content)
    const revisions = (data.revisions || []).slice().sort((a, b) => a.version - b.version)
    setSavedContent(revisions.length ? revisions[revisions.length - 1].content_md : '')
  }, [id])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [resumeData, jobList] = await Promise.all([
          api.get<ResumeSummary>(`/api/resumes/${id}`),
          api.get<Job[]>('/api/jobs'),
        ])
        if (cancelled) return
        setResume(resumeData)
        setDraft(resumeData.draft_content)
        const revisions = (resumeData.revisions || []).slice().sort((a, b) => a.version - b.version)
        setSavedContent(revisions.length ? revisions[revisions.length - 1].content_md : '')
        setJobs(jobList)
        let bestId: number | '' = ''
        let bestScore = { longest: MIN_TITLE_MATCH - 1, shared: 0 }
        jobList.forEach((job) => {
          const score = titleMatchScore(resumeData.title, job.title)
          if (
            score.longest > bestScore.longest ||
            (score.longest === bestScore.longest && score.shared > bestScore.shared)
          ) {
            bestScore = score
            bestId = job.id
          }
        })
        setSuggestedJobId(bestId)
        setJobId(bestId)
      } catch (err) {
        setError(errorMessage(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  // Poll the running analysis until it reaches a terminal state.
  useEffect(() => {
    if (!analysis) return
    if (analysis.status === 'succeeded' || analysis.status === 'failed') return
    const timer = window.setTimeout(async () => {
      try {
        const data = await api.get<AnalysisDetail>(`/api/analyses/${analysis.id}`)
        setAnalysis(data)
        if (data.status === 'succeeded') setMessage('分析完成')
      } catch (err) {
        setError(errorMessage(err))
      }
    }, 1500)
    return () => window.clearTimeout(timer)
  }, [analysis])

  async function startAnalysis() {
    if (jobId === '') {
      setError('请先选择目标岗位（可在工作台新建岗位）')
      return
    }
    setBusy('analyze')
    setError('')
    setMessage('')
    try {
      const created = await api.post<{ id: number }>('/api/analyses', {
        resume_id: id,
        job_id: Number(jobId),
      })
      const detail = await api.get<AnalysisDetail>(`/api/analyses/${created.id}`)
      setAnalysis(detail)
      await api.post(`/api/analyses/${created.id}/run`)
      const running = await api.get<AnalysisDetail>(`/api/analyses/${created.id}`)
      setAnalysis(running)
      setMessage('已发起分析，模型正在处理…')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function retryAnalysis() {
    if (!analysis) return
    setBusy('analyze')
    setError('')
    try {
      await api.post(`/api/analyses/${analysis.id}/run`)
      const data = await api.get<AnalysisDetail>(`/api/analyses/${analysis.id}`)
      setAnalysis(data)
      setMessage('已重新发起分析')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  /** 采纳后把「新进去的那段文字」记下来，右侧预览据此闪一下，让改动可见。 */
  function markChanged(text: string | null | undefined) {
    if (!text) return
    setJustChanged(text)
    window.setTimeout(() => setJustChanged((current) => (current === text ? '' : current)), 900)
  }

  async function decide(suggestionId: number, decision: '采纳' | '忽略' | '未处理') {
    setBusy(`s${suggestionId}`)
    setError('')
    setMessage('')
    try {
      const result = await api.post<{ draft_content: string }>(
        `/api/suggestions/${suggestionId}/decision`,
        { decision },
      )
      setDraft(result.draft_content)
      if (analysis) {
        setAnalysis(await api.get<AnalysisDetail>(`/api/analyses/${analysis.id}`))
      }
      setDeleted(null) // 修改稿被后端刷新过，之前那次删除的撤销点已经失效
      if (decision === '采纳') {
        markChanged(analysis?.suggestions.find((row) => row.id === suggestionId)?.suggested_passage)
      }
      setMessage(decision === '采纳' ? '已采纳该建议，修改稿已更新' : '已忽略该建议')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function polishSupplement(text: string): Promise<Supplement> {
    if (!analysis || !supplementItem) throw new Error('缺少分析上下文，请重新打开分析结果')
    const result = await api.post<{ supplement: Supplement }>('/api/supplement', {
      analysis_id: analysis.id,
      item_id: supplementItem.id,
      text,
    })
    return result.supplement
  }

  async function decideSupplement(supplementId: number, decision: '采纳' | '忽略') {
    const result = await api.post<{ draft_content: string }>(
      `/api/supplements/${supplementId}/decision`,
      { decision },
    )
    setDraft(result.draft_content)
    if (analysis) {
      setAnalysis(await api.get<AnalysisDetail>(`/api/analyses/${analysis.id}`))
    }
    if (decision === '采纳') {
      const row = analysis?.items.find((item) => item.supplement?.id === supplementId)
      markChanged(row?.supplement?.polished_text)
    }
    setMessage(
      decision === '采纳' ? '已采纳补充内容，修改稿右栏已更新' : '已忽略这次补充，修改稿未改动',
    )
  }

  /** 跳到上方分析区/建议区的目标并闪一下，让用户知道跳到了哪里。 */
  function jumpTo(targetId: string) {
    const element = document.getElementById(targetId)
    if (!element) {
      setError('上方找不到对应的条目，可能已被清空，请重新发起分析。')
      return
    }
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setFlash(targetId)
    window.setTimeout(() => setFlash((current) => (current === targetId ? '' : current)), 2400)
  }

  /** 原稿某行的「编辑」：未体现／需要补充确认 → 打开补充框；否则跳到上方对应建议或条目。 */
  function editFromLine(line: string) {
    if (!analysis) return
    setError('')
    const item = itemForLine(line, analysis.items)
    if (item && item.match_status !== '已体现') {
      setSupplementItem(item)
      return
    }
    const suggestion = suggestionForLine(line, analysis.suggestions)
    if (suggestion) {
      jumpTo(`suggestion-${suggestion.id}`)
      return
    }
    if (item) {
      jumpTo(`item-${item.id}`)
      return
    }
    setError('这一行没有对应的分析条目或建议。')
  }

  function applyDelete(before: string, index: number, line: string) {
    setDeleted({ content: before, line })
    setDraft(removeLineAt(before, index))
    setError('')
  }

  function undoDelete() {
    if (!deleted) return
    setDraft(deleted.content)
    setDeleted(null)
    setMessage('已恢复刚删除的那一行')
  }

  /**
   * 删掉修改稿里与这一行对应的段落。原稿只读，永远不动。
   * 原稿行 ↔ 修改稿行不是一一对应，所以定位规则全部是确定性的（见 planDelete）。
   */
  async function deleteLine(line: string) {
    setMessage('')
    // 删除本身只是改文本，没有分析结果也能用；只有“先退回建议再删”那条路需要分析上下文。
    const plan = planDelete(line, draft, analysis?.suggestions ?? [])
    if (plan.kind === 'blocked') {
      setError(plan.reason)
      return
    }
    if (plan.kind === 'remove') {
      applyDelete(draft, plan.index, line)
      setMessage('已从修改稿删除这一行（原稿未改动）')
      return
    }
    if (!analysis) {
      // planDelete 拿不到建议列表时不会返回 undo-then-remove，这里只为把类型收窄成非空。
      setError('当前页面没有加载分析结果，请先刷新后重试。')
      return
    }
    // 这一行的原文已被采纳的改写替换掉了：先把建议退回“未处理”让原句回来，再删。
    if (dirty) {
      setError('修改稿有未保存的改动，请先点“暂存草稿”，再删除这一段（避免覆盖你刚改的内容）。')
      return
    }
    setBusy('delete')
    setError('')
    try {
      const result = await api.post<{ draft_content: string }>(
        `/api/suggestions/${plan.suggestionId}/decision`,
        { decision: '未处理' },
      )
      setAnalysis(await api.get<AnalysisDetail>(`/api/analyses/${analysis.id}`))
      const index = uniqueLineIndex(result.draft_content, line)
      if (index < 0) {
        setDraft(result.draft_content)
        setError('已把那条建议退回“未处理”，但这一行在修改稿里未能唯一定位，请手动删除。')
        return
      }
      applyDelete(result.draft_content, index, line)
      setMessage('已把该建议退回“未处理”，并从修改稿删除了这一行')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function saveDraftOnly() {
    setBusy('draft')
    setError('')
    setMessage('')
    try {
      await api.put(`/api/resumes/${id}/draft`, { content_md: draft })
      setMessage('修改稿已暂存（尚未生成新版本）')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function saveRevision() {
    setBusy('revision')
    setError('')
    setMessage('')
    try {
      await api.put(`/api/resumes/${id}/draft`, { content_md: draft })
      const revision = await api.post<Revision>(`/api/resumes/${id}/revisions`, { note: '' })
      setSavedContent(revision.content_md)
      setMessage(`修改稿已保存为 v${revision.version}`)
      await loadResume()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function exportMarkdown() {
    setError('')
    setMessage('')
    try {
      // 先把本页还没暂存的改动推给服务端，导出接口再把它存成一版，
      // 这样下载到的就是此刻看到的内容，不会导出旧版本。
      if (draft !== savedContent) {
        await api.put(`/api/resumes/${id}/draft`, { content_md: draft })
      }
      const payload = await api.get<ExportPayload>(`/api/resumes/${id}/export`)
      downloadMarkdown(payload.filename, payload.content)
      setMessage(`已导出最新修改稿 v${payload.revision_version}（${payload.filename}）`)
      await loadResume() // 导出会存成一版，刷新版本列表
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (loading) {
    return (
      <div className="page-loading">
        <span className="spinner" />
        正在加载简历…
      </div>
    )
  }

  if (!resume) {
    return (
      <>
        <div className="error-box">{error || '简历不存在或无权访问'}</div>
        <Link to="/">返回工作台</Link>
      </>
    )
  }

  const running = analysis && (analysis.status === 'pending' || analysis.status === 'running')

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{resume.title}</h1>
          <div className="sub">
            原稿只读 · 修改稿已保存 {(resume.revisions || []).length} 版
          </div>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}
      {deleted && (
        <div className="success-box row between">
          <span>已从修改稿删除这一段（原稿未改动）：{deleted.line.trim().slice(0, 32)}…</span>
          <button className="ghost" onClick={undoDelete}>
            撤销删除
          </button>
        </div>
      )}

      <div className="card">
        <h2>1. 发起匹配分析</h2>
        <div className="row">
          <JobPicker jobs={jobs} value={jobId} suggestedId={suggestedJobId} onChange={setJobId} />
          <button className="primary" onClick={startAnalysis} disabled={busy === 'analyze' || !!running}>
            {running ? '分析中…' : '新建分析任务'}
          </button>
          {analysis && (
            <button className="ghost" onClick={() => setAnalysis(null)} disabled={!!running}>
              清空当前结果
            </button>
          )}
        </div>
        {jobs.length === 0 && <div className="empty">还没有岗位，请先到工作台新建目标岗位。</div>}
        <p className="muted">
          岗位与简历<strong>不做绑定</strong>：同一份简历可以分别对多个岗位发起分析，这里只是按简历标题预选了一个贴近的岗位（预选的那个岗位在下拉列表里带一个绿色的「匹配」标记），随时可以切换。
          每次分析都会保存当时的简历与岗位快照；不会覆盖已保存的修改稿。
        </p>
      </div>

      {!analysis ? (
        <>
          <div className="card">
            <h2>2. 要求—证据—判断</h2>
            <div className="empty">尚未发起分析。选择岗位后点击“新建分析任务”。</div>
          </div>
          <div className="card">
            <h2>3. 逐条修改建议</h2>
            <div className="empty">分析完成后，这里会列出可采纳或忽略的修改建议。</div>
          </div>
        </>
      ) : (
        <AnalysisResult
          analysis={analysis}
          busy={busy}
          flash={flash}
          onSupplement={setSupplementItem}
          onDecide={decide}
          onRetry={retryAnalysis}
        />
      )}

      <div className="card">
        <h2>4. 修改稿与原始简历对照</h2>
        <div className="compare-grid">
          <div className="col sunken">
            <div className="col-head">
              <h3>原始简历</h3>
              <span className="pill status">只读</span>
            </div>
            <p className="muted">
              鼠标移到某一行上，右上角才会浮出一个小按钮：
              <strong>编辑</strong>＝该段对应「未体现 / 需要补充确认」就打开补充框，对应「已体现」且有建议就跳到上方对应位置。
              原稿<strong>只读</strong>，这里没有任何删除入口；要删段落请到右栏的<strong>修改稿</strong>里操作。
            </p>
            <div className="preview plain scroll">
              {resume.original_text.split(/\r?\n/).map((line, index) => {
                const item = analysis ? itemForLine(line, analysis.items) : null
                const suggestion = analysis ? suggestionForLine(line, analysis.suggestions) : null
                const canEdit = Boolean(item || suggestion)
                const editTitle =
                  item && item.match_status !== '已体现'
                    ? `补充「${item.requirement_quote}」的经历`
                    : suggestion
                    ? '跳到上方对应建议'
                    : '跳到上方对应条目'
                return (
                  <div className="preview-line" key={index}>
                    <div
                      className="preview-line-body"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(line) }}
                    />
                    {canEdit && (
                      <span className="line-actions">
                        {canEdit && (
                          <button
                            className="icon-btn"
                            title={editTitle}
                            aria-label={editTitle}
                            onClick={() => editFromLine(line)}
                          >
                            <IconPencil />
                          </button>
                        )}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
          <div className="col">
            <div className="col-head">
              <h3>修改稿</h3>
              {draftView === 'preview' && (
                <button
                  className="ghost zoom-btn"
                  onClick={() => setZoomOpen(true)}
                  title="放大预览：在弹窗里用更大字号查看修改稿"
                >
                  <IconExpand />
                  放大
                </button>
              )}
              <div className="segmented" role="tablist" aria-label="修改稿视图">
                <button
                  className={`seg-btn ${draftView === 'preview' ? 'active' : ''}`}
                  role="tab"
                  aria-selected={draftView === 'preview'}
                  onClick={() => setDraftView('preview')}
                >
                  预览
                </button>
                <button
                  className={`seg-btn ${draftView === 'edit' ? 'active' : ''}`}
                  role="tab"
                  aria-selected={draftView === 'edit'}
                  onClick={() => setDraftView('edit')}
                >
                  编辑
                </button>
              </div>
            </div>
            <p className="muted">
              鼠标移到某一行上会浮出小按钮：<strong>＋</strong>＝该行是「未体现 / 需要补充确认」的证据句，点它打开补充框；
              <strong>删除</strong>＝把这一行从修改稿去掉。这里的补充与删除都只作用于修改稿，原稿不会被改动。
            </p>
            {draftView === 'preview' ? (
              <div className="preview plain scroll">
                {draft.split(/\r?\n/).map((line, index) => {
                  const item = analysis ? itemForLine(line, analysis.items) : null
                  const supplementable = Boolean(item && item.match_status !== '已体现')
                  const deletable = isDeletableLine(line)
                  // 刚采纳进来的那一行闪一下。两个方向都要比：改后的正文带 Markdown 前缀
                  // （比如「- 」），单看一个方向会漏判；同时排除空行与过短的串。
                  const fresh = justChanged.trim()
                  const isFreshLine = Boolean(
                    fresh.length >= 4 &&
                      line.trim() &&
                      (line.includes(fresh) || fresh.includes(line.trim())),
                  )
                  return (
                    <div
                      className={`preview-line${isFreshLine ? ' line-fresh' : ''}`}
                      key={index}
                    >
                      <div
                        className="preview-line-body"
                        dangerouslySetInnerHTML={{ __html: renderMarkdown(line) }}
                      />
                      {(supplementable || deletable) && (
                        <span className="line-actions">
                          {supplementable && item && (
                            <button
                              className="icon-btn"
                              title={
                                item.supplement_state === '已补充' ? '已补充，可继续追加' : '补充真实经历'
                              }
                              aria-label="补充真实经历"
                              onClick={() => setSupplementItem(item)}
                            >
                              <IconPlus />
                            </button>
                          )}
                          {deletable && (
                            <button
                              className="icon-btn"
                              title="从修改稿删除这一行（原稿只读）"
                              aria-label="从修改稿删除这一行"
                              disabled={busy === 'delete'}
                              onClick={() => deleteLine(line)}
                            >
                              <IconTrash />
                            </button>
                          )}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : (
              <textarea rows={18} value={draft} onChange={(e) => setDraft(e.target.value)} />
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h2>5. 修改稿的保存与版本</h2>
          <span className={`draft-state${dirty ? ' is-dirty' : ''}`}>
            {dirty ? '修改稿有未保存的改动' : '修改稿与最近保存的版本一致'}
            {resume.latest_revision
              ? ` · 最近保存 v${resume.latest_revision.version}`
              : ' · 尚未保存过修改稿'}
          </span>
        </div>
        <div className="draft-bar">
          <button className="secondary" onClick={saveDraftOnly} disabled={busy === 'draft'}>
            暂存草稿
          </button>
          <button className="primary" onClick={saveRevision} disabled={busy === 'revision'}>
            保存修改稿（生成新版本）
          </button>
          <button className="secondary" onClick={exportMarkdown}>
            导出 Markdown
          </button>
          <span className="spacer" />
          <span className="muted">暂存只留在工作稿；「保存修改稿」才会生成一个新版本</span>
        </div>
        {(resume.revisions || []).length === 0 ? (
          <div className="version-empty">
            还没有保存过修改稿 —— 点上面的「保存修改稿（生成新版本）」会在这里留下 v1。
          </div>
        ) : (
          <div className="version-list">
            {(resume.revisions || [])
              .slice()
              .sort((a, b) => b.version - a.version)
              .map((revision) => (
                <div className="list-item row between" key={revision.id}>
                  <span>
                    <strong>v{revision.version}</strong>
                    {revision.note ? ` · ${revision.note}` : ''}
                  </span>
                  <span className="row">
                    <span className="tile-meta">
                      约 {revision.content_md.replace(/\s/g, '').length} 字 ·{' '}
                      {new Date(revision.created_at).toLocaleString()}
                    </span>
                    <button
                      className="icon-btn"
                      title={`只读预览 v${revision.version}`}
                      aria-label={`只读预览修改稿 v${revision.version}`}
                      onClick={() => setPreviewRevision(revision)}
                    >
                      <IconEye />
                    </button>
                  </span>
                </div>
              ))}
          </div>
        )}
      </div>

      {zoomOpen && (
        <PreviewModal
          title="修改稿 · 放大预览"
          initialBig
          onClose={() => setZoomOpen(false)}
          tabs={[{ key: 'draft', label: '修改稿', content: draft }]}
        />
      )}

      {previewRevision && (
        <PreviewModal
          title={`修改稿 v${previewRevision.version} · 只读预览`}
          onClose={() => setPreviewRevision(null)}
          tabs={[
            {
              key: 'revision',
              label: `v${previewRevision.version}（这一版）`,
              content: previewRevision.content_md,
            },
            { key: 'draft', label: '当前工作稿', content: draft },
          ]}
        />
      )}

      {supplementItem && analysis && (
        <SupplementModal
          item={analysis.items.find((row) => row.id === supplementItem.id) ?? supplementItem}
          onClose={() => setSupplementItem(null)}
          onPolish={polishSupplement}
          onDecide={decideSupplement}
        />
      )}
    </>
  )
}
