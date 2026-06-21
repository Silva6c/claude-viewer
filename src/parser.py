"""JSON 解析器 —— 将 Claude 导出的 conversations.json 解析为 Conversation 对象列表

支持的格式:
- conversations.json (JSON 数组) — Claude.ai 网页版导出
- JSONL (每行一个 JSON 对象) — Claude Code 会话记录（预留）
"""

import json
import sys
from typing import Optional

from .models import Conversation, ChatMessage, ContentBlock


def _parse_content_block(raw: dict) -> ContentBlock:
    """解析单个内容块 —— 根据 type 字段提取对应字段"""
    block_type = raw.get("type", "unknown")
    block = ContentBlock(type=block_type)

    # 通用字段
    block.start_timestamp = raw.get("start_timestamp")
    block.stop_timestamp = raw.get("stop_timestamp")
    block.flags = raw.get("flags")

    # ── text 类型 ──
    if block_type == "text":
        block.text = raw.get("text", "")
        block.citations = raw.get("citations", []) or []

    # ── thinking 类型 ──
    elif block_type == "thinking":
        block.thinking = raw.get("thinking", "")

    # ── tool_use 类型 ──
    elif block_type == "tool_use":
        block.tool_id = raw.get("id", "")
        block.tool_name = raw.get("name", "unknown_tool")
        block.tool_input = raw.get("input", {}) or {}
        block.tool_message = raw.get("message", "")
        block.tool_icon = raw.get("icon_name", "")

    # ── tool_result 类型 ──
    elif block_type == "tool_result":
        block.tool_use_id = raw.get("tool_use_id", "")
        block.tool_name = raw.get("name", "")
        block.is_error = raw.get("is_error", False)
        # tool_result 的 content 是嵌套的子内容块数组
        raw_sub_content = raw.get("content", [])
        if raw_sub_content:
            block.tool_result_content = [
                _parse_content_block(sub) for sub in raw_sub_content
            ]

    # ── code_block 类型 ──
    elif block_type == "code_block":
        block.language = raw.get("language", "")
        block.code = raw.get("code", "")

    # ── json_block 类型 ──
    elif block_type == "json_block":
        block.json_data = raw

    # ── table 类型 ──
    elif block_type == "table":
        block.table_data = raw.get("table", []) or []

    # ── rich_content 类型 ──
    elif block_type == "rich_content":
        block.rich_content_items = raw.get("content", []) or []

    # ── rich_link 类型 ──
    elif block_type == "rich_link":
        block.link_url = raw.get("url", "")
        block.link_title = raw.get("title", "")
        block.link_description = raw.get("description", "")
        block.link_image_url = raw.get("image_url", "")

    # ── web_search_citation 类型 ──
    elif block_type == "web_search_citation":
        block.citation_url = raw.get("url", "")
        block.citation_title = raw.get("title", "")
        block.citation_text = raw.get("text", "")

    # ── webpage_metadata 类型（常嵌套于 tool_result）──
    elif block_type == "webpage_metadata":
        block.site_domain = raw.get("site_domain", "")
        block.favicon_url = raw.get("favicon_url", "")
        block.site_name = raw.get("site_name", "")

    # ── knowledge 类型（嵌套于 tool_result）──
    elif block_type == "knowledge":
        block.knowledge_title = raw.get("title", "")
        block.knowledge_url = raw.get("url", "")
        block.knowledge_text = raw.get("text", "")
        block.is_missing = raw.get("is_missing", False)
        # 可能内嵌 webpage_metadata
        raw_meta = raw.get("metadata")
        if raw_meta:
            block.metadata = raw_meta

    # ── local_resource 类型（嵌套于 tool_result）──
    elif block_type == "local_resource":
        block.file_path = raw.get("file_path", "")
        block.file_name = raw.get("name", "")
        block.mime_type = raw.get("mime_type", "")

    # ── flag 类型 ──
    elif block_type == "flag":
        block.flag_text = raw.get("text", "")
        block.flag_level = raw.get("level", "info")

    # ── application/vnd.ant.react (Artifact 组件) ──
    elif block_type == "application/vnd.ant.react":
        # 保留完整原始数据供降级渲染
        block.raw_data = raw

    # ── 未知类型: 保留原始数据供降级渲染 ──
    else:
        block.raw_data = raw

    return block


def _parse_message(raw: dict) -> ChatMessage:
    """解析单条消息"""
    msg = ChatMessage(
        uuid=raw.get("uuid", ""),
        sender=raw.get("sender", "unknown"),
        text=raw.get("text", "") or "",
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        parent_message_uuid=raw.get("parent_message_uuid"),
        attachments=raw.get("attachments", []) or [],
        files=raw.get("files", []) or [],
    )

    # 解析 content 数组
    raw_content = raw.get("content", [])
    if raw_content:
        for item in raw_content:
            if isinstance(item, dict):
                msg.content_blocks.append(_parse_content_block(item))

    return msg


def _parse_conversation(raw: dict) -> Optional[Conversation]:
    """解析单个对话，失败返回 None"""
    try:
        conv = Conversation(
            uuid=raw.get("uuid", ""),
            name=raw.get("name", "未命名对话"),
            summary=raw.get("summary", ""),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
        )
        # 提取 account uuid
        account = raw.get("account", {})
        if isinstance(account, dict):
            conv.account_uuid = account.get("uuid")

        # 解析消息
        raw_messages = raw.get("chat_messages", [])
        for raw_msg in raw_messages:
            if isinstance(raw_msg, dict):
                msg = _parse_message(raw_msg)
                conv.messages.append(msg)

        return conv
    except Exception as e:
        print(f"[WARN] 解析对话失败: {raw.get('name', '未知')} — {e}", file=sys.stderr)
        return None


def load_conversations(filepath: str) -> list:
    """从 JSON 文件加载对话列表

    支持格式:
    - JSON 数组 (conversations.json 标准格式)
    - JSONL (每行一个对话对象，预留)

    返回: List[Conversation]
    """
    conversations = []

    print(f"[INFO] 正在读取文件: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    stripped = content.lstrip()
    if not stripped:
        raise ValueError("文件为空或仅包含空白字符")

    print("[INFO] 正在解析 JSON...")

    if stripped.startswith("["):
        # JSON 数组格式
        raw_list = json.loads(content)
        if not isinstance(raw_list, list):
            raise ValueError(f"期望 JSON 数组，实际类型: {type(raw_list).__name__}")

        total = len(raw_list)
        for i, raw_conv in enumerate(raw_list):
            if not isinstance(raw_conv, dict):
                print(f"[WARN] 跳过非对象元素 [{i}]", file=sys.stderr)
                continue
            conv = _parse_conversation(raw_conv)
            if conv:
                conversations.append(conv)
            if (i + 1) % 20 == 0:
                print(f"  解析进度: {i + 1}/{total}")

    elif stripped.startswith("{"):
        # JSONL 格式: 尝试按行解析
        conversations = _parse_jsonl(content)

    else:
        raise ValueError(f"无法识别的文件格式，首个非空字符: '{stripped[0]}'")

    # 统计信息
    total_messages = sum(c.message_count for c in conversations)
    print(f"[OK] 解析完成: {len(conversations)} 个对话, {total_messages} 条消息")
    return conversations


def _parse_jsonl(content: str) -> list:
    """解析 JSONL 格式（每行一个 JSON 对象）"""
    conversations = []
    lines = content.strip().split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            if isinstance(raw, dict):
                # 可能是完整对话，也可能是单条消息需要聚合
                if "chat_messages" in raw:
                    # 完整对话
                    conv = _parse_conversation(raw)
                    if conv:
                        conversations.append(conv)
                else:
                    # 单条消息格式（预留）
                    print(f"[WARN] 第 {i+1} 行: 跳过非对话格式", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"[WARN] 第 {i+1} 行 JSON 解析失败: {e}", file=sys.stderr)
    return conversations


def load_conversations_safe(filepath: str) -> list:
    """安全加载 —— 捕获所有异常，返回空列表而不是崩溃"""
    try:
        return load_conversations(filepath)
    except FileNotFoundError:
        print(f"[ERROR] 文件不存在: {filepath}", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"[ERROR] 未知错误: {e}", file=sys.stderr)
        return []
