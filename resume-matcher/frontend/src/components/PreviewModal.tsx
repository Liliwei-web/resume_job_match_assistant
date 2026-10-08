import { useEffect, useState } from 'react'
import { renderMarkdown } from '../markdown'
import { IconExpand } from './icons'

export interface PreviewTab {
  key: string
  label: string
  content: string
}

interface Props {
  title: string
  tabs: PreviewTab[]
  /** 打开时就放大字号（工作台那个「放大」按钮走这条路）。 */
  initialBig?: boolean
  onClose: () => void
}

/**
 * 只读的 Markdown 预览弹窗：简历（原稿 / 修改稿）、历史版本、修改稿放大共用一份。
 *
 * 刻意只有「看」和「切页签」两个能力：预览里不出现任何写操作，
 * 这样点开任何一份内容都不用先担心会不会改到东西。
 */
export default function PreviewModal({ title, tabs, initialBig = false, onClose }: Props) {
  const [active, setActive] = useState(0)
  const [big, setBig] = useState(initialBig)
  const tab = tabs[Math.min(active, Math.max(tabs.length - 1, 0))]
  const text = tab?.content ?? ''
  const chars = text.replace(/\s/g, '').length

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal wide">
        <div className="row between">
          <h3>{title}</h3>
          <div className="row">
            <button
              className="ghost zoom-btn"
              aria-pressed={big}
              onClick={() => setBig((current) => !current)}
            >
              <IconExpand />
              {big ? '还原字号' : '放大字号'}
            </button>
            <button className="ghost" onClick={onClose}>
              关闭（Esc）
            </button>
          </div>
        </div>
        {tabs.length > 1 && (
          <div className="segmented" role="tablist" aria-label="预览内容">
            {tabs.map((item, index) => (
              <button
                key={item.key}
                className={`seg-btn ${index === active ? 'active' : ''}`}
                role="tab"
                aria-selected={index === active}
                onClick={() => setActive(index)}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
        <p className="muted">只读预览 · 约 {chars} 字 · 这里不会改动任何数据</p>
        <div className={`preview-body${big ? ' is-big' : ''}`}>
          {text.trim() ? (
            <div
              className="preview plain"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
            />
          ) : (
            <div className="empty">这一份还没有内容。</div>
          )}
        </div>
      </div>
    </div>
  )
}
