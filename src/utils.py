"""工具函数模块 —— 时间格式化、文件名安全化、文本截断等"""

from datetime import datetime, timezone, timedelta
import re


def format_timestamp(iso_string: str) -> str:
    """将 ISO 8601 时间戳转换为可读的本地时间字符串
    例如: "2026-03-08T16:48:49.264453Z" → "2026-03-08 16:48"
    失败时返回 "未知时间"
    """
    if not iso_string:
        return "未知时间"
    try:
        # 尝试解析 ISO 8601 格式
        # 处理带 Z 后缀的情况
        ts = iso_string.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        # 转换为本地时间
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        # 如果解析失败，尝试截取前16个字符
        if len(iso_string) >= 16:
            return iso_string[:16].replace("T", " ")
        return iso_string


def safe_truncate(text: str, max_len: int = 150) -> str:
    """安全截断文本，超出长度加省略号"""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def html_escape(text: str) -> str:
    """转义 HTML 特殊字符"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
    )


def extract_date(iso_string: str) -> str:
    """从 ISO 时间戳提取日期部分
    例如: "2026-03-08T16:48:49.264453Z" → "2026-03-08"
    """
    if not iso_string:
        return ""
    if len(iso_string) >= 10:
        return iso_string[:10]
    return iso_string


def sanitize_filename(name: str, max_len: int = 60) -> str:
    """安全化文件名 —— 替换所有非法字符"""
    import re
    # Windows/macOS/Linux 通用非法字符
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    if len(name) > max_len:
        name = name[:max_len]
    return name or "untitled"
