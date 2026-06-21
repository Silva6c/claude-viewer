"""Claude 对话浏览器 —— Flask Web 应用

启动后在浏览器中打开图形界面，支持:
- 自动加载 chat_history/conversations.json
- 拖拽或浏览选择 conversations.json
- 侧边栏对话列表，支持搜索
- 一问一答格式查看对话
- Thinking 块默认折叠
- 代码语法高亮
- 亮/暗主题切换
- 用户画像（memories.json）
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
from src.content_renderer import render_message_html
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
    """接收上传的 JSON 文件并解析"""
    global conversations

    if "file" not in request.files:
        return jsonify({"error": "未收到文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    with tempfile.NamedTemporaryFile(mode='wb', suffix='.json', delete=False) as tmp:
        file.save(tmp.name)
        temp_path = tmp.name

    try:
        conversations = load_conversations_safe(temp_path)
        global _conversation_index
        _conversation_index = {c.uuid: c for c in conversations}
        total_messages = sum(c.message_count for c in conversations)

        return jsonify({
            "success": True,
            "conversation_count": len(conversations),
            "message_count": total_messages,
            "filename": file.filename,
        })
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
        result.append({
            "uuid": conv.uuid,
            "name": conv.name,
            "summary": safe_truncate(conv.summary, 200) if conv.summary else "",
            "created_at": format_timestamp(conv.created_at),
            "updated_at": format_timestamp(conv.updated_at),
            "date": extract_date(conv.updated_at),
            "message_count": conv.message_count,
        })

    result.sort(key=lambda c: c["updated_at"] or c["created_at"], reverse=True)

    return jsonify({
        "conversations": result,
        "total": len(result),
        "has_profile": bool(user_profile),
    })


@app.route("/api/conv/<conv_uuid>")
def api_conversation(conv_uuid: str):
    """返回单个对话的完整数据（含渲染后的 HTML）"""
    conv = _find_conversation(conv_uuid)
    if not conv:
        return jsonify({"error": "对话不存在"}), 404

    messages = []
    for msg in conv.messages:
        rendered_html = render_message_html(
            sender=msg.sender,
            content_blocks=msg.content_blocks,
            fallback_text=msg.text,
        )

        messages.append({
            "uuid": msg.uuid,
            "sender": msg.sender,
            "created_at": format_timestamp(msg.created_at),
            "rendered_html": rendered_html,
        })

    return jsonify({
        "uuid": conv.uuid,
        "name": conv.name,
        "summary": conv.summary,
        "created_at": format_timestamp(conv.created_at),
        "updated_at": format_timestamp(conv.updated_at),
        "message_count": conv.message_count,
        "messages": messages,
    })


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
    """搜索对话（按标题和摘要模糊匹配）"""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": [], "total": 0})

    results = []
    for conv in conversations:
        name_lower = conv.name.lower()
        summary_lower = conv.summary.lower() if conv.summary else ""

        if query in name_lower or query in summary_lower:
            results.append({
                "uuid": conv.uuid,
                "name": conv.name,
                "summary": safe_truncate(conv.summary, 200) if conv.summary else "",
                "updated_at": format_timestamp(conv.updated_at),
                "date": extract_date(conv.updated_at),
                "message_count": conv.message_count,
                "match_in": "title" if query in name_lower else "summary",
            })

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

    type_counts = {}
    for conv in conversations:
        for msg in conv.messages:
            for block in msg.content_blocks:
                bt = block.type
                type_counts[bt] = type_counts.get(bt, 0) + 1

    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)

    return jsonify({
        "conversation_count": len(conversations),
        "message_count": total_messages,
        "human_messages": total_human,
        "assistant_messages": total_assistant,
        "content_types": [{"type": t, "count": c} for t, c in sorted_types],
    })


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


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _find_conversation(uuid: str) -> Conversation | None:
    """按 UUID 查找对话（O(1) 索引查找）"""
    return _conversation_index.get(uuid)


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

    # 加载对话数据
    conv_path = os.path.join(chat_dir, "conversations.json")
    if os.path.exists(conv_path):
        print(f"[INFO] 自动加载: {conv_path}")
        conversations = load_conversations_safe(conv_path)
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
║  即可开始浏览对话                          ║
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
        print(f"[OK] 已加载 {len(conversations)} 个对话 ({total_msgs} 条消息)")
    if user_profile:
        print("[OK] 已加载用户画像")

    print("[INFO] 服务启动中...")
    webbrowser.open(url)
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
