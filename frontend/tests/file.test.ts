import { describe, expect, it } from 'vitest'
import { isDocFile, ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB } from '../src/utils/file'

describe('file utils', () => {
  it('detects Office documents case-insensitively', () => {
    expect(isDocFile('report.DOCX')).toBe(true)
    expect(isDocFile('slides.ppt')).toBe(true)
    expect(isDocFile('sheet.XLSX')).toBe(true)
  })

  it('does not classify non-document files as Office documents', () => {
    expect(isDocFile('manual.pdf')).toBe(false)
    expect(isDocFile('archive')).toBe(false)
    expect(isDocFile('.docx')).toBe(true)
  })

  it('keeps upload constraints aligned with supported formats', () => {
    expect(ALLOWED_EXTENSIONS).toContain('.pdf')
    expect(ALLOWED_EXTENSIONS).toContain('.docx')
    expect(MAX_FILE_SIZE_MB).toBe(200)
  })
})
