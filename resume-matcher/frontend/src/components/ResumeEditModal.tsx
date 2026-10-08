import { useState } from 'react'
import { api, errorMessage } from '../api'
import type { ResumeSummary } from '../types'

interface Props {
  resume: ResumeSummary
  onClose: () => void
  onSaved: (resume: ResumeSummary) => void
}

/**
 * 编辑简历素材：标题 + 原稿正文。
 *
 * 「原稿只读」约束的是系统与模型（分析、采纳、补充都不许改它），
 * 用户本人改自己的素材不在此列——但改原稿是个不可逆的覆盖动作，所以走两步：
 * 先编辑，正文真的变了再点一次「确认覆盖」。
 */
export default function ResumeEditModal({ resume, onClose, onSaved }: Props) {
  const [title, setTitle] = useState(resume.title)
  const [original, setOriginal] = useState(resume.original_text)
  const [resetDraft, setResetDraft] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const originalChanged = original.trim() !== resume.original_text.trim()
  const draftDiffers = resume.draft_content.trim() !== resume.original_text.trim()
  const draftChars = resume.draft_content.replace(/\s/g, '').length

  async function save() {
    setBusy(true)
    setError('')
    try {
      const saved = await api.put<ResumeSummary>(`/api/resumes/${resume.id}`, {
        title,
        original_text: original,
        reset_draft: resetDraft,
      })
      onSaved(saved)
    } catch (err) {
      setError(errorMessage(err))
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  function submit() {
    if (!title.trim()) {
      setError('简历名称不能为空')
      return
    }
    if (!original.trim()) {
      setError('简历正文不能为空')
      return
    }
    // 只是改标题就直接存；动了正文才需要一次显式确认。
    if (originalChanged && !confirming) {
      setConfirming(true)
      return
    }
    void save()
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="编辑简历">
      <div className="modal" style={{ maxWidth: 720 }}>
        <div className="row between">
          <h3>编辑简历</h3>
          <button className="ghost" onClick={onClose} disabled={busy}>
            关闭
          </button>
        </div>
        <div className="field">
          <label>简历名称</label>
          <input value={title} onChange={(event) => setTitle(event.target.value)} />
        </div>
        <div className="field">
          <label>简历正文（原稿）</label>
          <textarea
            rows={14}
            value={original}
            onChange={(event) => {
              setOriginal(event.target.value)
              setConfirming(false)
            }}
          />
        </div>

        <div className="warn-box">
          <strong>原稿只读的是「系统与模型」</strong>：分析、采纳、补充一律不会改它。
          你在这里改的是自己上传的素材，但这次改动<strong>不可恢复</strong>，且——
          已有的分析结果用的是<strong>发起时冻结的快照</strong>，不会跟着变；历史分析记录里的岗位快照同样不受影响。
        </div>

        <label className="check-row">
          <input
            type="checkbox"
            checked={resetDraft}
            onChange={(event) => setResetDraft(event.target.checked)}
          />
          <span>
            同时把<strong>修改稿</strong>重置为新原稿
            {draftDiffers
              ? `（当前修改稿约 ${draftChars} 字，和原文不同：不勾选就会保留它，且新分析仍然用修改稿）`
              : '（当前修改稿与原文一致，勾不勾都一样）'}
            。已保存的版本一律不动。
          </span>
        </label>

        {confirming && (
          <div className="confirm-inline">
            <div>
              将<strong>覆盖原稿正文</strong>（不可恢复）。已有的分析结果与历史快照不受影响。
            </div>
            <div className="row">
              <button className="danger" onClick={save} disabled={busy}>
                {busy ? '保存中…' : '确认覆盖并保存'}
              </button>
              <button onClick={() => setConfirming(false)} disabled={busy}>
                我再看看
              </button>
            </div>
          </div>
        )}

        {error && <div className="error-box">{error}</div>}
        {!confirming && (
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" onClick={submit} disabled={busy}>
              {busy ? '保存中…' : originalChanged ? '保存（需确认覆盖）' : '保存'}
            </button>
            <button onClick={onClose} disabled={busy}>
              取消
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
