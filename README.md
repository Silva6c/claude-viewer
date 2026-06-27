# Claude 对话浏览器

将 Claude.ai / Claude Code 导出的对话数据转换为美观的一问一答 Web 界面。

## 功能

- 🌐 **Web 图形界面** —— 浏览器中浏览，类似 Claude 网页版体验
- 📂 **拖拽上传** —— 支持 `.json` (Claude.ai) 和 `.jsonl` (Claude Code) 两种格式
- 💬 **一问一答格式** —— You / Claude 气泡式对话（绿色人类气泡）
- 💭 **Thinking 折叠** —— 思考过程默认折叠，点击展开
- 🔧 **工具调用卡片** —— 工具使用和结果显示为卡片
- 🎨 **代码高亮** —— 自动语法高亮（highlight.js）
- 🌙 **亮/暗主题** —— 一键切换，大 DOM 下已极致优化
- 🔍 **全局搜索** —— 按标题和摘要模糊搜索对话
- 🔎 **对话内搜索** —— 在当前对话内全文搜索，气泡级导航
- ☰ **消息导航** —— 数据驱动的消息大纲，支持 1700+ 条消息流畅跳转
- 📥 **加载全部** —— 分块渐进渲染，加载 1700+ 条消息不卡顿
- 📄 **Markdown 导出** —— 一键导出当前对话
- ⌨️ **键盘快捷键** —— `Ctrl+K` 搜索，`↑↓` 导航

## 快速开始

```bash
# 1. 安装依赖
pip install flask

# 2. 启动应用
python app.py

# 3. 浏览器自动打开 http://localhost:5000
# 4. 拖入 conversations.json 或 .jsonl 即可浏览
```

## 获取对话数据

**Claude.ai**:
1. 打开 [claude.ai](https://claude.ai) → 左下角头像 → **Settings**
2. **Privacy** → **Export Data** → 下载 ZIP
3. 解压得到 `conversations.json`

**Claude Code**:
- `.jsonl` 文件直接拖入即可，自动识别

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+K` | 聚焦搜索框 |
| `↑` `↓` | 对话内搜索：在匹配结果间跳转 |
| `Esc` | 清除搜索 |
