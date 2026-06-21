"""Markdown 导出渲染器 —— 将对话渲染为精美的 Markdown 文档

输出格式：
- YAML frontmatter（Obsidian / VS Code 兼容）
- 清晰的一问一答结构
- Thinking 用 <details> 折叠
- 工具调用用 blockquote 展示
- 代码块带语言标记
"""

import json as _json

from .models import Conversation, ChatMessage, ContentBlock
from .utils import format_timestamp, extract_date


def export_conversation_md(conv: Conversation) -> str:
    """将单个对话导出为 Markdown 字符串"""
    lines = []

    # ── YAML frontmatter ──
    lines.append("---")
    lines.append(f'title: "{_escape_yaml(conv.name)}"')
    lines.append(f"created: {extract_date(conv.created_at)}")
    lines.append(f"updated: {extract_date(conv.updated_at)}")
    lines.append(f"messages: {conv.message_count}")
    lines.append("---")
    lines.append("")

    # ── 标题 ──
    lines.append(f"# {conv.name}")
    lines.append("")

    # ── 元信息 ──
    meta_parts = []
    if conv.created_at:
        meta_parts.append(f"**创建时间:** {format_timestamp(conv.created_at)}")
    if conv.updated_at:
        meta_parts.append(f"**最后活跃:** {format_timestamp(conv.updated_at)}")
    meta_parts.append(f"**消息数:** {conv.message_count}")
    lines.append("> " + " · ".join(meta_parts))
    lines.append("")

    # ── 摘要 ──
    if conv.summary:
        lines.append("---")
        lines.append("")
        lines.append("## 📋 对话摘要")
        lines.append("")
        lines.append(conv.summary.strip())
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── 消息列表 ──
    for i, msg in enumerate(conv.messages):
        role = "You" if msg.sender == "human" else "Claude"
        time_str = format_timestamp(msg.created_at) if msg.created_at else ""
        header = f"### {role}"
        if time_str:
            header += f" — {time_str}"
        lines.append(header)
        lines.append("")

        # 渲染内容块
        for block in msg.content_blocks:
            rendered = _render_block_md(block)
            if rendered:
                lines.append(rendered)
                lines.append("")

        # 无内容块时使用 text 字段
        if not msg.content_blocks and msg.text.strip():
            lines.append(msg.text.strip())
            lines.append("")

        # 消息分隔线（最后一条不加）
        if i < len(conv.messages) - 1:
            lines.append("---")
            lines.append("")

    # ── 页脚 ──
    lines.append("---")
    lines.append("")
    lines.append(f"*由 Claude 对话浏览器导出*")

    return "\n".join(lines)


def _render_block_md(block: ContentBlock) -> str:
    """将单个内容块渲染为 Markdown"""
    bt = block.type

    if bt == "text":
        return _md_text(block)
    elif bt == "thinking":
        return _md_thinking(block)
    elif bt == "tool_use":
        return _md_tool_use(block)
    elif bt == "tool_result":
        return _md_tool_result(block)
    elif bt == "code_block":
        return _md_code_block(block)
    elif bt == "json_block":
        raw = block.json_data or {}
        display = {k: v for k, v in raw.items()
                   if k not in ("type", "start_timestamp", "stop_timestamp", "flags")}
        if display:
            return f"```json\n{_json.dumps(display, ensure_ascii=False, indent=2)}\n```"
        return ""
    elif bt == "table":
        return _md_table(block)
    elif bt == "rich_content":
        return _md_rich_content(block)
    elif bt == "rich_link":
        return _md_rich_link(block)
    elif bt == "web_search_citation":
        return _md_citation(block)
    elif bt == "webpage_metadata":
        return _md_webpage_meta(block)
    elif bt == "knowledge":
        return _md_knowledge(block)
    elif bt == "local_resource":
        return _md_local_resource(block)
    elif bt == "flag":
        return _md_flag(block)
    elif bt == "application/vnd.ant.react":
        return _md_artifact(block)
    else:
        return _md_unknown(block)


# ═══════════════════════════════════════════
# 各类型 Markdown 渲染
# ═══════════════════════════════════════════

def _md_text(block: ContentBlock) -> str:
    text = (block.text or "").strip()
    return text if text else ""


def _md_thinking(block: ContentBlock) -> str:
    thinking = (block.thinking or "").strip()
    if not thinking:
        return "<details><summary>💭 思考过程</summary>\n\n*（无内容）*\n\n</details>"
    # 用 HTML details 标签实现折叠（Markdown 广泛支持）
    return f"<details><summary>💭 思考过程</summary>\n\n{thinking}\n\n</details>"


def _md_tool_use(block: ContentBlock) -> str:
    name = block.tool_name or "未知工具"
    msg = block.tool_message or ""
    tool_input = block.tool_input or {}

    lines = [f'> 🔧 **工具调用:** `{name}`']
    if msg:
        lines.append(f'> *{msg}*')
    if tool_input:
        formatted = _json.dumps(tool_input, ensure_ascii=False, indent=2)
        lines.append('>')
        lines.append('> ```json')
        for input_line in formatted.split('\n'):
            lines.append(f'> {input_line}')
        lines.append('> ```')
    return '\n'.join(lines)


def _md_tool_result(block: ContentBlock) -> str:
    name = block.tool_name or "工具"
    is_error = block.is_error

    lines = [f'> 📋 **{name} 结果**']
    if is_error:
        lines.append('> ⚠️ *错误*')

    # 递归渲染子内容
    for sub in block.tool_result_content:
        if isinstance(sub, ContentBlock):
            sub_md = _render_block_md(sub)
            if sub_md:
                # 子内容也缩进在 blockquote 中
                for sub_line in sub_md.split('\n'):
                    lines.append(f'> {sub_line}')

    return '\n'.join(lines)


def _md_code_block(block: ContentBlock) -> str:
    code = block.code or ""
    lang = block.language or ""
    return f"```{lang}\n{code}\n```"


def _md_table(block: ContentBlock) -> str:
    rows = block.table_data
    if not rows or not isinstance(rows, list) or len(rows) == 0:
        return ""

    lines = []
    # 表头
    header = rows[0]
    if isinstance(header, list):
        lines.append("| " + " | ".join(str(c) for c in header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        # 表体
        for row in rows[1:]:
            if isinstance(row, list):
                lines.append("| " + " | ".join(str(c) for c in row) + " |")

    return "\n".join(lines)


def _md_rich_content(block: ContentBlock) -> str:
    items = block.rich_content_items
    if not items:
        return ""
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        subtitles = item.get("subtitles", []) or []
        if title:
            lines.append(f"📌 **{title}**")
        for sub in subtitles:
            lines.append(f"  {sub}")
    return "\n".join(lines) if lines else ""


def _md_rich_link(block: ContentBlock) -> str:
    url = block.link_url or ""
    title = block.link_title or url
    desc = block.link_description or ""
    if desc:
        return f"[{title}]({url}) — {desc}"
    return f"[{title}]({url})"


def _md_citation(block: ContentBlock) -> str:
    url = block.citation_url or ""
    title = block.citation_title or url
    return f"🔗 [{title}]({url})"


def _md_webpage_meta(block: ContentBlock) -> str:
    domain = block.site_domain or ""
    site_name = block.site_name or domain
    return f"*来源: {site_name} ({domain})*"


def _md_knowledge(block: ContentBlock) -> str:
    title = block.knowledge_title or ""
    url = block.knowledge_url or ""
    text = block.knowledge_text or ""
    is_missing = block.is_missing
    missing_note = " 🔴 已失效" if is_missing else ""

    lines = []
    if url:
        lines.append(f"** [{title}]({url}){missing_note}**")
    else:
        lines.append(f"**{title}{missing_note}**")
    if text:
        # 截断过长文本
        if len(text) > 600:
            text = text[:600] + "…"
        lines.append(text)
    return "\n".join(lines)


def _md_local_resource(block: ContentBlock) -> str:
    file_name = block.file_name or block.file_path or "未知文件"
    mime_type = block.mime_type or ""
    return f"📄 **{file_name}** ({mime_type})"


def _md_flag(block: ContentBlock) -> str:
    text = block.flag_text or ""
    level = block.flag_level or "info"
    emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "🏷️")
    return f"{emoji} {text}"


def _md_artifact(block: ContentBlock) -> str:
    raw = block.raw_data or {}
    name = raw.get("identifier", raw.get("name", "交互组件"))
    return f"🧩 *交互组件: {name}（需在 Claude 网页版中查看）*"


def _md_unknown(block: ContentBlock) -> str:
    raw = block.raw_data or {}
    formatted = _json.dumps(raw, ensure_ascii=False, indent=2)
    return f"<details><summary>📦 未知内容块: {block.type}</summary>\n\n```json\n{formatted}\n```\n\n</details>"


# ═══════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════

def _escape_yaml(text: str) -> str:
    """转义 YAML 字符串中的特殊字符"""
    return text.replace('"', '\\"').replace('\n', ' ')
