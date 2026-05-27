import { describe, expect, it } from 'vitest'
import { formatSize, statusTag } from '../src/utils/format'

describe('format utils', () => {
  it('formats byte sizes with expected units', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(2 * 1024 * 1024)).toBe('2.0 MB')
    expect(formatSize(3 * 1024 * 1024 * 1024)).toBe('3.0 GB')
  })

  it('maps task statuses to Element Plus tag metadata', () => {
    expect(statusTag.pending).toEqual({ type: 'info', label: '等待中' })
    expect(statusTag.processing).toEqual({ type: 'warning', label: '处理中' })
    expect(statusTag.completed).toEqual({ type: 'success', label: '已完成' })
    expect(statusTag.failed).toEqual({ type: 'danger', label: '失败' })
  })
})
