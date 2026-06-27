"""Claude 对话浏览器 —— Flask Web 应用

启动后在浏览器中打开图形界面，支持:
- 自动加载 chat_history/ 下的 conversations.json 和 .jsonl 文件
- 拖拽或浏览选择 .json / .jsonl 文件
- 侧边栏对话列表，支持搜索
- 一问一答格式查看对话
- Thinking 块默认折叠
- 代码语法高亮
- 亮/暗主题切换
- 用户画像（memories.json）
- Claude Code JSONL 格式支持
"""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import webbrowser
from urllib.parse import quote as _url_quote
from flask import Flask, request, jsonify, Response, render_template

from src.parser import load_conversations_safe
from src.content_renderer import render_message_html, render_conversation_meta_html
from src.renderer_md import export_conversation_md
from src.models import Conversation, ChatMessage
from src.utils import format_timestamp, extract_date, safe_truncate, sanitize_filename

app = Flask(__name__)

# 消掉 Flask 开发服务器警告
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ── 全局状态 ──
conversations: list[Conversation] = []
user_profile: dict = {}          # 用户画像数据
_conversation_index: dict = {}   # UUID → Conversation 快速查找


# ═══════════════════════════════════════════
# 页面路由
# ═══════════════════════════════════════════

@app.route("/")
def index():
    """返回单页面前端"""
    return render_template("index.html")


# ═══════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """接收上传的文件（.json 或 .jsonl）并解析"""
    global conversations

    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    # 获取文件扩展名
    _, ext = os.path.splitext(file.filename)
    if ext not in (".json", ".jsonl"):
        return jsonify({"error": f"不支持的文件格式: {ext}，请上传 .json 或 .jsonl 文件"}), 400

    # 保留原始扩展名
    suffix = ext if ext else ".json"
    with tempfile.NamedTemporaryFile(mode='wb', suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        conversations = load_conversations_safe(temp_path)
        global _conversation_index
        _conversation_index = {c.uuid: c for c in conversations}
        total_messages = sum(c.message_count for c in conversations)

        # 检测格式
        source_format = conversations[0].source_format if conversations else "unknown"

        return jsonify({
            "success": True,
            "conversation_count": len(conversations),
            "message_count": total_messages,
            "filename": file.filename,
            "source_format": source_format,
        })
        # 持久化：复制到 chat_history 目录，刷新/重启不丢失
        try:
            import shutil
            base_dir = os.path.dirname(os.path.abspath(__file__))
            chat_dir = os.path.join(base_dir, "chat_history")
            os.makedirs(chat_dir, exist_ok=True)
            dest_path = os.path.join(chat_dir, file.filename)
            shutil.copy(temp_path, dest_path)
            print(f"[INFO] 文件已保存到: {dest_path}")
        except Exception as copy_err:
            print(f"[WARN] 复制文件到 chat_history 失败: {copy_err}")
    except Exception as e:
        return jsonify({"error": f"解析失败: {str(e)}"}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.route("/api/list")
def api_list():
    """返回对话列表（摘要信息）"""
    result = []
    for conv in conversations:
        item = {
            "uuid": conv.uuid,
            "name": conv.name,
            "summary": safe_truncate(conv.summary, 200) if conv.summary else "",
            "created_at": format_timestamp(conv.created_at),
            "updated_at": format_timestamp(conv.updated_at),
            "date": extract_date(conv.updated_at),
            "message_count": conv.message_count,
            "source_format": conv.source_format,
        }
        # CC 特有信息
        if conv.source_format == "claude_code":
            item["cwd"] = conv.cwd
            item["git_branch"] = conv.git_branch
            item["version"] = conv.version
            item["mode"] = conv.mode
        result.append(item)

    result.sort(key=lambda c: c["updated_at"] or c["created_at"], reverse=True)

    return jsonify({
        "conversations": result,
        "total": len(result),
        "has_profile": bool(user_profile),
    })


@app.route("/api/conv/<conv_uuid>")
def api_conversation(conv_uuid: str):
    """返回单个对话的完整数据（含渲染后的 HTML）

    支持分页参数:
    - limit: 每页消息数（默认50，设为0表示全部）
    - offset: 偏移量（默认0）
    """
    conv = _find_conversation(conv_uuid)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404

    # 分页参数
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        limit = 50
        offset = 0

    total_messages = len(conv.messages)

    # limit=0 表示全部加载
    if limit <= 0:
        limit = total_messages

    page_messages = conv.messages[offset:offset + limit]
    has_more = (offset + limit) < total_messages

    # ── 构建轻量消息索引（全量，不受分页影响）──
    message_index = []
    for i, msg in enumerate(conv.messages):
        preview = _get_message_preview(msg)
        message_index.append({
            "uuid": msg.uuid,
            "sender": msg.sender,
            "preview": preview,
            "timestamp": format_timestamp(msg.created_at),
            "has_tool_use": any(b.type == "tool_use" for b in msg.content_blocks),
            "is_meta": msg.is_meta,
            "page": i // limit if limit > 0 else 0,  # 该消息所在页
        })

    messages = []
    for msg in page_messages:
        # 构建消息元数据
        msg_meta = {
            "model": msg.model,
            "usage": msg.usage,
            "stop_reason": msg.stop_reason,
            "cwd": msg.cwd,
            "git_branch": msg.git_branch,
            "version": msg.version,
        }

        rendered_html = render_message_html(
            sender=msg.sender,
            content_blocks=msg.content_blocks,
            fallback_text=msg.text,
            msg_meta=msg_meta,
        )

        msg_data = {
            "uuid": msg.uuid,
            "sender": msg.sender,
            "created_at": format_timestamp(msg.created_at),
            "rendered_html": rendered_html,
        }

        # CC 特有字段
        if msg.model:
            msg_data["model"] = msg.model
        if msg.usage:
            msg_data["usage"] = msg.usage
        if msg.stop_reason:
            msg_data["stop_reason"] = msg.stop_reason
        if msg.is_meta:
            msg_data["is_meta"] = True

        messages.append(msg_data)

    # 对话级 CC 元数据
    cc_meta_html = render_conversation_meta_html(conv)

    response = {
        "uuid": conv.uuid,
        "name": conv.name,
        "summary": conv.summary,
        "created_at": format_timestamp(conv.created_at),
        "updated_at": format_timestamp(conv.updated_at),
        "message_count": conv.message_count,
        "messages": messages,
        "message_index": message_index,
        "source_format": conv.source_format,
        # 分页信息
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "total_messages": total_messages,
    }

    if cc_meta_html:
        response["cc_meta_html"] = cc_meta_html

    # CC 特有元数据
    if conv.source_format == "claude_code":
        response["cwd"] = conv.cwd
        response["git_branch"] = conv.git_branch
        response["version"] = conv.version
        response["mode"] = conv.mode
        response["session_id"] = conv.session_id

    return jsonify(response)


@app.route("/api/conv/<conv_uuid>/messages")
def api_conversation_messages(conv_uuid: str):
    """按 UUID 列表返回指定消息的完整 HTML（用于搜索后按需加载）"""
    conv = _find_conversation(conv_uuid)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404

    ids_str = request.args.get("ids", "")
    if not ids_str:
        return jsonify({"error": "缺少 ids 参数"}), 400

    ids = [s.strip() for s in ids_str.split(",") if s.strip()]

    # 建立消息 UUID → 消息的索引
    msg_map = {m.uuid: m for m in conv.messages}

    messages = []
    for mid in ids:
        msg = msg_map.get(mid)
        if not msg:
            continue

        msg_meta = {
            "model": msg.model,
            "usage": msg.usage,
            "stop_reason": msg.stop_reason,
            "cwd": msg.cwd,
            "git_branch": msg.git_branch,
            "version": msg.version,
        }

        rendered_html = render_message_html(
            sender=msg.sender,
            content_blocks=msg.content_blocks,
            fallback_text=msg.text,
            msg_meta=msg_meta,
        )

        msg_data = {
            "uuid": msg.uuid,
            "sender": msg.sender,
            "created_at": format_timestamp(msg.created_at),
            "rendered_html": rendered_html,
        }
        if msg.model:
            msg_data["model"] = msg.model
        if msg.usage:
            msg_data["usage"] = msg.usage
        if msg.stop_reason:
            msg_data["stop_reason"] = msg.stop_reason
        if msg.is_meta:
            msg_data["is_meta"] = True

        messages.append(msg_data)

    return jsonify({"messages": messages})


@app.route("/api/conv/<conv_uuid>/export")
def api_export_conversation(conv_uuid: str):
    """导出单个对话为 Markdown 文件"""
    conv = _find_conversation(conv_uuid)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404

    md_content = export_conversation_md(conv)

    # 生成安全的文件名
    safe_name = sanitize_filename(conv.name)
    filename = f"{safe_name}.md"

    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename)}"
        }
    )


@app.route("/api/search")
def api_search():
    """搜索对话（按标题、摘要和消息正文模糊匹配）"""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": [], "total": 0})

    results = []
    seen = set()

    for conv in conversations:
        name_lower = conv.name.lower()
        summary_lower = conv.summary.lower() if conv.summary else ""

        # 匹配标题或摘要
        if query in name_lower or query in summary_lower:
            key = conv.uuid + ":title"
            if key not in seen:
                item = {
                    "uuid": conv.uuid,
                    "name": conv.name,
                    "summary": safe_truncate(conv.summary, 200) if conv.summary else "",
                    "updated_at": format_timestamp(conv.updated_at),
                    "date": extract_date(conv.updated_at),
                    "message_count": conv.message_count,
                    "match_in": "title" if query in name_lower else "summary",
                    "source_format": conv.source_format,
                }
                results.append(item)
                seen.add(key)

        # 搜索消息正文
        matched_snippets = []
        for msg in conv.messages:
            preview = _get_message_preview(msg, 200)
            if preview and query in preview.lower():
                matched_snippets.append(preview)
                if len(matched_snippets) >= 3:
                    break

        if matched_snippets:
            key = conv.uuid + ":messages"
            if key not in seen:
                item = {
                    "uuid": conv.uuid,
                    "name": conv.name,
                    "summary": safe_truncate(conv.summary, 200) if conv.summary else "",
                    "updated_at": format_timestamp(conv.updated_at),
                    "date": extract_date(conv.updated_at),
                    "message_count": conv.message_count,
                    "match_in": "messages",
                    "snippets": matched_snippets,
                    "source_format": conv.source_format,
                }
                results.append(item)
                seen.add(key)

    results.sort(key=lambda c: c["updated_at"] or c["created_at"], reverse=True)

    return jsonify({"results": results, "total": len(results)})


@app.route("/api/stats")
def api_stats():
    """返回数据统计信息"""
    if not conversations:
        return jsonify({"error": "未加载数据"}), 400

    total_messages = sum(c.message_count for c in conversations)
    total_human = sum(c.human_message_count for c in conversations)
    total_assistant = sum(c.assistant_message_count for c in conversations)
    total_system = sum(c.system_message_count for c in conversations)

    type_counts = {}
    for conv in conversations:
        for msg in conv.messages:
            for block in msg.content_blocks:
                bt = block.type
                type_counts[bt] = type_counts.get(bt, 0) + 1

    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

    result = {
        "conversation_count": len(conversations),
        "message_count": total_messages,
        "human_messages": total_human,
        "assistant_messages": total_assistant,
        "system_messages": total_system,
        "content_types": [{"type": t, "count": c} for t, c in sorted_types],
    }

    # 统计 CC 格式的会话数
    cc_count = sum(1 for c in conversations if c.source_format == "claude_code")
    if cc_count > 0:
        result["claude_code_sessions"] = cc_count

    return jsonify(result)


@app.route("/api/profile")
def api_profile():
    """返回用户画像（memories.json 中的 conversations_memory）"""
    if not user_profile:
        return jsonify({"error": "未找到用户画像数据"}), 404

    return jsonify({
        "has_profile": True,
        "profile_markdown": user_profile.get("conversations_memory", ""),
        "account_uuid": user_profile.get("account_uuid", ""),
    })


@app.route("/api/conv/<conv_uuid>/search")
def api_conv_search(conv_uuid: str):
    """服务端深度全文搜索 —— 扫描消息的全部内容块

    接受 ?q=关键词，返回匹配消息的 UUID 列表 + 上下文片段
    用于客户端 preview 索引搜不到时的兜底
    """
    conv = _find_conversation(conv_uuid)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404

    query = request.args.get("q", "").strip().lower()
    if not query or len(query) < 1:
        return jsonify({"results": [], "total": 0})

    PAGE_SIZE = 50
    results = []
    for i, msg in enumerate(conv.messages):
        fulltext = _get_message_fulltext(msg)
        if not fulltext:
            continue

        idx = fulltext.lower().find(query)
        if idx < 0:
            continue

        # 提取匹配上下文片段（关键词前后各 60 字符）
        start = max(0, idx - 60)
        end = min(len(fulltext), idx + len(query) + 60)
        snippet = fulltext[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(fulltext):
            snippet += "…"

        results.append({
            "uuid": msg.uuid,
            "sender": msg.sender,
            "preview": snippet,
            "page": i // PAGE_SIZE,
        })

    # 保持对话原始顺序（遍历时已是顺序追加，无需重排）

    # 限制返回数量，避免客户端处理压力
    return jsonify({
        "results": results[:200],
        "total": len(results),
    })


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _find_conversation(uuid: str) -> Conversation | None:
    """按 UUID 查找对话（O(1) 索引查找）"""
    return _conversation_index.get(uuid)


def _get_message_preview(msg, max_len: int = 800) -> str:
    """从消息中提取纯文本预览 —— 拼接所有内容块，不遗漏后半段文本

    Args:
        msg: ChatMessage 对象
        max_len: 最大字符数（默认 800，覆盖大部分消息全文）

    Returns:
        纯文本预览字符串
    """
    # 优先从 text 字段提取
    if msg.text:
        text = msg.text.strip()
        if text:
            if text.startswith("/"):
                return text[:max_len] + "…" if len(text) > max_len else text
            return text[:max_len] + "…" if len(text) > max_len else text

    # 拼接所有内容块的文本（不再只取第一个）
    parts = []
    for block in msg.content_blocks:
        if block.type == "text" and block.text:
            parts.append(block.text.strip())
        elif block.type == "thinking" and block.thinking:
            parts.append(block.thinking.strip())
        elif block.type == "tool_use" and block.tool_name:
            parts.append(f"[{block.tool_name}]")
            if block.tool_input:
                # 工具输入参数中也包含可搜索的关键信息
                try:
                    import json as _json
                    input_str = _json.dumps(block.tool_input, ensure_ascii=False)
                    parts.append(input_str)
                except Exception:
                    pass
        elif block.type == "tool_result":
            if block.tool_result_text:
                parts.append(block.tool_result_text.strip())
            if block.tool_result_file and isinstance(block.tool_result_file, dict):
                content = block.tool_result_file.get("content", "")
                if content:
                    parts.append(content.strip())
        elif block.type == "meta_event" and block.flag_text:
            parts.append(block.flag_text)

    full_text = " ".join(parts)
    if full_text:
        return full_text[:max_len] + "…" if len(full_text) > max_len else full_text

    # 对于系统消息，直接返回 text
    if msg.sender == "system" and msg.text:
        return msg.text[:max_len] + "…" if len(msg.text) > max_len else msg.text

    return ""


def _get_message_fulltext(msg) -> str:
    """提取消息全部可搜索文本（不截断），供服务端深度搜索使用

    注意：不能简单用 msg.text 提前 return，因为 assistant 消息的 msg.text
    只包含第一个文本块（parser 只取了首个 text block），工具调用之后的文本全部丢失。
    必须遍历所有 content_blocks 拼接全量文本。
    """
    # 人类消息：msg.text 即完整输入，content_blocks 通常为空
    if msg.sender == "human" and msg.text:
        return msg.text.strip()

    # 系统/meta 消息：text 字段即全文
    if msg.sender in ("system", "meta") and msg.text:
        return msg.text.strip()

    # assistant 消息及所有其他情况：遍历全部 content_blocks
    parts = []
    if msg.text and msg.text.strip():
        parts.append(msg.text.strip())

    for block in msg.content_blocks:
        if block.type == "text" and block.text:
            parts.append(block.text)
        elif block.type == "thinking" and block.thinking:
            parts.append(block.thinking)
        elif block.type == "tool_use":
            if block.tool_name:
                parts.append(block.tool_name)
            if block.tool_input:
                try:
                    import json as _json
                    parts.append(_json.dumps(block.tool_input, ensure_ascii=False))
                except Exception:
                    pass
        elif block.type == "tool_result":
            if block.tool_result_text:
                parts.append(block.tool_result_text)
            if block.tool_result_file and isinstance(block.tool_result_file, dict):
                content = block.tool_result_file.get("content", "")
                if content:
                    parts.append(content)
        elif block.type == "meta_event" and block.flag_text:
            parts.append(block.flag_text)

    return " ".join(parts)


def _load_memories(memories_path: str) -> dict:
    """加载 memories.json，返回用户画像数据"""
    try:
        with open(memories_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list) and len(raw) > 0:
            return raw[0]
        elif isinstance(raw, dict):
            return raw
    except Exception as e:
        print(f"[WARN] 加载用户画像失败: {e}")
    return {}


def _auto_load():
    """启动时自动加载 chat_history 目录下的数据"""
    global conversations, user_profile, _conversation_index

    base_dir = os.path.dirname(os.path.abspath(__file__))
    chat_dir = os.path.join(base_dir, "chat_history")

    if not os.path.isdir(chat_dir):
        return

    # 加载对话数据（支持 .json 和 .jsonl）
    all_convs = []

    # 1. 加载标准 conversations.json
    conv_path = os.path.join(chat_dir, "conversations.json")
    if os.path.exists(conv_path):
        print(f"[INFO] 自动加载: {conv_path}")
        convs = load_conversations_safe(conv_path)
        all_convs.extend(convs)
        print(f"[INFO]   加载了 {len(convs)} 个对话")

    # 2. 加载所有 .jsonl 文件
    try:
        for entry in os.listdir(chat_dir):
            if entry.endswith(".jsonl"):
                jsonl_path = os.path.join(chat_dir, entry)
                print(f"[INFO] 自动加载 JSONL: {jsonl_path}")
                convs = load_conversations_safe(jsonl_path)
                all_convs.extend(convs)
                print(f"[INFO]   加载了 {len(convs)} 个会话")
    except Exception as e:
        print(f"[WARN] 扫描 JSONL 文件失败: {e}")

    conversations = all_convs
    _conversation_index = {c.uuid: c for c in conversations}

    # 加载用户画像
    mem_path = os.path.join(chat_dir, "memories.json")
    if os.path.exists(mem_path):
        print(f"[INFO] 加载用户画像: {mem_path}")
        user_profile = _load_memories(mem_path)


# ═══════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════

def _port_is_free(host: str, port: int) -> bool:
    """检测端口是否空闲（尝试连接，连得上说明被占用）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _kill_old_process(host: str, port: int) -> bool:
    """杀掉占用指定端口的进程，成功返回 True"""
    try:
        if sys.platform == 'win32':
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split('\n'):
                if f'{host}:{port}' in line and 'LISTENING' in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    subprocess.run(
                        ['taskkill', '/f', '/pid', pid],
                        capture_output=True, timeout=5
                    )
                    print(f"[OK] 已停止旧进程 (PID: {pid})")
                    return True
        else:
            result = subprocess.run(
                ['lsof', '-ti', f'tcp:{port}'], capture_output=True, text=True, timeout=5
            )
            pid = result.stdout.strip()
            if pid:
                os.kill(int(pid), signal.SIGTERM)
                print(f"[OK] 已停止旧进程 (PID: {pid})")
                return True
    except Exception as e:
        print(f"[WARN] 无法停止旧进程: {e}")
    return False


def _handle_port_conflict(host: str, port: int, url: str) -> bool:
    """端口被占用时的处理——提示用户选择
    返回 True 表示要启动新服务，False 表示只打开浏览器
    """
    print(f"[INFO] 端口 {port} 已被占用")
    print(f"  [R] 重启服务（加载新代码）")
    print(f"  [Enter] 打开浏览器（连到已有服务）")
    try:
        choice = input("  请选择: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        # 无法交互（如被管道调用），默认重启
        choice = 'r'

    if choice == 'r':
        print("[INFO] 正在停止旧服务...")
        if _kill_old_process(host, port):
            import time
            time.sleep(0.5)  # 等端口释放
            return True
        else:
            print("[WARN] 无法自动停止，请手动关闭后重试")
            return False
    else:
        print("[INFO] 打开浏览器连接到已有服务...")
        webbrowser.open(url)
        return False


def _print_banner(url: str):
    """打印启动横幅"""
    banner = f"""
╔══════════════════════════════════════════╗
║     Claude 对话浏览器                    ║
╠══════════════════════════════════════════╣
║     >>> {url}                <<<
║                                          ║
║  在浏览器中拖拽 conversations.json        ║
║  或 .jsonl 文件即可开始浏览对话            ║
║  支持 Claude.ai / Claude Code 格式        ║
╚══════════════════════════════════════════╝
"""
    try:
        print(banner)
    except UnicodeEncodeError:
        print("=" * 50)
        print("  Claude Conversation Viewer")
        print(f"  Open: {url}")
        print("=" * 50)


def main():
    host = "127.0.0.1"
    port = 5000
    url = f"http://{host}:{port}"
    auto_restart = '--restart' in sys.argv  # 命令行加 --restart 则自动杀旧启新

    # 修复 Windows 控制台编码问题
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    # ── 端口检测（先检测，避免浪费加载时间）──
    if not _port_is_free(host, port):
        if auto_restart:
            print(f"[INFO] 端口 {port} 已被占用，--restart 模式：自动停止旧进程...")
            if _kill_old_process(host, port):
                import time; time.sleep(0.5)
            else:
                print("[ERROR] 无法停止旧进程，启动失败")
                return
        elif not _handle_port_conflict(host, port, url):
            return  # 用户选择打开浏览器，退出

    # 自动加载数据
    _auto_load()

    _print_banner(url)

    if conversations:
        total_msgs = sum(c.message_count for c in conversations)
        cc_count = sum(1 for c in conversations if c.source_format == "claude_code")
        ai_count = len(conversations) - cc_count
        parts = [f"{len(conversations)} 个对话 ({total_msgs} 条消息)"]
        if ai_count:
            parts.append(f"{ai_count} 个 Claude.ai 对话")
        if cc_count:
            parts.append(f"{cc_count} 个 Claude Code 会话")
        print(f"[OK] 已加载 " + ", ".join(parts))
    if user_profile:
        print("[OK] 已加载用户画像")

    print("[INFO] 服务启动中...")
    webbrowser.open(url)
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
