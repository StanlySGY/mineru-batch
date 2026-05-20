// 错误码 → 用户友好提示映射
const CODE_MAP: Record<string, string> = {
  MINERU_TIMEOUT: '解析超时，文件可能过大，建议增大超时时间',
  MINERU_CONNECT_FAIL: '无法连接到 MinerU 服务，请检查地址是否正确',
  MINERU_API_ERROR: 'MinerU 服务返回错误，请检查服务状态',
  DOC_CONVERT_FAIL: '文档转换失败，请确认 LibreOffice 已安装',
  DOC_CONVERT_TIMEOUT: '文档转换超时(120s)，文件可能过大',
  PDF_NOT_GENERATED: 'PDF 转换后文件未生成，请重试',
  FILE_TOO_LARGE: '文件超过大小限制',
  UNSUPPORTED_TYPE: '不支持的文件类型',
  NO_AVAILABLE_NODE: '没有可用的 MinerU 节点，请在设置中配置',
  TASK_CANCELLED: '任务已取消',
  TASK_TIMEOUT: '任务超时，建议增大超时时间后重试',
  NO_CONTENT_IN_RESULT: 'MinerU 返回结果异常，未找到解析内容',
  WEBHOOK_FAILED: 'Webhook 推送失败（不影响解析结果）',
}

// 错误码 → 修复建议映射
const SUGGESTION_MAP: Record<string, string> = {
  MINERU_TIMEOUT: '建议：增大超时时间或检查 MinerU 服务负载',
  MINERU_CONNECT_FAIL: '建议：检查 MinerU 服务地址是否正确，网络是否可达',
  MINERU_API_ERROR: '建议：检查 MinerU 服务状态，确认 API 版本兼容',
  DOC_CONVERT_FAIL: '建议：确认 LibreOffice 已安装（apt install libreoffice）',
  DOC_CONVERT_TIMEOUT: '建议：文档文件可能过大，尝试拆分后重新上传',
  PDF_NOT_GENERATED: '建议：检查 LibreOffice 是否正常工作，重试任务',
  FILE_TOO_LARGE: '建议：压缩文件或拆分为多个小文件',
  UNSUPPORTED_TYPE: '建议：仅支持 PDF/图片/Word/PPT/Excel 格式',
  NO_AVAILABLE_NODE: '建议：前往设置页配置 MinerU 节点',
  TASK_TIMEOUT: '建议：增大超时时间后重试',
  NO_CONTENT_IN_RESULT: '建议：检查文件内容是否可解析，尝试切换解析场景',
}

// 兼容旧格式的正则映射
const LEGACY_MAP: [RegExp, string][] = [
  [/MinerU API error (\d+)/, 'MinerU 服务返回错误 (HTTP $1)'],
  [/连接 MinerU 失败/, '无法连接到 MinerU 服务，请检查地址是否正确'],
  [/调用 MinerU 超时/, '解析超时，文件可能过大，建议增大超时时间'],
  [/LibreOffice exit/, '文档转换失败，请确认 LibreOffice 已安装'],
  [/LibreOffice 转换超时/, '文档转换超时(120s)，文件可能过大'],
  [/文档转 PDF 失败/, '文档转 PDF 失败，请检查文件是否损坏'],
  [/MinerU 返回结果中未找到 md_content/, 'MinerU 返回结果异常，未找到解析内容'],
  [/PDF 文件未生成/, 'PDF 转换后文件未生成，请重试'],
  [/任务已取消/, '任务已取消'],
  [/没有可用的 MinerU 服务节点/, '没有可用的 MinerU 节点，请在设置中配置'],
  [/不支持的文件类型/, '不支持的文件类型'],
  [/超过大小限制/, '文件超过大小限制'],
]

function extractCode(msg: string): string | null {
  if (!msg || !msg.startsWith('[')) return null
  const idx = msg.indexOf(']')
  if (idx <= 0) return null
  return msg.slice(1, idx)
}

export function translateError(msg: string): string {
  if (!msg) return '未知错误'

  // 优先匹配 [ERROR_CODE] 格式
  const code = extractCode(msg)
  if (code && CODE_MAP[code]) {
    return CODE_MAP[code]
  }

  // 兼容旧格式
  for (const [pattern, translation] of LEGACY_MAP) {
    if (pattern.test(msg)) return msg.replace(pattern, translation)
  }

  if (msg.length > 200) return msg.slice(0, 200) + '...'
  return msg
}

export function getErrorSuggestion(msg: string): string | null {
  if (!msg) return null

  const code = extractCode(msg)
  if (code && SUGGESTION_MAP[code]) {
    return SUGGESTION_MAP[code]
  }

  // 兼容旧格式
  for (const [codeKey, suggestion] of Object.entries(SUGGESTION_MAP)) {
    const key = codeKey.toLowerCase().replace(/_/g, ' ')
    if (msg.toLowerCase().includes(key)) return suggestion
  }

  return null
}
