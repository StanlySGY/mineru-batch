"""统一错误码体系 — 错误码前缀格式: [ERROR_CODE] message"""


class ErrorCode:
    # MinerU 相关
    MINERU_TIMEOUT = "MINERU_TIMEOUT"
    MINERU_CONNECT_FAIL = "MINERU_CONNECT_FAIL"
    MINERU_API_ERROR = "MINERU_API_ERROR"
    NO_CONTENT_IN_RESULT = "NO_CONTENT_IN_RESULT"

    # 文档转换
    DOC_CONVERT_FAIL = "DOC_CONVERT_FAIL"
    DOC_CONVERT_TIMEOUT = "DOC_CONVERT_TIMEOUT"
    PDF_NOT_GENERATED = "PDF_NOT_GENERATED"

    # 文件相关
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"

    # 节点相关
    NO_AVAILABLE_NODE = "NO_AVAILABLE_NODE"

    # 任务相关
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_TIMEOUT = "TASK_TIMEOUT"

    # Webhook
    WEBHOOK_FAILED = "WEBHOOK_FAILED"


def with_code(code: str, message: str) -> str:
    """给错误信息加上错误码前缀"""
    return f"[{code}] {message}"


def extract_code(error_message: str) -> str | None:
    """从错误信息中提取错误码"""
    if not error_message:
        return None
    if error_message.startswith("[") and "]" in error_message:
        return error_message[1:error_message.index("]")]
    return None


def strip_code(error_message: str) -> str:
    """移除错误信息中的错误码前缀"""
    if not error_message:
        return ""
    if error_message.startswith("[") and "]" in error_message:
        return error_message[error_message.index("]") + 1:].strip()
    return error_message


# 前端友好建议映射
ERROR_SUGGESTIONS: dict[str, str] = {
    ErrorCode.MINERU_TIMEOUT: "建议：增大超时时间或检查 MinerU 服务负载",
    ErrorCode.MINERU_CONNECT_FAIL: "建议：检查 MinerU 服务地址是否正确，网络是否可达",
    ErrorCode.MINERU_API_ERROR: "建议：检查 MinerU 服务状态，确认 API 版本兼容",
    ErrorCode.DOC_CONVERT_FAIL: "建议：确认 LibreOffice 已安装（apt install libreoffice）",
    ErrorCode.DOC_CONVERT_TIMEOUT: "建议：文档文件可能过大，尝试拆分后重新上传",
    ErrorCode.PDF_NOT_GENERATED: "建议：检查 LibreOffice 是否正常工作，重试任务",
    ErrorCode.FILE_TOO_LARGE: "建议：压缩文件或拆分为多个小文件",
    ErrorCode.UNSUPPORTED_TYPE: "建议：仅支持 PDF/图片/Word/PPT/Excel 格式",
    ErrorCode.NO_AVAILABLE_NODE: "建议：前往设置页配置 MinerU 节点",
    ErrorCode.TASK_CANCELLED: "任务已被用户取消",
    ErrorCode.TASK_TIMEOUT: "建议：增大超时时间后重试",
    ErrorCode.NO_CONTENT_IN_RESULT: "建议：检查文件内容是否可解析，尝试切换解析场景",
    ErrorCode.WEBHOOK_FAILED: "Webhook 推送失败，不影响解析结果",
}


def get_suggestion(error_message: str) -> str | None:
    """根据错误信息获取修复建议"""
    code = extract_code(error_message)
    if code:
        return ERROR_SUGGESTIONS.get(code)
    # 兼容无错误码的旧格式
    for key, suggestion in ERROR_SUGGESTIONS.items():
        if key.lower().replace("_", " ") in error_message.lower():
            return suggestion
    return None
