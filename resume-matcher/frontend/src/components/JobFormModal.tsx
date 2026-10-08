import { useState } from 'react'
import { api, errorMessage } from '../api'
import type { Job } from '../types'

interface Props {
  job: Job
  onClose: () => void
  onSaved: (job: Job) => void
}

/** 编辑已有岗位：小幅改动不必新建再删旧的。 */
export default function JobFormModal({ job, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(job.title)
  const [description, setDescription] = useState(job.description)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const changed = title.trim() !== job.title || description.trim() !== job.description

  async function save() {
    if (!title.trim() || !description.trim()) {
      setError('岗位名称和岗位描述都不能为空')
      return
    }
    setBusy(true)
    setError('')
    try {
      const saved = await api.put<Job>(`/api/jobs/${job.id}`, { title, description })
      onSaved(saved)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑岗位">
      <div className="modal" style={{ maxWidth: 620 }}>
        <div className="row between">
          <h3>编辑岗位</h3>
          <button className="ghost" onClick={onClose} disabled={busy}>
            关闭
          </button>
        </div>
        <div className="field">
          <label>岗位名称</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div className="field">
          <label>岗位描述</label>
          <textarea
            rows={12}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <div className="warn-box">
          改完之后<strong>只有之后的「新建分析任务」用新描述</strong>。已经跑过的分析保存的是发起时的岗位快照
          （含当时的岗位名），历史记录与已有结果都不会跟着变。
        </div>
        {error && <div className="error-box">{error}</div>}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={save} disabled={busy || !changed}>
            {busy ? '保存中…' : '保存岗位'}
          </button>
          <button onClick={onClose} disabled={busy}>
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
