"""内容块 HTML 渲染器 —— 将 15 种内容块类型渲染为 HTML 片段

输出策略:
- text/thinking 等 Markdown 内容: 输出原始文本，由前端 marked.js 渲染
- 结构化内容 (tool_use, tool_result, code_block 等): 输出完整 HTML
- 嵌套渲染: tool_result 内的 knowledge/webpage_metadata/local_resource 递归处理
- CC 格式支持: tool_result 的纯文本和文件信息渲染

HTML 片段由前端插入页面后，再由 marked.js 和 highlight.js 进行最终渲染。
"""

import json as json_mod
from typing import Optional

from .models import ContentBlock
from .utils import html_escape, safe_truncate

# ── 工具图标映射（模块级常量）──
TOOL_ICON_MAP = {
    "globe": "🌐", "search": "🔍", "file": "📄",
    "folder": "📁", "code": "💻", "terminal": "🖥️", "image": "🖼️",
}

# ── 常见工具的人类可读名称 ──
TOOL_DISPLAY_NAMES = {
    "Read": "读取文件",
    "Write": "写入文件",
    "Edit": "编辑文件",
    "Bash": "执行命令",
    "PowerShell": "执行 PowerShell",
    "Glob": "搜索文件",
    "Grep": "搜索内容",
    "WebSearch": "网页搜索",
    "WebFetch": "获取网页",
    "Agent": "启动子代理",
    "Skill": "调用技能",
    "TaskCreate": "创建任务",
    "TaskUpdate": "更新任务",
    "AskUserQuestion": "询问用户",
    "Monitor": "监控进程",
    "CronCreate": "创建定时任务",
    "NotebookEdit": "编辑 Notebook",
    "DesignSync": "设计同步",
    "EnterPlanMode": "进入计划模式",
    "ExitPlanMode": "退出计划模式",
}


def _escape_json(obj, indent: int = 2) -> str:
    """格式化 JSON 并转义 HTML"""
    try:
        formatted = json_mod.dumps(obj, ensure_ascii=False, indent=indent)
        return html_escape(formatted)
    except (TypeError, ValueError):
        return html_escape(str(obj))


def _render_tool_result_sub_blocks(blocks: list) -> str:
    """递归渲染 tool_result 内嵌的子内容块"""
    if not blocks:
        return ""
    parts = []
    for block in blocks:
        if not isinstance(block, ContentBlock):
            continue
        rendered = render_content_block(block)
        if rendered:
            parts.append(rendered)
    return "\n".join(parts)


def render_content_block(block: ContentBlock) -> str:
    """将单个内容块渲染为 HTML 片段

    这是核心分发函数 —— 根据 block.type 调用对应的渲染函数
    """
    bt = block.type

    if bt == "text":
        return _render_text(block)
    elif bt == "thinking":
        return _render_thinking(block)
    elif bt == "tool_use":
        return _render_tool_use(block)
    elif bt == "tool_result":
        return _render_tool_result(block)
    elif bt == "code_block":
        return _render_code_block(block)
    elif bt == "json_block":
        return _render_json_block(block)
    elif bt == "table":
        return _render_table(block)
    elif bt == "rich_content":
        return _render_rich_content(block)
    elif bt == "rich_link":
        return _render_rich_link(block)
    elif bt == "web_search_citation":
        return _render_web_search_citation(block)
    elif bt == "webpage_metadata":
        return _render_webpage_metadata(block)
    elif bt == "knowledge":
        return _render_knowledge(block)
    elif bt == "local_resource":
        return _render_local_resource(block)
    elif bt == "flag":
        return _render_flag(block)
    elif bt == "application/vnd.ant.react":
        return _render_artifact(block)
    elif bt == "meta_event":
        return _render_meta_event(block)
    else:
        return _render_unknown(block)


# ═══════════════════════════════════════════
# 各类型渲染函数
# ═══════════════════════════════════════════

def _render_text(block: ContentBlock) -> str:
    """文本块 —— 输出原始 Markdown，前端 marked.js 渲染"""
    text = block.text or ""
    if not text.strip():
        return ""
    return f'<div class="text-block">{html_escape(text)}</div>'


def _render_thinking(block: ContentBlock) -> str:
    """思考块 —— 默认折叠的 <details> 面板"""
    thinking = block.thinking or ""
    if not thinking.strip():
        return '<details class="thinking-block"><summary>💭 思考过程</summary><div class="thinking-content"><em>（无思考内容）</em></div></details>'
    return f'''<details class="thinking-block">
<summary>💭 思考过程</summary>
<div class="thinking-content">{html_escape(thinking)}</div>
</details>'''


def _render_tool_use(block: ContentBlock) -> str:
    """工具调用卡片"""
    name = block.tool_name or "未知工具"
    msg = block.tool_message or ""
    icon = block.tool_icon or ""
    tool_input = block.tool_input or {}

    icon_display = TOOL_ICON_MAP.get(icon, "🔧")
    display_name = TOOL_DISPLAY_NAMES.get(name, name)

    # 格式化输入参数
    input_formatted = _escape_json(tool_input)

    msg_html = f'<span class="tool-msg">{html_escape(msg)}</span>' if msg else ""

    return f'''<div class="tool-card tool-use">
<div class="tool-header">{icon_display} 使用工具: <code class="tool-name">{html_escape(name)}</code>
<span class="tool-display-name">{html_escape(display_name)}</span>{msg_html}</div>
<details class="tool-input-details">
<summary>📝 输入参数</summary>
<pre><code class="language-json">{input_formatted}</code></pre>
</details>
</div>'''


def _render_tool_result(block: ContentBlock) -> str:
    """工具结果卡片 —— 递归渲染嵌套子内容，支持 CC 格式"""
    name = block.tool_name or "工具"
    is_error = block.is_error
    error_class = " tool-result-error" if is_error else ""

    # 优先使用子内容块渲染（Claude.ai 格式）
    if block.tool_result_content:
        sub_html = _render_tool_result_sub_blocks(block.tool_result_content)
    # CC 格式：纯文本内容
    elif block.tool_result_text:
        text = block.tool_result_text
        # 如果文本看起来像文件列表输出，用 <pre> 包裹
        if _looks_like_file_list(text):
            sub_html = f'<pre class="tool-result-output"><code>{html_escape(text)}</code></pre>'
        else:
            sub_html = f'<div class="text-block">{html_escape(text)}</div>'
    # CC 格式：文件结果
    elif block.tool_result_file:
        file_info = block.tool_result_file
        file_path = file_info.get("filePath", file_info.get("path", ""))
        file_content = file_info.get("content", "")
        num_lines = file_info.get("numLines", 0)
        start_line = file_info.get("startLine", 1)
        total_lines = file_info.get("totalLines", 0)

        parts = [f'<div class="tool-result-file">']
        parts.append(f'<div class="tool-result-file-header">📄 <code>{html_escape(file_path)}</code>')
        if total_lines:
            parts.append(f' <span class="file-line-info">(第 {start_line}-{start_line + num_lines - 1} 行，共 {total_lines} 行)</span>')
        parts.append('</div>')
        if file_content:
            parts.append(f'<pre><code>{html_escape(file_content)}</code></pre>')
        parts.append('</div>')
        sub_html = "\n".join(parts)
    else:
        sub_html = '<em>（空结果）</em>'

    error_badge = '<span class="error-badge">⚠️ 错误</span>' if is_error else ""

    return f'''<div class="tool-card tool-result{error_class}">
<div class="tool-header">📋 {html_escape(name)} 结果 {error_badge}</div>
<div class="tool-result-body">{sub_html}</div>
</div>'''


def _looks_like_file_list(text: str) -> bool:
    """检测文本是否看起来像文件列表输出"""
    if not text:
        return False
    lines = text.strip().split("\n")
    if len(lines) > 30:
        return True
    # 检测是否包含典型的路径分隔符
    path_count = sum(1 for line in lines if "/" in line or "\\" in line)
    return path_count > len(lines) * 0.5


def _render_code_block(block: ContentBlock) -> str:
    """代码块 —— highlight.js 自动高亮"""
    code = block.code or ""
    lang = block.language or ""
    lang_class = f' class="language-{html_escape(lang)}"' if lang else ""
    return f'<pre><code{lang_class}>{html_escape(code)}</code></pre>'


def _render_json_block(block: ContentBlock) -> str:
    """JSON 块 —— 格式化显示"""
    data = block.json_data or {}
    # 排除 type 和通用字段后显示
    display = {k: v for k, v in data.items()
               if k not in ("type", "start_timestamp", "stop_timestamp", "flags")}
    if not display:
        return ""
    formatted = _escape_json(display)
    return f'<pre><code class="language-json">{formatted}</code></pre>'


def _render_table(block: ContentBlock) -> str:
    """表格 —— 渲染为 HTML table"""
    rows = block.table_data
    if not rows or not isinstance(rows, list) or len(rows) == 0:
        return ""

    html_parts = ['<div class="table-wrapper"><table class="content-table">']

    # 第一行作为表头
    header_row = rows[0]
    if isinstance(header_row, list):
        html_parts.append("<thead><tr>")
        for cell in header_row:
            html_parts.append(f"<th>{html_escape(str(cell))}</th>")
        html_parts.append("</tr></thead>")

    # 剩余行作为表体
    if len(rows) > 1:
        html_parts.append("<tbody>")
        for row in rows[1:]:
            if isinstance(row, list):
                html_parts.append("<tr>")
                for cell in row:
                    html_parts.append(f"<td>{html_escape(str(cell))}</td>")
                html_parts.append("</tr>")
        html_parts.append("</tbody>")

    html_parts.append("</table></div>")
    return "\n".join(html_parts)


def _render_rich_content(block: ContentBlock) -> str:
    """富文本内容卡片（如 '已添加记忆' 通知）"""
    items = block.rich_content_items
    if not items:
        return ""

    parts = ['<div class="info-card rich-content">']
    for item in items:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        subtitles = item.get("subtitles", []) or []
        url = item.get("url", "")
        source = item.get("source", "")

        parts.append('<div class="info-card-item">')
        if title:
            if url:
                parts.append(f'<a href="{html_escape(url)}" target="_blank" class="info-title">{html_escape(title)}</a>')
            else:
                parts.append(f'<span class="info-title">{html_escape(title)}</span>')
        for sub in subtitles:
            parts.append(f'<span class="info-subtitle">{html_escape(str(sub))}</span>')
        if source:
            parts.append(f'<span class="info-source">{html_escape(str(source))}</span>')
        parts.append('</div>')

    parts.append('</div>')
    return "\n".join(parts)


def _render_rich_link(block: ContentBlock) -> str:
    """富链接预览卡片"""
    url = block.link_url or ""
    title = block.link_title or url
    desc = block.link_description or ""
    img = block.link_image_url or ""

    img_html = f'<img src="{html_escape(img)}" alt="" class="rich-link-img" loading="lazy">' if img else ""

    return f'''<a href="{html_escape(url)}" target="_blank" class="rich-link-card" rel="noopener">
{img_html}
<div class="rich-link-info">
<span class="rich-link-title">{html_escape(title)}</span>
<span class="rich-link-desc">{html_escape(safe_truncate(desc, 200))}</span>
<span class="rich-link-domain">{html_escape(url)}</span>
</div>
</a>'''


def _render_web_search_citation(block: ContentBlock) -> str:
    """网页搜索引用"""
    url = block.citation_url or ""
    title = block.citation_title or url
    text = block.citation_text or ""

    return f'''<div class="citation-block">
<span class="citation-title">🔗 <a href="{html_escape(url)}" target="_blank" rel="noopener">{html_escape(title)}</a></span>
<span class="citation-text">{html_escape(safe_truncate(text, 300))}</span>
</div>'''


def _render_webpage_metadata(block: ContentBlock) -> str:
    """网页元数据（favicon + 域名）"""
    domain = block.site_domain or ""
    favicon = block.favicon_url or ""
    site_name = block.site_name or domain

    favicon_html = f'<img src="{html_escape(favicon)}" alt="" class="favicon" loading="lazy" width="16" height="16">' if favicon else ""

    return f'''<span class="webpage-meta">
{favicon_html}
<span class="site-name">{html_escape(site_name)}</span>
<span class="site-domain">{html_escape(domain)}</span>
</span>'''


def _render_knowledge(block: ContentBlock) -> str:
    """知识库结果卡片（嵌套在 tool_result 中）"""
    title = block.knowledge_title or ""
    url = block.knowledge_url or ""
    text = block.knowledge_text or ""
    is_missing = block.is_missing

    # 渲染内嵌的 webpage_metadata
    meta_html = ""
    if block.metadata and isinstance(block.metadata, dict):
        meta_type = block.metadata.get("type", "")
        if meta_type == "webpage_metadata":
            meta_block = ContentBlock(
                type="webpage_metadata",
                site_domain=block.metadata.get("site_domain", ""),
                favicon_url=block.metadata.get("favicon_url", ""),
                site_name=block.metadata.get("site_name", ""),
            )
            meta_html = _render_webpage_metadata(meta_block)

    missing_badge = ' <span class="missing-badge">🔴 已失效</span>' if is_missing else ""

    return f'''<div class="knowledge-card">
<div class="knowledge-header">
{meta_html}
<a href="{html_escape(url)}" target="_blank" class="knowledge-title" rel="noopener">{html_escape(title)}{missing_badge}</a>
</div>
<div class="knowledge-text">{html_escape(safe_truncate(text, 500))}</div>
</div>'''


def _render_local_resource(block: ContentBlock) -> str:
    """本地文件引用（嵌套在 tool_result 中）"""
    file_path = block.file_path or ""
    file_name = block.file_name or file_path
    mime_type = block.mime_type or ""

    # 根据 MIME 类型选择图标
    icon = "📄"
    if mime_type:
        if "image" in mime_type:
            icon = "🖼️"
        elif "markdown" in mime_type or "text" in mime_type:
            icon = "📝"
        elif "pdf" in mime_type:
            icon = "📕"
        elif "code" in mime_type or "javascript" in mime_type or "json" in mime_type:
            icon = "💻"

    return f'''<div class="local-resource">
{icon} <span class="resource-name">{html_escape(file_name)}</span>
<span class="resource-meta">{html_escape(mime_type)} · {html_escape(file_path)}</span>
</div>'''


def _render_flag(block: ContentBlock) -> str:
    """标记/通知标签"""
    text = block.flag_text or ""
    level = block.flag_level or "info"
    level_class = f"flag-{level}" if level in ("info", "warning", "error") else "flag-info"

    return f'<span class="flag-badge {level_class}">{html_escape(text)}</span>'


def _render_artifact(block: ContentBlock) -> str:
    """Artifact 交互组件（application/vnd.ant.react）—— 降级显示"""
    raw = block.raw_data or {}
    artifact_name = raw.get("identifier", raw.get("name", "Artifact 组件"))
    return f'''<div class="artifact-placeholder">
<span class="artifact-icon">🧩</span>
<span class="artifact-name">交互组件: {html_escape(str(artifact_name))}</span>
<span class="artifact-hint">（需要在 Claude 网页版中查看完整交互内容）</span>
</div>'''


def _render_meta_event(block: ContentBlock) -> str:
    """Meta 事件块 —— 默认折叠的微型指示器"""
    label = block.flag_text or block.type
    raw = block.raw_data or {}

    # 如果没有额外数据，只显示标签
    if not raw or len(raw) <= 1:
        return f'<span class="meta-indicator">{html_escape(label)}</span>'

    # 有额外数据 → 可折叠展开查看原始 JSON
    formatted = _escape_json(raw)
    return f'''<details class="meta-event-details">
<summary><span class="meta-indicator">{html_escape(label)}</span></summary>
<pre class="meta-raw-data"><code class="language-json">{formatted}</code></pre>
</details>'''


def _render_unknown(block: ContentBlock) -> str:
    """未知类型 —— 降级显示原始 JSON"""
    raw = block.raw_data or {}
    display = {k: v for k, v in raw.items()
               if k not in ("start_timestamp", "stop_timestamp", "flags")}
    if not display:
        return f'<span class="unknown-block">[未知内容块: {html_escape(block.type)}]</span>'
    formatted = _escape_json(display)
    return f'''<details class="unknown-block-details">
<summary>📦 未知内容块: {html_escape(block.type)}</summary>
<pre><code class="language-json">{formatted}</code></pre>
</details>'''


# ═══════════════════════════════════════════
# 消息级渲染
# ═══════════════════════════════════════════

def render_message_html(sender: str, content_blocks: list, fallback_text: str = "",
                        msg_meta: dict = None) -> str:
    """将一条消息的所有内容块渲染为 HTML

    Args:
        sender: "human" | "assistant" | "system"
        content_blocks: ContentBlock 列表
        fallback_text: 如果 content_blocks 为空，使用此纯文本
        msg_meta: 消息元数据 (model, usage, stop_reason 等)，用于 CC 格式

    Returns:
        完整的消息体 HTML 字符串
    """
    parts = []

    # ── 系统消息特殊渲染 ──
    if sender == "system":
        return _render_system_message(fallback_text, msg_meta)

    # ── Meta 消息特殊渲染 ──
    if sender == "meta":
        return _render_meta_message(content_blocks, fallback_text)

    # ── CC 元数据横幅（仅 assistant 消息）──
    if msg_meta and sender == "assistant":
        meta_html = _render_cc_meta_banner(msg_meta)
        if meta_html:
            parts.append(meta_html)

    # 如果有内容块，使用内容块渲染
    if content_blocks:
        for block in content_blocks:
            if isinstance(block, ContentBlock):
                rendered = render_content_block(block)
                if rendered:
                    parts.append(rendered)
    elif fallback_text.strip():
        # 无内容块时，使用 text 字段作为后备
        parts.append(f'<div class="text-block">{html_escape(fallback_text)}</div>')

    return "\n".join(parts)


def _render_system_message(text: str, msg_meta: dict = None) -> str:
    """渲染系统消息（斜杠命令输出、轮次耗时等）"""
    if not text:
        return ""
    return f'<div class="system-message"><span class="system-message-text">{html_escape(text)}</span></div>'


def _render_meta_message(content_blocks: list, fallback_text: str = "") -> str:
    """渲染元事件消息 —— 微型可折叠指示器

    将多个 meta_event 块组合成一个可折叠的单元
    """
    if not content_blocks and not fallback_text:
        return ""

    parts = []
    for block in content_blocks:
        if isinstance(block, ContentBlock):
            rendered = render_content_block(block)
            if rendered:
                parts.append(rendered)

    if not parts and fallback_text:
        return f'<span class="meta-indicator">{html_escape(fallback_text)}</span>'

    return "\n".join(parts)


def _render_cc_meta_banner(msg_meta: dict) -> str:
    """渲染 CC 特有的元数据横幅（模型、用量等）"""
    if not msg_meta:
        return ""

    parts = []
    model = msg_meta.get("model")
    usage = msg_meta.get("usage")
    stop_reason = msg_meta.get("stop_reason")

    if model:
        parts.append(f'<span class="cc-meta-model">🤖 {html_escape(model)}</span>')

    if usage and isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        if input_tokens or output_tokens:
            tokens_str = f"↑{input_tokens}"
            if cache_read:
                tokens_str += f" (缓存命中:{cache_read})"
            tokens_str += f" ↓{output_tokens}"
            parts.append(f'<span class="cc-meta-tokens">🔢 {tokens_str}</span>')

    if stop_reason:
        reason_map = {
            "end_turn": "对话结束",
            "tool_use": "调用工具",
            "max_tokens": "达到上限",
            "stop_sequence": "遇到停止符",
        }
        reason_display = reason_map.get(stop_reason, stop_reason)
        parts.append(f'<span class="cc-meta-stop">{html_escape(reason_display)}</span>')

    if parts:
        return '<div class="cc-meta-banner">' + " · ".join(parts) + "</div>"

    return ""


def render_conversation_meta_html(conv) -> str:
    """渲染对话的 CC 元数据横幅（显示在对话顶部）

    Args:
        conv: Conversation 对象

    Returns:
        HTML 字符串
    """
    if conv.source_format != "claude_code":
        return ""

    parts = ['<div class="cc-session-meta">']

    if conv.mode:
        parts.append(f'<span class="cc-session-mode">📌 模式: {html_escape(conv.mode)}</span>')
    if conv.version:
        parts.append(f'<span class="cc-session-version">🔖 CC v{html_escape(conv.version)}</span>')
    if conv.cwd:
        parts.append(f'<span class="cc-session-cwd">📂 {html_escape(conv.cwd)}</span>')
    if conv.git_branch and conv.git_branch != "HEAD":
        parts.append(f'<span class="cc-session-git">🌿 {html_escape(conv.git_branch)}</span>')

    parts.append('</div>')

    if len(parts) > 1:  # 不止有闭合标签
        return "\n".join(parts)
    return ""
