const ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => ESCAPES[char] ?? char)
}

function inline(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
}

/** Minimal, escape-first markdown renderer (headings, lists, rules, paragraphs, bold). */
export function renderMarkdown(source: string): string {
  const lines = (source || '').split(/\r?\n/)
  const html: string[] = []
  let inList = false

  const closeList = () => {
    if (inList) {
      html.push('</ul>')
      inList = false
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (!line.trim()) {
      closeList()
      continue
    }
    // 分隔线：`---` 不属于列表（第一个 - 后面没有空格），不单独处理会渲染成一段字面文本。
    if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      closeList()
      html.push('<hr />')
      continue
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      continue
    }
    const bullet = /^[-*]\s+(.*)$/.exec(line.trim())
    if (bullet) {
      if (!inList) {
        html.push('<ul>')
        inList = true
      }
      html.push(`<li>${inline(bullet[1])}</li>`)
      continue
    }
    closeList()
    html.push(`<p>${inline(line)}</p>`)
  }

  closeList()
  return html.join('\n')
}

/** 触发浏览器下载（内容来自导出接口返回的 Markdown）。 */
export function downloadMarkdown(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
