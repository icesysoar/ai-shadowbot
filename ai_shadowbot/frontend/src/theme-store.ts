// 画布主题与配色（对齐 Alpha Node 视觉 + ai-shadowbot 状态语义）

// 节点分类配色（标题栏颜色）
export const CATEGORY_COLORS: Record<string, string> = {
  控制: '#4a9eff',
  鼠标: '#f59e0b',
  键盘: '#a371f7',
  应用: '#3fb950',
  系统: '#8b949e',
  浏览器: '#6C5CE7',
  Excel: '#217346',
  网络: '#e14e36',
  文件: '#d4a574',
}

export function categoryColor(category: string): string {
  return CATEGORY_COLORS[category] || '#8b949e'
}

// 执行状态配色（标题栏 / 主体）
export const STATUS_COLORS: Record<string, { title: string; body: string }> = {
  success: { title: '#1f6f43', body: '#14361f' },
  failed: { title: '#7d2b2b', body: '#3a1717' },
  running: { title: '#2c5282', body: '#16283d' },
  skipped: { title: '#4b4b4b', body: '#2a2a2a' },
}

export function statusTitleColor(status: string): string | undefined {
  return STATUS_COLORS[status]?.title
}

export function statusBodyColor(status: string): string | undefined {
  return STATUS_COLORS[status]?.body
}

export function statusBadge(status: string): string {
  switch (status) {
    case 'success':
      return '✓'
    case 'failed':
      return '✗'
    case 'running':
      return '●'
    case 'skipped':
      return '○'
    default:
      return ''
  }
}
