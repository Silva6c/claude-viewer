"""JSON 解析器 —— 将 Claude 导出的对话数据解析为 Conversation 对象列表

支持的格式:
- conversations.json (JSON 数组) — Claude.ai 网页版导出
- JSONL (每行一个 JSON 对象) — Claude Code 会话记录
"""

import json
import sys
import re
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
        block.signature = raw.get("signature", "")

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
        # tool_result 的 content 可能是:
        # 1. 嵌套的子内容块数组 (Claude.ai 格式)
        # 2. 纯文本字符串 (CC 格式)
        # 3. 含 file 信息的 dict (CC 格式)
        raw_content = raw.get("content")
        if isinstance(raw_content, list):
            block.tool_result_content = [
                _parse_content_block(sub) for sub in raw_content
            ]
        elif isinstance(raw_content, str):
            block.tool_result_text = raw_content
            block.is_error = raw.get("is_error", False)
        elif isinstance(raw_content, dict):
            # CC 格式中 tool_result 可能是 dict
            block.tool_result_text = raw_content.get("content", "")
            block.is_error = raw_content.get("is_error", False)
            if "file" in raw_content:
                block.tool_result_file = raw_content["file"]
        # 检查 CC 格式的顶层 is_error
        if raw.get("is_error") and not block.is_error:
            block.is_error = True

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
    """解析单条消息 (Claude.ai 格式)"""
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
    """解析单个对话 (Claude.ai 格式)，失败返回 None"""
    try:
        conv = Conversation(
            uuid=raw.get("uuid", ""),
            name=raw.get("name", "未命名对话"),
            summary=raw.get("summary", ""),
            created_at=raw.get("created_at"),
            updated_at=raw.get("updated_at"),
            source_format="claude_ai",
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


# ═══════════════════════════════════════════
# 格式检测
# ═══════════════════════════════════════════

def _detect_format(content: str) -> str:
    """检测文件格式: "claude_ai_json" | "claude_code_jsonl" | "unknown"

    检测策略:
    1. 取第一行，尝试 JSON 解析
    2. 检查是否有 CC JSONL 的特征字段 (sessionId + type)
    3. 检查首字符判断 JSON 数组 vs JSONL
    """
    stripped = content.lstrip()
    if not stripped:
        return "unknown"

    # 取第一行尝试解析
    first_line = stripped.split("\n")[0].strip()
    try:
        first_obj = json.loads(first_line)
        if isinstance(first_obj, dict):
            # 检查 CC JSONL 特征: 有 sessionId 字段且有 type 字段
            if "sessionId" in first_obj and "type" in first_obj:
                return "claude_code_jsonl"
            # 有 chat_messages 字段 → Claude.ai JSONL (完整对话格式)
            if "chat_messages" in first_obj:
                return "claude_ai_jsonl"
            # 其他 JSONL 变体 → 尝试 CC 解析
            return "claude_code_jsonl"
    except (json.JSONDecodeError, KeyError):
        pass

    # 回退到首字符检测
    if stripped.startswith("["):
        return "claude_ai_json"
    elif stripped.startswith("{"):
        # 可能是 JSONL，尝试 CC 解析
        return "claude_code_jsonl"

    return "unknown"


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def load_conversations(filepath: str) -> list:
    """从文件加载对话列表

    支持格式:
    - JSON 数组 (conversations.json 标准格式)
    - Claude Code JSONL (每行一个事件，一个文件=一个会话)

    返回: List[Conversation]
    """
    print(f"[INFO] 正在读取文件: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    stripped = content.lstrip()
    if not stripped:
        raise ValueError("文件为空或仅包含空白字符")

    fmt = _detect_format(content)
    print(f"[INFO] 检测到格式: {fmt}")

    if fmt == "claude_ai_json":
        return _load_claude_ai_json(content)
    elif fmt in ("claude_code_jsonl", "claude_ai_jsonl"):
        # 先尝试 CC JSONL 解析
        result = _load_cc_jsonl(content)
        if result:
            return result
        # 回退到旧版 JSONL 解析
        return _parse_jsonl(content)
    else:
        raise ValueError(f"无法识别的文件格式，首个非空字符: '{stripped[0]}'")


# ═══════════════════════════════════════════
# Claude.ai JSON 数组格式
# ═══════════════════════════════════════════

def _load_claude_ai_json(content: str) -> list:
    """加载 Claude.ai 标准 JSON 数组格式"""
    conversations = []
    raw_list = json.loads(content)

    if not isinstance(raw_list, list):
        raise ValueError(f"期望 JSON 数组，实际类型: {type(raw_list).__name__}")

    total = len(raw_list)
    print("[INFO] 正在解析 JSON 数组...")
    for i, raw_conv in enumerate(raw_list):
        if not isinstance(raw_conv, dict):
            print(f"[WARN] 跳过非对象元素 [{i}]", file=sys.stderr)
            continue
        conv = _parse_conversation(raw_conv)
        if conv:
            conversations.append(conv)
        if (i + 1) % 20 == 0:
            print(f"  解析进度: {i + 1}/{total}")

    total_messages = sum(c.message_count for c in conversations)
    print(f"[OK] 解析完成: {len(conversations)} 个对话, {total_messages} 条消息")
    return conversations


# ═══════════════════════════════════════════
# Claude Code JSONL 格式解析
# ═══════════════════════════════════════════

def _load_cc_jsonl(content: str) -> list:
    """解析 Claude Code JSONL 事件流为 Conversation 列表

    CC JSONL 是一个事件流，每行一个 JSON 对象。
    一个文件 = 一个 CC 会话 = 一个 Conversation。

    事件类型:
    - mode, permission-mode, file-history-snapshot, last-prompt: 元事件（忽略）
    - user: 用户消息（可能是普通文本、斜杠命令或工具结果）
    - assistant: AI 回复（可能多行共享同一 message.id，需合并）
    - system: 系统消息（命令输出、轮次耗时等）
    - attachment: 附件（技能列表、任务提醒等）
    """
    # ── 第1步：逐行解析所有事件 ──
    events = []
    lines = content.strip().split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                events.append(obj)
        except json.JSONDecodeError as e:
            print(f"[WARN] 第 {i+1} 行 JSON 解析失败: {e}", file=sys.stderr)

    if not events:
        print("[WARN] JSONL 文件中没有有效事件")
        return []

    print(f"[INFO] 读取到 {len(events)} 个事件")

    # ── 第2步：提取会话元数据 ──
    session_id = None
    cwd = None
    git_branch = None
    version = None
    mode = "normal"
    first_timestamp = None
    last_timestamp = None

    for e in events:
        if not session_id:
            session_id = e.get("sessionId")
        if not cwd and e.get("cwd"):
            cwd = e["cwd"]
        if not git_branch and e.get("gitBranch"):
            git_branch = e["gitBranch"]
        if not version and e.get("version"):
            version = e["version"]
        if e.get("type") == "mode":
            mode = e.get("mode", "normal")
        ts = e.get("timestamp")
        if ts:
            if not first_timestamp:
                first_timestamp = ts
            last_timestamp = ts

    # ── 第3步：过滤事件 ──
    # 仅过滤真正无用户价值的内部追踪数据
    FILTERED_TYPES = {
        "file-history-snapshot",  # 纯内部文件追踪，体积大且无意义
    }
    # ai-title / agent-name 提取后也过滤（不显示为消息）
    NAME_EXTRACTION_TYPES = {"ai-title", "agent-name"}

    # 需要保留并转为 meta 消息的事件类型
    META_EVENT_TYPES = {
        "mode", "permission-mode", "last-prompt",
        "plan_mode", "plan_mode_exit", "plan_mode_reentry", "plan_file_reference",
        "date_change", "ultra_effort_enter", "ultra_effort_exit",
        "queued_command", "queue-operation", "command_permissions",
        "compact_file_reference", "invoked_skills", "agent-setting",
        "edited_text_file", "file", "task_reminder",
    }

    # 提取 ai-title 作为对话名称
    ai_title = None
    for e in events:
        if e.get("type") == "ai-title":
            ai_title = e.get("aiTitle")
            break

    main_events = []
    for e in events:
        t = e.get("type", "")
        # 过滤纯内部事件
        if t in FILTERED_TYPES:
            continue
        # 提取后过滤
        if t in NAME_EXTRACTION_TYPES:
            continue
        # 排除侧链
        if e.get("isSidechain", False):
            continue
        # 排除 isMeta=true 的用户消息（斜杠命令输出等）
        if e.get("isMeta", False) and t == "user":
            continue
        main_events.append(e)

    # ── 第4步：合并 assistant 消息（相同 message.id 的行合并 content）──
    merged_events = []
    i = 0
    while i < len(main_events):
        e = main_events[i]

        if e.get("type") == "assistant":
            msg = e.get("message", {})
            msg_id = msg.get("id", "")
            if msg_id:
                # 收集所有连续的同 message.id 的 assistant 事件
                merged_msg = dict(msg)  # 浅拷贝 message 对象
                merged_content = list(msg.get("content", []))
                merged_uuid = e.get("uuid", "")
                merged_timestamp = e.get("timestamp", "")
                j = i + 1

                while j < len(main_events):
                    next_e = main_events[j]
                    if next_e.get("type") != "assistant":
                        break
                    next_msg = next_e.get("message", {})
                    if next_msg.get("id") != msg_id:
                        break
                    # 合并 content
                    next_content = next_msg.get("content", [])
                    merged_content.extend(next_content)
                    # 更新时间为最新
                    if next_e.get("timestamp"):
                        merged_timestamp = next_e["timestamp"]
                    if next_e.get("uuid"):
                        merged_uuid = next_e["uuid"]
                    j += 1

                merged_msg["content"] = merged_content
                merged_e = dict(e)
                merged_e["message"] = merged_msg
                merged_e["uuid"] = merged_uuid
                merged_e["timestamp"] = merged_timestamp
                merged_events.append(merged_e)
                i = j
            else:
                merged_events.append(e)
                i += 1
        else:
            merged_events.append(e)
            i += 1

    # ── 第5步：识别 tool_result 并关联到前一个 assistant 消息 ──
    # 在 CC 格式中，tool_result 作为 type:"user" 出现
    # 需要将其附加到前一个使用了工具的 assistant 消息
    processed_events = []
    i = 0
    while i < len(merged_events):
        e = merged_events[i]

        if e.get("type") == "user":
            # 检查是否为 tool_result
            msg_content = e.get("message", {}).get("content")
            is_tool_result = False

            if isinstance(msg_content, list):
                for item in msg_content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        is_tool_result = True
                        break

            if is_tool_result:
                # 找到前一个 assistant 消息，附加 tool_result
                if processed_events:
                    last = processed_events[-1]
                    if last.get("type") == "assistant":
                        # 将 tool_result 附加到 assistant 消息的 content 中
                        last_content = last.get("message", {}).get("content", [])
                        for item in msg_content:
                            if isinstance(item, dict):
                                last_content.append(item)
                        last["message"]["content"] = last_content
                        # 更新 tool_result 相关元数据
                        tr_data = e.get("toolUseResult")
                        if tr_data:
                            last["_tool_use_result"] = tr_data
                        i += 1
                        continue

            # 不是 tool_result，正常添加
            processed_events.append(e)

        elif e.get("type") == "system":
            # 系统消息保留
            processed_events.append(e)
        elif e.get("type") == "attachment":
            # 附件保留
            processed_events.append(e)
        elif e.get("type") in META_EVENT_TYPES:
            # 元事件保留
            processed_events.append(e)
        else:
            # assistant 消息正常添加
            processed_events.append(e)

        i += 1

    # ── 第6步：构建 ChatMessage 列表 ──
    messages = []
    for e in processed_events:
        t = e.get("type", "")
        msg_obj = e.get("message", {})

        if t == "user":
            # 用户消息
            user_content = msg_obj.get("content", "")

            # 提取纯文本
            if isinstance(user_content, str):
                text = user_content
                content_blocks = []
            elif isinstance(user_content, list):
                # 用户消息中的 content 数组（通常为空或含特殊块）
                text = ""
                content_blocks = []
                for item in user_content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text = item.get("text", "")
                        else:
                            content_blocks.append(_parse_content_block(item))
                    elif isinstance(item, str):
                        text = item
            else:
                text = str(user_content)
                content_blocks = []

            # 清理斜杠命令标记
            clean_text = _clean_user_message(text)

            # 跳过中断消息和空消息
            if not clean_text or "[Request interrupted" in clean_text:
                continue

            msg = ChatMessage(
                uuid=e.get("uuid", ""),
                sender="human",
                text=clean_text,
                content_blocks=content_blocks,
                created_at=e.get("timestamp"),
                parent_message_uuid=e.get("parentUuid"),
                cwd=e.get("cwd"),
                git_branch=e.get("gitBranch"),
                version=e.get("version"),
                message_type="user",
                is_meta=e.get("isMeta", False),
                is_sidechain=e.get("isSidechain", False),
                is_tool_result=False,
            )
            messages.append(msg)

        elif t == "assistant":
            # AI 回复
            raw_content = msg_obj.get("content", [])
            content_blocks = []
            for item in raw_content:
                if isinstance(item, dict):
                    content_blocks.append(_parse_content_block(item))

            # 提取纯文本
            text = ""
            for block in content_blocks:
                if block.type == "text" and block.text:
                    text = block.text
                    break

            msg = ChatMessage(
                uuid=e.get("uuid", ""),
                sender="assistant",
                text=text,
                content_blocks=content_blocks,
                created_at=e.get("timestamp"),
                parent_message_uuid=e.get("parentUuid"),
                model=msg_obj.get("model"),
                usage=msg_obj.get("usage"),
                stop_reason=msg_obj.get("stop_reason"),
                cwd=e.get("cwd"),
                git_branch=e.get("gitBranch"),
                version=e.get("version"),
                message_type="assistant",
                is_meta=False,
                is_sidechain=e.get("isSidechain", False),
            )
            messages.append(msg)

        elif t == "system":
            # 系统消息
            subtype = e.get("subtype", "")
            sys_content = e.get("content", "")

            if subtype == "turn_duration":
                # 轮次耗时 —— 作为系统消息显示
                duration_ms = e.get("durationMs", 0)
                msg_count = e.get("messageCount", 0)
                sys_text = f"[本轮耗时 {duration_ms / 1000:.1f}s，共 {msg_count} 条消息]"
            elif subtype == "local_command":
                # 斜杠命令输出 —— 清理 XML 标记
                sys_text = _clean_system_message(sys_content) if sys_content else ""
            else:
                sys_text = sys_content if sys_content else ""

            if sys_text.strip():
                msg = ChatMessage(
                    uuid=e.get("uuid", ""),
                    sender="system",
                    text=sys_text,
                    content_blocks=[],
                    created_at=e.get("timestamp"),
                    parent_message_uuid=e.get("parentUuid"),
                    message_type="system",
                    is_meta=True,
                )
                messages.append(msg)

        elif t in META_EVENT_TYPES:
            # 元事件 → 转为折叠的 meta 消息
            meta_text = _format_meta_event(e)
            if meta_text:
                msg = ChatMessage(
                    uuid=e.get("uuid", ""),
                    sender="meta",
                    text=meta_text,
                    content_blocks=[_build_meta_content_block(e)],
                    created_at=e.get("timestamp"),
                    parent_message_uuid=e.get("parentUuid"),
                    message_type=t,
                    is_meta=True,
                )
                messages.append(msg)

        elif t == "attachment":
            # 附件（技能列表等）
            att = e.get("attachment", {})
            att_type = att.get("type", "")
            att_content = att.get("content", "")

            if att_type == "skill_listing":
                # 技能列表 —— 首次出现时作为系统上下文显示
                is_initial = att.get("isInitial", False)
                if is_initial:
                    skill_count = att.get("skillCount", 0)
                    msg = ChatMessage(
                        uuid=e.get("uuid", ""),
                        sender="system",
                        text=f"📋 已加载 {skill_count} 个技能",
                        content_blocks=[],
                        created_at=e.get("timestamp"),
                        parent_message_uuid=e.get("parentUuid"),
                        message_type="attachment",
                        is_meta=True,
                    )
                    messages.append(msg)

    # ── 第7步：构建 Conversation ──
    if not session_id:
        session_id = "unknown-session"

    # 生成对话名称：优先使用 ai-title，其次第一条用户消息
    if ai_title:
        conv_name = ai_title
    else:
        conv_name = _generate_cc_conversation_name(messages, cwd)

    conv = Conversation(
        uuid=session_id,
        name=conv_name,
        summary=f"Claude Code 会话 — {cwd or '未知目录'}",
        created_at=first_timestamp,
        updated_at=last_timestamp,
        messages=messages,
        session_id=session_id,
        cwd=cwd,
        git_branch=git_branch,
        version=version,
        mode=mode,
        source_format="claude_code",
    )

    total_messages = sum(1 for m in messages if m.sender in ("human", "assistant"))
    print(f"[OK] CC 会话解析完成: {len(messages)} 条消息 "
          f"(用户+AI: {total_messages}, 系统: {conv.system_message_count})")
    return [conv]


def _clean_user_message(text: str) -> str:
    """清理用户消息中的 XML 标记和特殊格式

    CC 用户消息可能包含:
    - <command-name>...</command-name>
    - <command-message>...</command-message>
    - <command-args>...</command-args>
    - <local-command-caveat>...</local-command-caveat>
    - <local-command-stdout>...</local-command-stdout>
    - <system-reminder>...</system-reminder>
    """
    if not text:
        return ""

    # 提取斜杠命令名（如果有的话）
    cmd_match = re.search(r'<command-name>(.*?)</command-name>', text, re.DOTALL)
    cmd_args_match = re.search(r'<command-args>(.*?)</command-args>', text, re.DOTALL)

    if cmd_match:
        cmd_name = cmd_match.group(1).strip()
        cmd_args = cmd_args_match.group(1).strip() if cmd_args_match else ""
        if cmd_args:
            return f"/{cmd_name} {cmd_args}"
        return f"/{cmd_name}"

    # 移除 XML 标记，保留纯文本
    # 先移除 caveat 和 reminder
    cleaned = re.sub(r'<local-command-caveat>.*?</local-command-caveat>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<system-reminder>.*?</system-reminder>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<local-command-stdout>.*?</local-command-stdout>', '', cleaned, flags=re.DOTALL)

    # 移除剩余的 XML 标签
    cleaned = re.sub(r'<[^>]+>', '', cleaned)

    # 移除多余空白
    cleaned = cleaned.strip()

    return cleaned if cleaned else text.strip()


def _clean_system_message(text: str) -> str:
    """清理系统消息中的 XML 标记"""
    if not text:
        return ""
    # 移除 XML 标签
    cleaned = re.sub(r'<local-command-stdout>', '', text)
    cleaned = re.sub(r'</local-command-stdout>', '', cleaned)
    cleaned = re.sub(r'<local-command-caveat>.*?</local-command-caveat>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<system-reminder>.*?</system-reminder>', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    return cleaned.strip()


def _format_meta_event(e: dict) -> str:
    """将 CC 元事件格式化为人类可读的摘要文本"""
    t = e.get("type", "")

    if t == "mode":
        mode = e.get("mode", "unknown")
        return f"会话模式: {mode}"
    elif t == "permission-mode":
        pm = e.get("permissionMode", "unknown")
        return f"权限模式: {pm}"
    elif t == "last-prompt":
        lp = e.get("lastPrompt", "")
        preview = lp[:80] + "…" if len(lp) > 80 else lp
        return f"最后提示: {preview}"
    elif t == "plan_mode":
        return "进入计划模式"
    elif t == "plan_mode_exit":
        return "退出计划模式"
    elif t == "plan_mode_reentry":
        return "重新进入计划模式"
    elif t == "plan_file_reference":
        return "引用计划文件"
    elif t == "date_change":
        date = e.get("date", "")
        return f"日期变更: {date}" if date else "日期变更"
    elif t == "ultra_effort_enter":
        return "进入全力模式 (ultracode)"
    elif t == "ultra_effort_exit":
        return "退出全力模式"
    elif t == "queued_command":
        cmd = e.get("command", e.get("commandId", ""))
        return f"后台命令已入队: {cmd}" if cmd else "后台命令已入队"
    elif t == "queue-operation":
        op = e.get("operation", "")
        return f"队列操作: {op}" if op else "队列操作"
    elif t == "command_permissions":
        return "命令权限已更新"
    elif t == "compact_file_reference":
        return "紧凑文件引用"
    elif t == "invoked_skills":
        skills = e.get("skills", e.get("names", []))
        if isinstance(skills, list) and skills:
            names = ", ".join(str(s) for s in skills[:5])
            if len(skills) > 5:
                names += f" 等{len(skills)}个"
            return f"调用技能: {names}"
        return "调用技能"
    elif t == "agent-setting":
        agent = e.get("agentSetting", "")
        return f"代理设置: {agent}" if agent else "代理设置已更改"
    elif t == "edited_text_file":
        path = e.get("path", e.get("filePath", ""))
        return f"编辑文件: {path}" if path else "文件已编辑"
    elif t == "file":
        path = e.get("path", e.get("filePath", ""))
        return f"文件操作: {path}" if path else "文件操作"
    elif t == "task_reminder":
        items = e.get("items", e.get("content", []))
        count = len(items) if isinstance(items, list) else 0
        return f"任务提醒 ({count} 项)" if count else "任务提醒"
    else:
        return f"事件: {t}"


def _build_meta_content_block(e: dict) -> ContentBlock:
    """将元事件的原始 JSON 打包为 ContentBlock 供展开查看"""
    # 过滤掉过于内部或重复的字段
    skip_keys = {"sessionId", "version", "gitBranch", "cwd", "userType", "entrypoint",
                 "isSidechain", "uuid", "parentUuid", "timestamp"}
    display = {k: v for k, v in e.items() if k not in skip_keys and v is not None}
    return ContentBlock(
        type="meta_event",
        raw_data=display,
        flag_text=_format_meta_event(e),
        flag_level="info",
    )


def _generate_cc_conversation_name(messages: list, cwd: str = None) -> str:
    """从 CC 会话中生成对话名称"""
    # 找第一条有实质内容的用户消息（跳过斜杠命令和中断消息）
    for msg in messages:
        if msg.sender == "human" and msg.text and not msg.is_meta:
            text = msg.text.strip()
            # 跳过斜杠命令
            if text.startswith("/"):
                continue
            # 跳过中断消息
            if "[Request interrupted" in text:
                continue
            # 截取前 60 个字符作为标题
            if len(text) > 60:
                text = text[:60] + "…"
            return text

    # 回退到目录名
    if cwd:
        import os
        return f"CC 会话 — {os.path.basename(cwd)}"

    return "Claude Code 会话"


# ═══════════════════════════════════════════
# 旧版 JSONL 解析（兼容预留）
# ═══════════════════════════════════════════

def _parse_jsonl(content: str) -> list:
    """解析 JSONL 格式（每行一个完整的对话对象，旧版兼容）"""
    conversations = []
    lines = content.strip().split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            if isinstance(raw, dict):
                if "chat_messages" in raw:
                    conv = _parse_conversation(raw)
                    if conv:
                        conversations.append(conv)
                else:
                    print(f"[WARN] 第 {i+1} 行: 跳过非对话格式", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"[WARN] 第 {i+1} 行 JSON 解析失败: {e}", file=sys.stderr)
    return conversations


# ═══════════════════════════════════════════
# 安全加载
# ═══════════════════════════════════════════

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
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []
