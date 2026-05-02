export function formatTime(iso: string | null) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}

export function formatSize(bytes: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

export const statusTag: Record<string, { type: 'info' | 'warning' | 'success' | 'danger'; label: string }> = {
  pending: { type: 'info', label: '等待中' },
  processing: { type: 'warning', label: '处理中' },
  completed: { type: 'success', label: '已完成' },
  failed: { type: 'danger', label: '失败' },
}
