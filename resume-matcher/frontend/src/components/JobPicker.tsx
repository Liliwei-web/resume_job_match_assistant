import { useEffect, useRef, useState } from 'react'
import type { Job } from '../types'

interface Props {
  jobs: Job[]
  value: number | ''
  /** 按简历标题预选出来的岗位：选中它、以及在列表里都能看到绿色的「匹配」标记。 */
  suggestedId: number | ''
  onChange: (id: number | '') => void
  disabled?: boolean
}

interface Row {
  id: number | ''
  title: string
}

const PLACEHOLDER: Row = { id: '', title: '请选择目标岗位' }

/**
 * 目标岗位下拉。
 *
 * 用自定义列表而不是原生 <select>：原生 option 里放不下徽标，也没法可靠上色，
 * 而「哪个岗位是按简历标题预选的」需要在下拉列表里就能一眼看见。
 * 键盘：Enter/空格/↓ 展开，↑↓ 移动，Enter 选中，Esc 收起。
 */
export default function JobPicker({ jobs, value, suggestedId, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement | null>(null)

  const rows: Row[] = [PLACEHOLDER, ...jobs.map((job) => ({ id: job.id, title: job.title }))]
  const selected = rows.find((row) => row.id === value) ?? PLACEHOLDER
  const matched = value !== '' && value === suggestedId

  // 展开时把高亮停在当前选中项上，键盘操作从当前位置开始。
  useEffect(() => {
    if (!open) return
    const index = rows.findIndex((row) => row.id === value)
    setActive(index >= 0 ? index : 0)
    // rows 每次渲染都是新数组，这里只依赖展开状态与当前值。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, value, jobs.length])

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  function pick(id: number | '') {
    onChange(id)
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (disabled) return
    if (!open) {
      if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
        event.preventDefault()
        setOpen(true)
      }
      return
    }
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((index) => Math.min(index + 1, rows.length - 1))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((index) => Math.max(index - 1, 0))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      pick(rows[active]?.id ?? '')
      return
    }
    if (event.key === 'Tab') setOpen(false)
  }

  return (
    <div className={`picker${open ? ' is-open' : ''}`} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        id="job-picker"
        className="picker-toggle"
        onClick={() => setOpen((current) => !current)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="目标岗位"
      >
        <span className={`picker-value${selected.id === '' ? ' is-placeholder' : ''}`}>
          {selected.title}
        </span>
        {matched && (
          <span className="match-chip" title="已按简历标题预选，可随时切换">
            匹配
          </span>
        )}
        <span className="picker-caret" aria-hidden="true">
          ▾
        </span>
      </button>

      {open && (
        <div className="picker-menu" role="listbox" aria-label="目标岗位">
          {rows.map((row, index) => (
            <button
              type="button"
              key={row.id === '' ? 'placeholder' : row.id}
              data-job-id={row.id}
              role="option"
              aria-selected={row.id === value}
              className={`picker-option${index === active ? ' is-active' : ''}${
                row.id === value ? ' is-selected' : ''
              }`}
              onMouseEnter={() => setActive(index)}
              onClick={() => pick(row.id)}
            >
              <span className="picker-option-title">{row.title}</span>
              {row.id !== '' && row.id === suggestedId && (
                <span className="match-chip" title="已按简历标题预选">
                  匹配
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
