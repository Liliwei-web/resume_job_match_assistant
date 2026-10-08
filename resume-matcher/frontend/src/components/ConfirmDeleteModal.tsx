interface Props {
  title: string
  /** 逐行说明将要删除什么，计数来自后端的 deletion-preview。 */
  lines: string[]
  warning?: string
  error?: string
  busy: '' | 'delete' | 'export'
  onCancel: () => void
  onConfirm: () => void
  /** 只在删简历时给：先按最新修改稿导出 Markdown，导出成功后再删除。 */
  exportLabel?: string
  onExportAndDelete?: () => void
}

/** 删除简历 / 岗位的二次确认弹窗。主按钮是红色危险操作，导出是可选的安全路径。 */
export default function ConfirmDeleteModal({
  title,
  lines,
  warning,
  error,
  busy,
  onCancel,
  onConfirm,
  exportLabel,
  onExportAndDelete,
}: Props) {
  const working = busy !== ''

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal" style={{ maxWidth: 520 }}>
        <div className="row between">
          <h3>{title}</h3>
          <button className="ghost" onClick={onCancel} disabled={working}>
            关闭
          </button>
        </div>

        {lines.map((line) => (
          <p className="muted" key={line}>
            {line}
          </p>
        ))}
        {warning && <div className="warn-box">{warning}</div>}
        {error && <div className="error-box">{error}</div>}

        <div className="row" style={{ marginTop: 12 }}>
          {onExportAndDelete && (
            <button onClick={onExportAndDelete} disabled={working}>
              {busy === 'export' ? '正在导出…' : (exportLabel ?? '先导出再删')}
            </button>
          )}
          <button className="danger" onClick={onConfirm} disabled={working}>
            {busy === 'delete' ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}
