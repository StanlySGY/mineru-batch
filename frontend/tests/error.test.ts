import { describe, expect, it } from 'vitest'
import { getErrorSuggestion, translateError } from '../src/utils/error'

describe('error utils', () => {
  it('translates structured error codes', () => {
    expect(translateError('[MINERU_TIMEOUT] timeout')).toBe('解析超时，文件可能过大，建议增大超时时间')
    expect(translateError('[NO_AVAILABLE_NODE] none')).toBe('没有可用的 MinerU 节点，请在设置中配置')
  })

  it('keeps legacy error messages user friendly', () => {
    expect(translateError('MinerU API error 500')).toBe('MinerU 服务返回错误 (HTTP 500)')
    expect(translateError('调用 MinerU 超时')).toBe('解析超时，文件可能过大，建议增大超时时间')
  })

  it('returns actionable suggestions when available', () => {
    expect(getErrorSuggestion('[DOC_CONVERT_FAIL] failed')).toBe('建议：确认 LibreOffice 已安装（apt install libreoffice）')
    expect(getErrorSuggestion('unknown failure')).toBeNull()
  })
})
