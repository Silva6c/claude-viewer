# Claude 对话浏览器

将 Claude.ai 导出的 `conversations.json` 转换为美观的一问一答 Web 界面。

## 功能

- 🌐 **Web 图形界面** —— 浏览器中浏览，类似 Claude 网页版体验
- 📂 **拖拽上传** —— 拖拽 JSON 文件到页面，或点击选择文件
- 💬 **一问一答格式** —— You / Claude 气泡式对话
- 💭 **Thinking 折叠** —— 思考过程默认折叠，点击展开
- 🔧 **工具调用卡片** —— 工具使用和结果显示为卡片
- 🎨 **代码高亮** —— 自动语法高亮（highlight.js）
- 🌙 **亮/暗主题** —— 一键切换
- 🔍 **搜索对话** —— 按标题和摘要模糊搜索
- ⌨️ **键盘快捷键** —— `Ctrl+K` 搜索，`↑↓` 导航对话

## 快速开始

```bash
# 1. 安装依赖
pip install flask

# 2. 启动应用
python app.py

# 3. 浏览器自动打开 http://localhost:5000
# 4. 拖入 conversations.json 即可浏览
```

## 获取 conversations.json

1. 打开 [claude.ai](https://claude.ai)
2. 点击左下角头像 → **Settings**（设置）
3. 点击 **Privacy**（隐私）→ **Export Data**（导出数据）
4. 等待处理完成后下载 ZIP 文件
5. 解压得到 `conversations.json`

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+K` | 聚焦搜索框 |
| `↑` `↓` | 上下导航对话 |
| `Esc` | 清除搜索 |

## 文件结构

```
json_reader/
├── app.py                      # Flask 入口
├── requirements.txt            # Python 依赖
├── README.md                   # 本文件
├── src/
│   ├── models.py               # 数据模型
│   ├── parser.py               # JSON 解析
│   ├── content_renderer.py     # 内容块渲染
│   └── utils.py                # 工具函数
├── static/
│   ├── style.css               # 样式表
│   └── app.js                  # 前端逻辑
└── templates/
    └── index.html              # 页面模板
```
