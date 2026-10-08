import { useState } from 'react'
import { renderMarkdown } from '../markdown'
import { IconPlus } from './icons'
import type { AnalysisDetail, AnalysisItem } from '../types'

type Decision = '采纳' | '忽略' | '未处理'

interface Props {
  analysis: AnalysisDetail
  /**
   * 只读回放：历史记录页打开的是当初那次分析的结果，采纳/补充都会写到「当前修改稿」上，
   * 从历史页面里操作会造成「改了今天的稿、却以为改的是当时那份」的歧义，所以一律隐藏。
   */
  readOnly?: boolean
  busy?: string
  /** 被跳转命中的元素 id，命中时闪一下。 */
  flash?: string
  onSupplement?: (item: AnalysisItem) => void
  onDecide?: (suggestionId: number, decision: Decision) => void
  onRetry?: () => void
  /** 工作台里是编号的「2. / 3.」两节；回放页没有编号。 */
  numbered?: boolean
}

export function StatusPill({ status }: { status: string }) {
  const cls = status === '已体现' ? 'shown' : status === '未体现' ? 'absent' : 'check'
  return <span className={`pill ${cls}`}>{status}</span>
}

/**
 * 「要求—证据—判断」+「逐条修改建议」两节。
 *
 * 抽成组件是因为工作台和「分析记录回放页」要显示同一份结果：各写一遍迟早会漂移，
 * 一边改了另一边没改，同一个分析在两处长得不一样。
 */
export default function AnalysisResult({
  analysis,
  readOnly = false,
  busy = '',
  flash = '',
  onSupplement,
  onDecide,
  onRetry,
  numbered = true,
}: Props) {
  // 建议文本默认渲染 Markdown（加粗、列表直接看得见）；需要核对原文时才切到源码。
  const [sourceFor, setSourceFor] = useState<number | null>(null)

  const running = analysis.status === 'pending' || analysis.status === 'running'
  // 还需要用户补充经历的条目：未体现 / 需要补充确认，且补充尚未被采纳。
  const pendingSupplement = analysis.items.filter(
    (row) => row.match_status !== '已体现' && row.supplement_state !== '已补充',
  ).length

  const itemTitle = numbered ? '2. 要求—证据—判断' : '要求—证据—判断'
  const suggestionTitle = numbered ? '3. 逐条修改建议' : '逐条修改建议'

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>{itemTitle}</h2>
          {!readOnly && pendingSupplement > 0 && (
            <span className="pill pending">待补充 {pendingSupplement} 条</span>
          )}
        </div>
        {analysis.status === 'pending' && (
          <div className="info-box">
            <span className="spinner" />
            分析任务已创建，等待模型处理…
          </div>
        )}
        {analysis.status === 'running' && (
          <div className="info-box">
            <span className="spinner" />
            模型正在分析（任务 #{analysis.id}）…
          </div>
        )}
        {analysis.status === 'failed' && (
          <div className="error-box">
            分析失败：{analysis.error_message || '未知错误'}
            {onRetry && (
              <>
                {'\n'}
                <button className="secondary" onClick={onRetry} disabled={busy === 'analyze'}>
                  重试
                </button>
              </>
            )}
          </div>
        )}
        {analysis.status === 'succeeded' && (
          <>
            <p className="muted">
              任务 #{analysis.id} · 岗位：{analysis.job_title} · 模型：
              {analysis.model_name || '未知'} ·{' '}
              {new Date(analysis.finished_at || analysis.created_at).toLocaleString()}
            </p>
            {analysis.items.length === 0 ? (
              <div className="empty">模型没有返回可对应到岗位要求的条目，请重试。</div>
            ) : (
              <div className="analysis-list">
                {analysis.items.map((item, index) => (
                  <article
                    id={`item-${item.id}`}
                    key={item.id}
                    className={`analysis-row ${flash === `item-${item.id}` ? 'flash' : ''}`}
                  >
                    <div className="analysis-row-top">
                      <StatusPill status={item.match_status} />
                      <span className="index">
                        {index + 1} / {analysis.items.length}
                      </span>
                      <span className="spacer" />
                    </div>
                    <div className="pair-grid">
                      <div className="pair-cell">
                        <div className="pair-label">岗位要求（原文）</div>
                        <p>{item.requirement_quote}</p>
                      </div>
                      <div className={`pair-cell ${item.evidence_quote ? '' : 'is-empty'}`}>
                        <div className="pair-label">简历对应原文</div>
                        <p>{item.evidence_quote || '（原文中无对应内容）'}</p>
                      </div>
                    </div>
                    <p className="analysis-reason">{item.reason}</p>
                    {item.confirmation_question && (
                      <div className="callout">需要确认：{item.confirmation_question}</div>
                    )}
                    {!readOnly && item.match_status !== '已体现' && (
                      <div className="analysis-actions">
                        <button
                          className={`supplement-btn${item.supplement_state === '已补充' ? ' is-done' : ''}`}
                          onClick={() => onSupplement?.(item)}
                          disabled={item.supplement_state === '已补充' || running}
                        >
                          {item.supplement_state === '已补充' ? (
                            '已补充'
                          ) : (
                            <>
                              <IconPlus />
                              {item.supplement_state === '待处理' ? '补充（待采纳）' : '补充这段经历'}
                            </>
                          )}
                        </button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="card">
        <h2>{suggestionTitle}</h2>
        {analysis.status !== 'succeeded' ? (
          <div className="empty">分析完成后，这里会列出可采纳或忽略的修改建议。</div>
        ) : analysis.suggestions.length === 0 ? (
          <div className="empty">这次分析没有产生修改建议。</div>
        ) : (
          analysis.suggestions.map((suggestion) => (
            <div
              id={`suggestion-${suggestion.id}`}
              key={suggestion.id}
              className={`suggestion ${suggestion.decision === '采纳' ? 'accepted' : ''} ${
                suggestion.decision === '忽略' ? 'ignored' : ''
              } ${flash === `suggestion-${suggestion.id}` ? 'flash' : ''}`}
            >
              <div className="row between">
                <strong>
                  {suggestion.is_question
                    ? '需要补充的信息'
                    : `改写建议 · ${suggestion.section || '其他'}`}
                </strong>
                <span className="decision">当前：{suggestion.decision}</span>
              </div>
              {suggestion.original_passage && (
                <>
                  <div className="muted">原文</div>
                  <div className="quote">{suggestion.original_passage}</div>
                </>
              )}
              {suggestion.suggested_passage && (
                <>
                  <div className="row between">
                    <div className="muted">
                      {sourceFor === suggestion.id
                        ? '建议文本（Markdown 源码）'
                        : '建议文本（Markdown 已渲染）'}
                    </div>
                    <button
                      className="ghost source-toggle"
                      aria-pressed={sourceFor === suggestion.id}
                      onClick={() =>
                        setSourceFor((current) =>
                          current === suggestion.id ? null : suggestion.id,
                        )
                      }
                    >
                      {sourceFor === suggestion.id ? '隐藏源码' : '查看源码'}
                    </button>
                  </div>
                  {sourceFor === suggestion.id ? (
                    <div className="quote">{suggestion.suggested_passage}</div>
                  ) : (
                    <div
                      className="quote rendered"
                      dangerouslySetInnerHTML={{
                        __html: renderMarkdown(suggestion.suggested_passage),
                      }}
                    />
                  )}
                </>
              )}
              <div className="muted">理由：{suggestion.rewrite_reason}</div>
              {!readOnly && (
                <div className="row" style={{ marginTop: 8 }}>
                  <button
                    className="primary"
                    onClick={() => onDecide?.(suggestion.id, '采纳')}
                    disabled={busy === `s${suggestion.id}` || suggestion.decision === '采纳'}
                  >
                    采纳
                  </button>
                  <button
                    className="secondary"
                    onClick={() => onDecide?.(suggestion.id, '忽略')}
                    disabled={busy === `s${suggestion.id}` || suggestion.decision === '忽略'}
                  >
                    忽略
                  </button>
                  {suggestion.decision !== '未处理' && (
                    <button
                      className="ghost"
                      onClick={() => onDecide?.(suggestion.id, '未处理')}
                      disabled={busy === `s${suggestion.id}`}
                    >
                      撤销
                    </button>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </>
  )
}
