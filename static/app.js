/* ═══════════════════════════════════════════
   Claude 对话浏览器 —— 前端交互逻辑
   纯 Vanilla JS，零框架依赖
   ═══════════════════════════════════════════ */

// ── 全局状态 ──
const state = {
    conversations: [],       // 对话列表
    currentConvUuid: null,   // 当前选中的对话 UUID
    theme: 'light',          // 当前主题
    searchQuery: '',         // 当前搜索词
};

// ── DOM 缓存 ──
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    dropZone: $('#drop-zone'),
    fileInput: $('#file-input'),
    fileInput2: $('#file-input-2'),
    loadingOverlay: $('#loading-overlay'),
    loadingText: $('#loading-text'),
    app: $('#app'),
    sidebar: $('#sidebar'),
    searchBox: $('#search-box'),
    sidebarStats: $('#sidebar-stats'),
    conversationList: $('#conversation-list'),
    btnTheme: $('#btn-theme'),
    btnNewFile: $('#btn-new-file'),
    btnProfile: $('#btn-profile'),
    profileModal: $('#profile-modal'),
    profileContent: $('#profile-content'),
    welcomeMessage: $('#welcome-message'),
    totalCount: $('#total-count'),
    conversationView: $('#conversation-view'),
    convTitle: $('#conv-title'),
    convMeta: $('#conv-meta'),
    convSummary: $('#conv-summary'),
    convSummaryBody: $('#conv-summary-body'),
    btnSummaryToggle: $('#btn-summary-toggle'),
    btnExport: $('#btn-export'),
    btnOutline: $('#btn-outline'),
    outlinePanel: $('#outline-panel'),
    outlineList: $('#outline-list'),
    messageList: $('#message-list'),
    btnBack: $('#btn-back'),
};


// ═══════════════════════════════════════════
// 文件处理
// ═══════════════════════════════════════════

// 拖拽事件
document.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dom.dropZone.classList.add('drag-over');
});

document.addEventListener('dragleave', (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.target === document.documentElement || e.target === document.body) {
        dom.dropZone.classList.remove('drag-over');
    }
});

document.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    dom.dropZone.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        handleFile(file);
    }
}

function handleFile(file) {
    if (!file.name.endsWith('.json')) {
        alert('请选择 .json 文件（conversations.json）');
        return;
    }
    uploadFile(file);
}

async function uploadFile(file) {
    showLoading('正在解析 JSON...');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });

        const data = await resp.json();

        if (data.error) {
            throw new Error(data.error);
        }

        // 加载成功
        hideLoading();
        dom.dropZone.style.display = 'none';
        dom.app.style.display = 'flex';

        // 加载对话列表
        await loadConversationList();

        console.log(`✅ 已加载 ${data.conversation_count} 个对话, ${data.message_count} 条消息`);

    } catch (err) {
        hideLoading();
        alert('解析失败: ' + err.message);
        console.error(err);
    }
}

function showLoading(text) {
    dom.loadingText.textContent = text || '正在解析 JSON...';
    dom.loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    dom.loadingOverlay.style.display = 'none';
}


// ═══════════════════════════════════════════
// 对话列表
// ═══════════════════════════════════════════

async function loadConversationList() {
    try {
        const resp = await fetch('/api/list');
        const data = await resp.json();
        applyListData(data);
    } catch (err) {
        console.error('加载对话列表失败:', err);
    }
}

function renderConversationList(conversations) {
    dom.conversationList.innerHTML = '';

    if (conversations.length === 0) {
        dom.conversationList.innerHTML = '<div style="padding:1rem;color:var(--text-muted);text-align:center;">没有找到对话</div>';
        return;
    }

    conversations.forEach(conv => {
        const item = document.createElement('button');
        item.className = 'conversation-item';
        item.dataset.uuid = conv.uuid;

        if (conv.uuid === state.currentConvUuid) {
            item.classList.add('active');
        }

        const title = highlightMatch(conv.name, state.searchQuery);

        item.innerHTML = `
            <span class="conv-item-title">${title}</span>
            <span class="conv-item-meta">${conv.date} · ${conv.message_count} 条消息</span>
        `;

        item.addEventListener('click', () => loadConversation(conv.uuid));
        dom.conversationList.appendChild(item);
    });
}

function highlightMatch(text, query) {
    if (!query || !text) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}


// ═══════════════════════════════════════════
// 对话加载与渲染
// ═══════════════════════════════════════════

async function loadConversation(uuid) {
    state.currentConvUuid = uuid;

    // 更新侧边栏高亮
    $$('.conversation-item').forEach(item => {
        item.classList.toggle('active', item.dataset.uuid === uuid);
    });

    // 显示加载状态
    dom.welcomeMessage.style.display = 'none';
    dom.conversationView.style.display = 'block';
    dom.messageList.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted);">加载中...</div>';

    // 移动端：隐藏侧边栏
    if (window.innerWidth <= 768) {
        dom.sidebar.classList.add('sidebar-hidden');
    }

    try {
        const resp = await fetch(`/api/conv/${uuid}`);
        const data = await resp.json();

        if (data.error) {
            throw new Error(data.error);
        }

        renderConversation(data);

    } catch (err) {
        dom.messageList.innerHTML = `<div style="text-align:center;padding:2rem;color:#ef4444;">加载失败: ${escapeHtml(err.message)}</div>`;
        console.error(err);
    }
}

function renderConversation(conv) {
    // 头部
    dom.convTitle.textContent = conv.name;
    dom.convMeta.textContent = `${conv.created_at} · ${conv.message_count} 条消息`;
    // 存下 UUID 供导出按钮使用
    dom.conversationView.dataset.uuid = conv.uuid;

    // 摘要 —— 折叠为一行，点击展开
    if (conv.summary) {
        dom.convSummary.style.display = 'block';
        dom.convSummary.dataset.expanded = 'false';
        dom.convSummaryBody.innerHTML = marked.parse(conv.summary);
        dom.btnSummaryToggle.style.display = 'flex';
        dom.btnSummaryToggle.onclick = toggleSummary;
    } else {
        dom.convSummary.style.display = 'none';
    }

    // 消息列表
    dom.messageList.innerHTML = '';
    conv.messages.forEach(msg => {
        const msgEl = createMessageElement(msg);
        dom.messageList.appendChild(msgEl);
    });

    // 渲染后处理
    postRenderProcessing();
    // 构建消息导航
    buildOutline(conv.messages);

    // 滚动到顶部
    dom.conversationView.scrollIntoView({ behavior: 'smooth' });
}

function createMessageElement(msg) {
    const wrapper = document.createElement('div');
    wrapper.className = `message message-${msg.sender}`;

    const roleLabel = msg.sender === 'human' ? 'You' : 'Claude';
    const timeStr = msg.created_at || '';

    wrapper.innerHTML = `
        <div class="message-header">
            <span class="message-role">${roleLabel}</span>
            <span class="message-time">${timeStr}</span>
        </div>
        <div class="message-body">${msg.rendered_html}</div>
    `;

    return wrapper;
}

function postRenderProcessing() {
    // 用 marked.js 渲染 Markdown 内容块（统一处理文本/思考/知识库）
    ['.text-block', '.thinking-content', '.knowledge-text'].forEach(sel => {
        $$(sel).forEach(block => {
            const decoded = decodeHtmlEntities(block.innerHTML);
            if (decoded.trim()) {
                block.innerHTML = marked.parse(decoded);
            }
        });
    });

    // 4. 用 highlight.js 高亮代码块 + 添加复制按钮
    $$('pre').forEach(pre => {
        // 跳过已经在 wrapper 里的
        if (pre.parentElement.classList.contains('code-block-wrapper')) return;

        const code = pre.querySelector('code');
        if (code) {
            // 解码 HTML 实体
            const decoded = decodeHtmlEntities(code.innerHTML);
            code.innerHTML = decoded;
            code.removeAttribute('data-highlighted');
            hljs.highlightElement(code);
        }

        // 包裹 pre 并添加复制按钮
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper';
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);

        const btn = document.createElement('button');
        btn.className = 'btn-copy';
        btn.textContent = '📋 复制';
        btn.addEventListener('click', function() {
            const text = pre.textContent || '';
            navigator.clipboard.writeText(text).then(() => {
                btn.textContent = '✅ 已复制';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = '📋 复制';
                    btn.classList.remove('copied');
                }, 2000);
            }).catch(() => {
                // fallback
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                btn.textContent = '✅ 已复制';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = '📋 复制';
                    btn.classList.remove('copied');
                }, 2000);
            });
        });
        wrapper.appendChild(btn);
    });

    // 5. 处理外部链接（新窗口打开）
    $$('.message-body a[href^="http"]').forEach(link => {
        link.setAttribute('target', '_blank');
        link.setAttribute('rel', 'noopener noreferrer');
    });
}

const _decodeTextarea = document.createElement('textarea');
function decodeHtmlEntities(html) {
    _decodeTextarea.innerHTML = html;
    return _decodeTextarea.value;
}


// ═══════════════════════════════════════════
// 搜索
// ═══════════════════════════════════════════

dom.searchBox.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.trim().toLowerCase();
    filterConversations();
});

function filterConversations() {
    const query = state.searchQuery;

    if (!query) {
        renderConversationList(state.conversations);
        return;
    }

    const filtered = state.conversations.filter(conv => {
        const name = (conv.name || '').toLowerCase();
        const summary = (conv.summary || '').toLowerCase();
        return name.includes(query) || summary.includes(query);
    });

    renderConversationList(filtered);
}


// ═══════════════════════════════════════════
// 主题切换
// ═══════════════════════════════════════════

dom.btnTheme.addEventListener('click', toggleTheme);

function toggleTheme() {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    applyTheme();
    localStorage.setItem('claude-viewer-theme', state.theme);
}

const HL_THEMES = {
    light: 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css',
    dark: 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css',
};

function applyTheme() {
    document.documentElement.setAttribute('data-theme', state.theme);
    dom.btnTheme.textContent = state.theme === 'light' ? '🌙' : '☀️';

    const hlTheme = document.querySelector('link[href*="highlight.js"]');
    if (hlTheme) {
        hlTheme.href = HL_THEMES[state.theme] || HL_THEMES.dark;
    }
}

// 初始化主题（从 localStorage 读取）
function initTheme() {
    const saved = localStorage.getItem('claude-viewer-theme');
    if (saved === 'dark') {
        state.theme = 'dark';
    }
    applyTheme();
}


// ═══════════════════════════════════════════
// 摘要折叠
// ═══════════════════════════════════════════

function toggleSummary() {
    const expanded = dom.convSummary.dataset.expanded === 'true';
    dom.convSummary.dataset.expanded = expanded ? 'false' : 'true';
}


// ═══════════════════════════════════════════
// 导出对话
// ═══════════════════════════════════════════

dom.btnExport.addEventListener('click', exportConversation);

function exportConversation() {
    const uuid = dom.conversationView.dataset.uuid;
    if (!uuid) return;

    // 直接触发下载
    const a = document.createElement('a');
    a.href = `/api/conv/${uuid}/export`;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // 按钮反馈
    dom.btnExport.textContent = '✅';
    setTimeout(() => { dom.btnExport.textContent = '📄'; }, 1500);
}


// ═══════════════════════════════════════════
// 消息导航面板
// ═══════════════════════════════════════════

let outlineObserver = null;

dom.btnOutline.addEventListener('click', toggleOutline);

function toggleOutline() {
    const visible = dom.outlinePanel.style.display === 'flex';
    if (visible) {
        closeOutline();
    } else {
        dom.outlinePanel.style.display = 'flex';
        dom.btnOutline.style.background = 'var(--bg-hover)';
        // 高亮当前可见消息
        updateOutlineActive();
    }
}

function closeOutline() {
    dom.outlinePanel.style.display = 'none';
    dom.btnOutline.style.background = '';
}

function buildOutline(messages) {
    dom.outlineList.innerHTML = '';

    messages.forEach((msg, index) => {
        const item = document.createElement('button');
        item.className = 'outline-item';
        item.dataset.index = index;

        const roleLabel = msg.sender === 'human' ? 'You' : 'Claude';
        const roleClass = msg.sender === 'human' ? 'role-human' : 'role-assistant';

        // 提取消息预览文本
        const preview = extractPreview(msg.rendered_html);

        item.innerHTML = `
            <span class="outline-role ${roleClass}">${roleLabel}</span>
            <span class="outline-preview">${escapeHtml(preview)}</span>
            <span class="outline-time">${msg.created_at || ''}</span>
        `;

        item.addEventListener('click', () => scrollToMessage(index));
        dom.outlineList.appendChild(item);
    });

    // 设置滚动监听（每次重建 outline 时重新绑定）
    if (outlineObserver) {
        outlineObserver.disconnect();
    }
    setupScrollSpy();
}

function extractPreview(html) {
    // 从渲染的 HTML 中提取纯文本预览
    if (!html) return '';
    const div = document.createElement('div');
    div.innerHTML = html;
    // 跳过 thinking 和 tool 块
    const skips = div.querySelectorAll('.thinking-block, .tool-card, .thinking-content, pre');
    skips.forEach(el => el.remove());
    const text = div.textContent || '';
    return text.replace(/\s+/g, ' ').trim().substring(0, 80);
}

function scrollToMessage(index) {
    const messages = $$('.message');
    if (messages[index]) {
        messages[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
        // 更新高亮
        updateOutlineActive(index);
    }
}

function setupScrollSpy() {
    // 使用 IntersectionObserver 监听消息块
    outlineObserver = new IntersectionObserver((entries) => {
        // 找第一个可见的消息
        let firstVisible = null;
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const idx = Array.from($$('.message')).indexOf(entry.target);
                if (idx !== -1 && (firstVisible === null || idx < firstVisible)) {
                    firstVisible = idx;
                }
            }
        });
        if (firstVisible !== null) {
            updateOutlineActive(firstVisible);
        }
    }, {
        root: null,
        threshold: 0.3,
        rootMargin: '-60px 0px 0px 0px',
    });

    // 观察所有消息
    $$('.message').forEach(msg => outlineObserver.observe(msg));
}

function updateOutlineActive(index) {
    const items = $$('.outline-item');
    items.forEach((item, i) => {
        if (index !== undefined) {
            item.classList.toggle('active', i === index);
        } else {
            // 自动检测：找第一个在视口中的消息
            const msgEl = $$('.message')[i];
            if (!msgEl) return;
            const rect = msgEl.getBoundingClientRect();
            const visible = rect.top < window.innerHeight * 0.6 && rect.bottom > 60;
            item.classList.toggle('active', visible);
        }
    });
}


// ═══════════════════════════════════════════
// 新文件 / 返回
// ═══════════════════════════════════════════

dom.btnNewFile.addEventListener('click', () => {
    dom.fileInput2.click();
});

dom.btnBack.addEventListener('click', () => {
    dom.welcomeMessage.style.display = 'flex';
    dom.conversationView.style.display = 'none';
    state.currentConvUuid = null;

    // 清除侧边栏高亮
    $$('.conversation-item').forEach(item => item.classList.remove('active'));

    // 移动端：显示侧边栏
    if (window.innerWidth <= 768) {
        dom.sidebar.classList.remove('sidebar-hidden');
    }
});


// ═══════════════════════════════════════════
// 用户画像
// ═══════════════════════════════════════════

dom.btnProfile.addEventListener('click', openProfile);

async function openProfile() {
    dom.profileModal.style.display = 'flex';
    dom.profileContent.innerHTML = '<div style="text-align:center;padding:2rem;"><div class="spinner"></div></div>';

    try {
        const resp = await fetch('/api/profile');
        const data = await resp.json();

        if (data.error) {
            dom.profileContent.innerHTML = `<p style="color:var(--text-muted)">${escapeHtml(data.error)}</p>`;
            return;
        }

        // 用 marked.js 渲染 Markdown
        dom.profileContent.innerHTML = marked.parse(data.profile_markdown || '');

    } catch (err) {
        dom.profileContent.innerHTML = `<p style="color:#ef4444">加载失败: ${escapeHtml(err.message)}</p>`;
    }
}

function closeProfile() {
    dom.profileModal.style.display = 'none';
}

// 点击遮罩关闭
dom.profileModal.addEventListener('click', (e) => {
    if (e.target === dom.profileModal) {
        closeProfile();
    }
});


// ═══════════════════════════════════════════
// 键盘快捷键
// ═══════════════════════════════════════════

document.addEventListener('keydown', (e) => {
    // Ctrl+K / Cmd+K: 聚焦搜索框
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        dom.searchBox.focus();
        dom.searchBox.select();
    }

    // Escape: 关闭模态窗 / 清除搜索
    if (e.key === 'Escape') {
        if (dom.profileModal.style.display === 'flex') {
            closeProfile();
            return;
        }
        if (document.activeElement === dom.searchBox) {
            dom.searchBox.value = '';
            state.searchQuery = '';
            filterConversations();
            dom.searchBox.blur();
        }
    }

    // ↑↓: 在对话列表中导航（当搜索框未聚焦时）
    if (['ArrowUp', 'ArrowDown'].includes(e.key) && document.activeElement !== dom.searchBox) {
        e.preventDefault();
        navigateConversationList(e.key === 'ArrowDown' ? 1 : -1);
    }
});

function navigateConversationList(direction) {
    const items = $$('.conversation-item');
    if (items.length === 0) return;

    const currentIndex = Array.from(items).findIndex(
        item => item.dataset.uuid === state.currentConvUuid
    );

    let newIndex;
    if (currentIndex === -1) {
        newIndex = direction > 0 ? 0 : items.length - 1;
    } else {
        newIndex = currentIndex + direction;
        if (newIndex < 0) newIndex = items.length - 1;
        if (newIndex >= items.length) newIndex = 0;
    }

    const item = items[newIndex];
    if (item) {
        loadConversation(item.dataset.uuid);
        item.scrollIntoView({ block: 'nearest' });
    }
}


// ═══════════════════════════════════════════
// 窗口大小响应
// ═══════════════════════════════════════════

window.addEventListener('resize', () => {
    if (window.innerWidth > 768) {
        dom.sidebar.classList.remove('sidebar-hidden');
        dom.btnBack.style.display = 'none';
    } else {
        dom.btnBack.style.display = 'flex';
    }
});


// ═══════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════

function init() {
    initTheme();

    // 配置 marked.js
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            breaks: true,
            gfm: true,
            headerIds: false,
            mangle: false,
        });
    }

    // 移动端返回按钮初始隐藏
    if (window.innerWidth <= 768) {
        dom.btnBack.style.display = 'flex';
    }

    // 尝试自动加载（后端可能已加载 chat_history 目录）
    autoLoad();
}

function applyListData(data) {
    state.conversations = data.conversations;
    renderConversationList(state.conversations);
    dom.sidebarStats.textContent = `共 ${data.total} 个对话`;
    dom.totalCount.textContent = data.total;
    if (data.has_profile && dom.btnProfile) {
        dom.btnProfile.style.display = 'flex';
    }
}

async function autoLoad() {
    try {
        const resp = await fetch('/api/list');
        const data = await resp.json();

        if (data.total > 0) {
            dom.dropZone.style.display = 'none';
            dom.app.style.display = 'flex';
            applyListData(data);
            console.log(`[auto] 已加载 ${data.total} 个对话`);
        } else {
            dom.dropZone.style.display = 'flex';
            dom.app.style.display = 'none';
            console.log('[auto] 无预加载数据，等待用户上传');
        }
    } catch (err) {
        dom.dropZone.style.display = 'flex';
        dom.app.style.display = 'none';
    }
}

// 启动
document.addEventListener('DOMContentLoaded', init);
