const ERROR_MAP: [RegExp, string][] = [
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

export function translateError(msg: string): string {
  if (!msg) return '未知错误'
  for (const [pattern, translation] of ERROR_MAP) {
    if (pattern.test(msg)) return msg.replace(pattern, translation)
  }
  if (msg.length > 200) return msg.slice(0, 200) + '...'
  return msg
}
