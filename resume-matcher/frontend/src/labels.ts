/** 分析任务状态在界面上的中文说法（工作台、历史记录、回放页共用）。 */
export const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '分析中',
  succeeded: '已完成',
  failed: '失败',
}

export const statusLabel = (status: string) => STATUS_LABELS[status] || status
