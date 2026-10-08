import { useState } from 'react'
import { errorMessage } from '../api'
import type { AnalysisItem, Supplement } from '../types'

interface Props {
  item: AnalysisItem
  onClose: () => void
  /** 调后端 /api/supplement：只润色，不写进修改稿 */
  onPolish: (text: string) => Promise<Supplement>
  /** 采纳 / 忽略这次补充 */
  onDecide: (supplementId: number, decision: '采纳' | '忽略') => Promise<void>
}

/**
 * 补充「未体现 / 需要补充确认」条目的三步弹窗：
 * 输入真实经历 → AI 只做措辞润色 → 左右对比后采纳或忽略。
 */
export default function SupplementModal({ item, onClose, onPolish, onDecide }: Props) {
  const [step, setStep] = useState<'input' | 'review'>('input')
  const [text, setText] = useState(item.supplement?.user_input ?? '')
  const [supplement, setSupplement] = useState<Supplement | null>(
    item.supplement && item.supplement.decision === '未处理' ? item.supplement : null,
  )
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    if (!text.trim()) {
      setError('请先写下你的真实经历，哪怕只有一两句话。')
      return
    }
    setBusy('polish')
    setError('')
    try {
      const result = await onPolish(text.trim())
      setSupplement(result)
      setStep('review')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy('')
    }
  }

  async function decide(decision: '采纳' | '忽略') {
    if (!supplement) return
    setBusy(decision)
    setError('')
    try {
      await onDecide(supplement.id, decision)
      onClose()
    } catch (err) {
      setError(errorMessage(err))
      setBusy('')
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal">
        <div className="row between">
          <h3>请补充你在「{item.requirement_quote}」方面的实际经历</h3>
          <button className="ghost" onClick={onClose} disabled={busy !== ''}>
            关闭
          </button>
        </div>

        {item.confirmation_question && step === 'input' && (
          <div className="warn-box">需要确认：{item.confirmation_question}</div>
        )}
        {error && <div className="error-box">{error}</div>}

        {step === 'input' ? (
          <>
            <p className="muted">
              请描述你的真实经历，AI 会帮你优化表达，但不会编造内容（不加公司名／项目名／数字／技术栈）。
              <br />
              只写你确实做过的事；没写进去的内容，AI 不会替你补。
            </p>
            <textarea
              rows={7}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="例如：在实验室项目里我负责过部署，写了一个脚本把服务发到服务器上，后面又改了几次"
              autoFocus
            />
            <div className="row" style={{ marginTop: 12 }}>
              <button className="primary" onClick={submit} disabled={busy !== ''}>
                {busy === 'polish' ? 'AI 润色中…' : '提交给 AI 润色'}
              </button>
              <button onClick={onClose} disabled={busy !== ''}>
                取消
              </button>
            </div>
          </>
        ) : (
          <>
            {supplement && (
              <>
                <div className="compare">
                  <div>
                    <div className="muted">你的原文</div>
                    <div className="quote">{supplement.user_input}</div>
                  </div>
                  <div>
                    <div className="muted">AI 润色后（只改措辞，不新增事实）</div>
                    <div className="quote suggested">{supplement.polished_text}</div>
                  </div>
                </div>
                {supplement.polish_reason && (
                  <div className="muted">理由：{supplement.polish_reason}</div>
                )}
                <p className="muted">
                  采纳后这段内容会写进<strong>修改稿</strong>（预计放在「{supplement.section}」），
                  原稿依旧保持只读；重复采纳不会重复插入。
                </p>
                <div className="row">
                  <button
                    onClick={() => {
                      setStep('input')
                      setError('')
                    }}
                    disabled={busy !== ''}
                  >
                    重新输入
                  </button>
                  <button className="primary" onClick={() => decide('采纳')} disabled={busy !== ''}>
                    {busy === '采纳' ? '写入中…' : '采纳'}
                  </button>
                  <button onClick={() => decide('忽略')} disabled={busy !== ''}>
                    忽略
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
