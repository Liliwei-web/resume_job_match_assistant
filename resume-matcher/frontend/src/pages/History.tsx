import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api'
import ConfirmDeleteModal from '../components/ConfirmDeleteModal'
import { statusLabel } from '../labels'
import type { AnalysisSummary, ResumeSummary } from '../types'

const isRunning = (row: AnalysisSummary) => row.status === 'pending' || row.status === 'running'

export default function History() {
  const [resumes, setResumes] = useState<ResumeSummary[]>([])
  const [analyses, setAnalyses] = useState<AnalysisSummary[]>([])
  const [selected, setSelected] = useState<number[]>([])
  // 复选框默认不出现：平时是一张干净的表格，点「管理记录」才进入可勾选/批量删除的模式。
  const [manage, setManage] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  // 待确认的删除：单条与批量走同一个弹窗，只是 ids 的长度不同。
  const [pending, setPending] = useState<number[] | null>(null)
  const [busy, setBusy] = useState<'' | 'delete'>('')

  const load = useCallback(async () => {
    const [resumeList, analysisList] = await Promise.all([
      api.get<ResumeSummary[]>('/api/resumes'),
      api.get<AnalysisSummary[]>('/api/analyses'),
    ])
    setResumes(resumeList)
    setAnalyses(analysisList)
  }, [])

  useEffect(() => {
    ;(async () => {
      try {
        await load()
      } catch (err) {
        setError(errorMessage(err))
      } finally {
        setLoading(false)
      }
    })()
  }, [load])

  if (loading) {
    return (
      <div className="page-loading">
        <span className="spinner" />
        正在加载历史记录…
      </div>
    )
  }

  const allSelected = analyses.length > 0 && selected.length === analyses.length
  const picked = analyses.filter((row) => selected.includes(row.id))
  const pickedAdopted = picked.reduce((sum, row) => sum + row.adopted_suggestion_count, 0)
  const pickedRunning = picked.filter(isRunning).length

  function toggle(id: number) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )
  }

  function exitManage() {
    setManage(false)
    setSelected([])
  }

  async function confirmDelete() {
    if (!pending) return
    setBusy('delete')
    setError('')
    setMessage('')
    try {
      if (pending.length === 1) {
        await api.del(`/api/analyses/${pending[0]}`)
        setMessage(`已删除分析记录 #${pending[0]}`)
      } else {
        const result = await api.post<{ deleted: number[]; missing: number[] }>(
          '/api/analyses/bulk-delete',
          { ids: pending },
        )
        setMessage(
          `已删除 ${result.deleted.length} 条分析记录` +
            (result.missing.length > 0
              ? `（其中 ${result.missing.length} 条不属于当前账号，已跳过）`
              : ''),
        )
      }
      setPending(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>历史记录</h1>
        <span className="sub">{analyses.length} 条分析记录</span>
      </div>
      {error && <div className="error-box">{error}</div>}
      {message && <div className="success-box">{message}</div>}

      <div className="card">
        <h2>我的简历</h2>
        {resumes.length === 0 ? (
          <div className="empty">还没有简历。</div>
        ) : (
          resumes.map((resume) => (
            <div className="list-item row between" key={resume.id}>
              <div>
                <Link to={`/resumes/${resume.id}`}>{resume.title}</Link>
                <div className="muted">
                  创建于 {new Date(resume.created_at).toLocaleString()} · 已保存修改稿{' '}
                  {resume.revision_count} 版
                </div>
              </div>
              <Link to={`/resumes/${resume.id}`}>
                <button className="secondary">打开</button>
              </Link>
            </div>
          ))
        )}
      </div>

      <div className="card">
        <div className="card-head">
          <h2>我的分析记录</h2>
          <span className="spacer" />
          {manage && selected.length > 0 && (
            <button className="danger" onClick={() => setPending(selected)} disabled={busy !== ''}>
              删除所选 {selected.length} 条
            </button>
          )}
          {manage && (
            <button className="secondary" onClick={exitManage} disabled={busy !== ''}>
              退出管理
            </button>
          )}
          {!manage && analyses.length > 0 && (
            <button className="secondary" onClick={() => setManage(true)}>
              管理记录
            </button>
          )}
        </div>
        {analyses.length === 0 ? (
          <div className="empty">还没有分析记录。</div>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {manage && (
                    <th className="pick">
                      <input
                        type="checkbox"
                        aria-label="全选分析记录"
                        checked={allSelected}
                        onChange={() =>
                          setSelected(allSelected ? [] : analyses.map((row) => row.id))
                        }
                      />
                    </th>
                  )}
                  <th>#</th>
                  <th>岗位</th>
                  <th>状态</th>
                  <th>条目 / 建议</th>
                  <th>采纳</th>
                  <th>模型</th>
                  <th>时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {analyses.map((item) => (
                  <tr key={item.id} data-analysis-id={item.id}>
                    {manage && (
                      <td className="pick">
                        <input
                          type="checkbox"
                          aria-label={`选择分析记录 #${item.id}`}
                          checked={selected.includes(item.id)}
                          onChange={() => toggle(item.id)}
                        />
                      </td>
                    )}
                    <td>{item.id}</td>
                    <td>
                      {/* 点开就是当初那次分析的结果（只读回放），简历本身从回放页再进去。 */}
                      <Link to={`/analyses/${item.id}`}>{item.job_title}</Link>
                    </td>
                    <td>
                      <span className="pill status">{statusLabel(item.status)}</span>
                    </td>
                    <td>
                      {item.item_count} / {item.suggestion_count}
                    </td>
                    <td>{item.adopted_suggestion_count}</td>
                    <td className="mono">{item.model_name || '-'}</td>
                    <td>{new Date(item.created_at).toLocaleString()}</td>
                    <td className="row-actions">
                      <Link to={`/analyses/${item.id}`}>
                        <button className="ghost">查看</button>
                      </Link>
                      <button
                        className="ghost danger-text"
                        onClick={() => setPending([item.id])}
                        disabled={busy !== ''}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">
          点岗位名或<strong>查看</strong>可以打开当初那次分析的结果（只读回放，含当时的岗位与简历快照，可在那里导出 Markdown 报告）。
          需要批量清理时点<strong>管理记录</strong>，勾选后再删。删除只清理分析记录（条目、逐条建议、补充记录一并清除，无法恢复），
          已经保存的修改稿与历史版本不受影响；要看新内容带来的判断变化，重新发起一次分析即可。
        </p>
      </div>

      {pending && (
        <ConfirmDeleteModal
          title={pending.length === 1 ? `删除分析记录 #${pending[0]}？` : `删除这 ${pending.length} 条分析记录？`}
          lines={[
            '此操作不可恢复：这些分析的条目、逐条建议与补充记录都会一并删除。',
            '已经保存的修改稿与历史版本不受影响，原稿始终只读保留。',
          ]}
          warning={
            pickedRunning > 0
              ? `选中的记录里有 ${pickedRunning} 条还在进行中，请等它结束后再删除。`
              : pickedAdopted > 0
                ? `其中包含 ${pickedAdopted} 条已采纳的建议——修改稿里的内容不会被回滚。`
                : undefined
          }
          error={error}
          busy={busy}
          onCancel={() => {
            setPending(null)
            setError('')
          }}
          onConfirm={confirmDelete}
        />
      )}
    </>
  )
}
