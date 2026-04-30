const DOC_EXTS = ['.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx']

export function isDocFile(name: string): boolean {
  const dot = name.lastIndexOf('.')
  if (dot < 0) return false
  return DOC_EXTS.includes(name.substring(dot).toLowerCase())
}

export const ALLOWED_EXTENSIONS = '.pdf,.png,.jpg,.jpeg,.bmp,.tiff,.webp,.doc,.docx,.ppt,.pptx,.xls,.xlsx'

export const MAX_FILE_SIZE_MB = 200
