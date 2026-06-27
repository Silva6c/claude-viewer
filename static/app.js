/* ═══════════════════════════════════════════
   Claude 对话浏览器 —— 前端交互逻辑
   纯 Vanilla JS，零框架依赖
   支持 Claude.ai / Claude Code 两种数据源
   ═══════════════════════════════════════════ */

// ── 全局状态 ──
const state = {
    conversations: [],       // 对话列表
    currentConvUuid: null,   // 当前选中的对话 UUID
    theme: 'light',          // 当前主题
    searchQuery: '',         // 当前搜索词
    convPageOffset: 0,       // 当前对话的分页偏移量
    convHasMore: false,      // 当前对话是否还有更多消息
    isLoadingMore: false,    // 是否正在加载更多
    isLoadingAll: false,     // 是否正在加载全部
    messageIndex: [],        // 全量消息索引（用于搜索）
    convSearchQuery: '',     // 对话内搜索词
    convSearchResults: [],   // 匹配的消息 UUID 列表
};

const PAGE_SIZE = 50;  // 每页消息数

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
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'json' && ext !== 'jsonl') {
        alert('请选择 .json 或 .jsonl 文件');
        return;
    }
    uploadFile(file);
}

async function uploadFile(file) {
    showLoading('正在解析文件...');

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

        const fmtLabel = data.source_format === 'claude_code' ? 'Claude Code 会话' : 'Claude.ai 对话';
        console.log(`✅ 已加载 ${data.conversation_count} 个${fmtLabel}, ${data.message_count} 条消息`);

    } catch (err) {
        hideLoading();
        alert('解析失败: ' + err.message);
        console.error(err);
    }
}

function showLoading(text) {
    dom.loadingText.textContent = text || '正在解析...';
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

        // 格式标记
        let formatBadge = '';
        if (conv.source_format === 'claude_code') {
            formatBadge = ' <span class="cc-badge">CC</span>';
        }

        // CC 特有信息
        let extraMeta = '';
        if (conv.source_format === 'claude_code' && conv.cwd) {
            const shortCwd = conv.cwd.split(/[\\/]/).pop() || conv.cwd;
            extraMeta = ` · ${escapeHtml(shortCwd)}`;
        }

        item.innerHTML = `
            <span class="conv-item-title">${title}${formatBadge}</span>
            <span class="conv-item-meta">${conv.date} · ${conv.message_count} 条消息${extraMeta}</span>
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

async function loadConversation(uuid, append = false) {
    if (!append) {
        state.currentConvUuid = uuid;
        state.convPageOffset = 0;
        state.convHasMore = false;

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
    } else {
        state.isLoadingMore = true;
    }

    try {
        const offset = append ? state.convPageOffset : 0;
        const resp = await fetch(`/api/conv/${uuid}?limit=${PAGE_SIZE}&offset=${offset}`);
        const data = await resp.json();

        if (data.error) {
            throw new Error(data.error);
        }

        state.convHasMore = data.has_more;
        state.convPageOffset = data.offset + data.messages.length;

        if (append) {
            appendMessages(data);
        } else {
            renderConversation(data);
        }

    } catch (err) {
        dom.messageList.innerHTML = `<div style="text-align:center;padding:2rem;color:#ef4444;">加载失败: ${escapeHtml(err.message)}</div>`;
        console.error(err);
    } finally {
        state.isLoadingMore = false;
    }
}

async function loadMoreMessages() {
    if (state.isLoadingMore || !state.convHasMore) return;
    const btn = document.getElementById('load-more-btn');
    if (btn) {
        btn.textContent = '加载中...';
        btn.disabled = true;
    }
    await loadConversation(state.currentConvUuid, true);
}

function appendMessages(data) {
    // 追加消息到已有列表
    data.messages.forEach(msg => {
        const msgEl = createMessageElement(msg);
        dom.messageList.appendChild(msgEl);
    });

    // 更新或移动"加载更多"按钮
    const currentMsgCount = dom.messageList.querySelectorAll('.message').length;
    updateLoadMoreButton(data.has_more, currentMsgCount, data.total_messages);

    // 对新消息做渲染后处理
    postRenderProcessing();

    // 增量追加导航条目（不再全量重建 DOM）
    syncOutline();
}

// ── 分块渐进渲染工具 ──
function yieldToBrowser() {
    return new Promise(resolve => setTimeout(resolve, 0));
}

function processChunkElements(elements) {
    // 只对传入的新元素做 marked.js 渲染，不全页扫描
    elements.forEach(el => {
        el.querySelectorAll('.text-block, .thinking-content, .knowledge-text').forEach(block => {
            const decoded = decodeHtmlEntities(block.innerHTML);
            if (decoded.trim()) {
                block.innerHTML = marked.parse(decoded);
            }
        });
    });
    // 外部链接新窗口
    elements.forEach(el => {
        el.querySelectorAll('a[href^="http"]').forEach(link => {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        });
    });
}

const LOAD_ALL_CHUNK = 30;  // 每批渲染 30 条

async function loadAllMessages() {
    if (state.isLoadingAll || state.isLoadingMore) return;
    state.isLoadingAll = true;

    const btnAll = document.getElementById('load-all-btn');
    const btnMore = document.getElementById('load-more-btn');

    if (btnAll) { btnAll.disabled = true; btnAll.textContent = '加载中…'; }
    if (btnMore) btnMore.disabled = true;

    const currentCount = dom.messageList.querySelectorAll('.message').length;
    let totalMessages = currentCount;

    try {
        // 一次性获取所有剩余消息
        const resp = await fetch(`/api/conv/${state.currentConvUuid}?limit=0&offset=${currentCount}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        const messages = data.messages || [];
        totalMessages = data.total_messages || currentCount + messages.length;
        state.convHasMore = false;

        // 更新消息索引（合并服务端返回的索引）
        if (data.message_index) {
            state.messageIndex = data.message_index;
        }

        // 分块渐进渲染
        for (let i = 0; i < messages.length; i += LOAD_ALL_CHUNK) {
            const chunk = messages.slice(i, i + LOAD_ALL_CHUNK);
            const newElements = [];

            chunk.forEach(msg => {
                if (!document.querySelector(`.message[data-uuid="${msg.uuid}"]`)) {
                    const msgEl = createMessageElement(msg);
                    dom.messageList.appendChild(msgEl);
                    newElements.push(msgEl);
                }
            });

            // 增量处理本块的 Markdown
            if (newElements.length > 0) {
                processChunkElements(newElements);
            }

            // 更新进度
            const loaded = currentCount + i + chunk.length;
            if (btnAll) {
                btnAll.textContent = `加载全部… ${Math.min(loaded, totalMessages)}/${totalMessages}`;
            }

            // 让出主线程给浏览器
            await yieldToBrowser();
        }

        // 全部完成：highlight.js 延迟到空闲时
        const doFinalHighlight = () => {
            $$('pre').forEach(pre => {
                if (pre.parentElement.classList.contains('code-block-wrapper')) return;
                const code = pre.querySelector('code');
                if (code) {
                    const decoded = decodeHtmlEntities(code.innerHTML);
                    code.innerHTML = decoded;
                    code.removeAttribute('data-highlighted');
                    hljs.highlightElement(code);
                }
                const wrapper = document.createElement('div');
                wrapper.className = 'code-block-wrapper';
                pre.parentNode.insertBefore(wrapper, pre);
                wrapper.appendChild(pre);
            });
        };

        if (window.requestIdleCallback) {
            requestIdleCallback(doFinalHighlight, { timeout: 3000 });
        } else {
            setTimeout(doFinalHighlight, 200);
        }

        // 更新按钮状态
        const finalCount = dom.messageList.querySelectorAll('.message').length;
        updateLoadMoreButton(false, finalCount, totalMessages);
        syncOutline();

    } catch (err) {
        console.error('加载全部失败:', err);
        if (btnAll) { btnAll.textContent = '加载失败，重试'; btnAll.disabled = false; }
        if (btnMore) { btnMore.disabled = false; updateLoadMoreButton(true, currentCount, totalMessages); }
    } finally {
        state.isLoadingAll = false;
    }
}

function updateLoadMoreButton(hasMore, shownCount, totalCount) {
    let btn = document.getElementById('load-more-btn');
    let btnAll = document.getElementById('load-all-btn');

    if (hasMore) {
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'load-more-btn';
            btn.className = 'btn-load-more';
            btn.addEventListener('click', loadMoreMessages);
            dom.messageList.appendChild(btn);
        }
        if (!btnAll) {
            btnAll = document.createElement('button');
            btnAll.id = 'load-all-btn';
            btnAll.className = 'btn-load-all';
            btnAll.textContent = '加载全部';
            btnAll.addEventListener('click', loadAllMessages);
            dom.messageList.appendChild(btnAll);
        }
        // 始终移到底部
        btn.textContent = `加载更多...（已显示 ${shownCount} 条，共 ${totalCount} 条）`;
        btn.disabled = false;
        btn.style.opacity = '1';
        dom.messageList.appendChild(btn);
        dom.messageList.appendChild(btnAll);
    } else {
        if (btn) {
            btn.textContent = `已加载全部 ${totalCount} 条消息`;
            btn.disabled = true;
            btn.style.opacity = '0.5';
            dom.messageList.appendChild(btn);
        }
        if (btnAll) {
            btnAll.remove();
        }
    }
}

function syncOutline() {
    // 从 state.messageIndex 匹配当前 DOM 中已渲染的消息，按对话顺序构建导航
    // 核心优化：不再从 DOM 提取 rendered_html 做 innerHTML 解析
    // 代价：创建简单 DOM 元素（可忽略），收益：消除 extractPreview 的 O(n) HTML 解析

    const uuidToIdx = {};
    state.messageIndex.forEach((entry, i) => {
        uuidToIdx[entry.uuid] = i;
    });

    const rendered = $$('.message');
    const pairs = [];
    rendered.forEach(el => {
        const uuid = el.dataset.uuid;
        if (uuid && uuidToIdx[uuid] !== undefined) {
            pairs.push({
                entry: state.messageIndex[uuidToIdx[uuid]],
                globalIndex: uuidToIdx[uuid],
            });
        }
    });

    // 按对话顺序排列（处理 loadMessagePage 导致的非连续加载）
    pairs.sort((a, b) => a.globalIndex - b.globalIndex);

    // 条目数没变则跳过
    if (pairs.length === _outlineEntryCount) return;
    _outlineEntryCount = pairs.length;

    // 构建 uuid → globalIndex 映射（O(1) 查找，scroll spy / updateOutlineActive 共用）
    _outlineUuidToIdx = {};
    pairs.forEach(p => { _outlineUuidToIdx[p.entry.uuid] = p.globalIndex; });

    dom.outlineList.innerHTML = '';

    if (pairs.length > 500) {
        // 超大导航：异步分块构建，保持 UI 响应
        _buildOutlineChunked(pairs);
    } else {
        // 常规大小：DocumentFragment 批量插入
        const fragment = document.createDocumentFragment();
        pairs.forEach(p => fragment.appendChild(_createOutlineItem(p.entry, p.globalIndex)));
        dom.outlineList.appendChild(fragment);
    }

    // 重建 scroll spy（观察全部已渲染消息）
    if (outlineObserver) outlineObserver.disconnect();
    outlineObserver = null;
    setupScrollSpy();
}

async function _buildOutlineChunked(pairs) {
    // 分块渲染超大导航（>500 条目），每块让出主线程保持 UI 响应
    const CHUNK = 200;
    for (let i = 0; i < pairs.length; i += CHUNK) {
        const chunk = pairs.slice(i, i + CHUNK);
        const fragment = document.createDocumentFragment();
        chunk.forEach(p => fragment.appendChild(_createOutlineItem(p.entry, p.globalIndex)));
        dom.outlineList.appendChild(fragment);
        if (i + CHUNK < pairs.length) {
            await new Promise(r => requestAnimationFrame(r));
        }
    }
}

function renderConversation(conv) {
    // 头部
    dom.convTitle.textContent = conv.name;

    // 存储消息索引（全量，用于搜索）
    state.messageIndex = conv.message_index || [];
    state.convSearchQuery = '';
    state.convSearchResults = [];
    _currentSearchHitIndex = -1;

    // 清空对话内搜索栏和旧高亮
    closeConvSearch();

    // 元信息
    const totalAll = conv.total_messages || conv.message_count;
    let metaText = `${conv.created_at} · 共 ${totalAll} 条消息`;
    if (conv.source_format === 'claude_code') {
        metaText += ' · Claude Code 会话';
        if (conv.mode) metaText += ` · ${conv.mode} 模式`;
    }
    dom.convMeta.textContent = metaText;

    // 对话内搜索栏（有消息索引时显示）
    showConvSearch();

    // CC 元数据横幅（先清除旧的，防止重复追加）
    const oldBanner = document.querySelector('.cc-session-meta');
    if (oldBanner) oldBanner.remove();

    if (conv.cc_meta_html) {
        dom.convMeta.insertAdjacentHTML('afterend', conv.cc_meta_html);
    }

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

    // "加载更多"按钮
    if (conv.has_more) {
        updateLoadMoreButton(true, conv.messages.length, conv.total_messages);
    }

    // 渲染后处理
    postRenderProcessing();
    // 构建消息导航（从预计算索引，非 DOM）
    _outlineEntryCount = 0;
    _currentVisibleUuid = null;
    _lastActiveUuid = null;
    _outlineUuidToIdx = {};
    syncOutline();

    // 滚动到顶部
    dom.conversationView.scrollIntoView({ behavior: 'smooth' });
}

function createMessageElement(msg) {
    const wrapper = document.createElement('div');
    if (msg.uuid) wrapper.dataset.uuid = msg.uuid;

    // 根据 sender 确定样式类
    if (msg.sender === 'human') {
        wrapper.className = 'message message-human';
    } else if (msg.sender === 'system') {
        wrapper.className = 'message message-system';
    } else if (msg.sender === 'meta') {
        wrapper.className = 'message message-meta';
    } else {
        wrapper.className = 'message message-assistant';
    }

    // 角色标签
    let roleLabel;
    switch (msg.sender) {
        case 'human': roleLabel = 'You'; break;
        case 'system': roleLabel = 'System'; break;
        case 'meta': roleLabel = ''; break;
        default: roleLabel = 'Claude'; break;
    }
    const timeStr = msg.created_at || '';

    // CC 模型标记
    let modelTag = '';
    if (msg.model && msg.sender === 'assistant') {
        modelTag = ` <span class="msg-model-tag">${escapeHtml(msg.model)}</span>`;
    }

    // Meta 消息使用极简头部
    if (msg.sender === 'meta') {
        wrapper.innerHTML = `
            <div class="message-body">${msg.rendered_html}</div>
        `;
    } else {
        wrapper.innerHTML = `
            <div class="message-header">
                <span class="message-role">${roleLabel}${modelTag}</span>
                <span class="message-time">${timeStr}</span>
            </div>
            <div class="message-body">${msg.rendered_html}</div>
        `;
    }

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

    // highlight.js 高亮推迟到空闲时执行（避免阻塞 UI）
    const doHighlight = () => {
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
    };

    // 使用 requestIdleCallback 延迟高亮处理，避免阻塞首屏渲染
    if (window.requestIdleCallback) {
        requestIdleCallback(doHighlight, { timeout: 2000 });
    } else {
        setTimeout(doHighlight, 100);
    }

    // 处理外部链接（新窗口打开）
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
// 对话内搜索
// ═══════════════════════════════════════════

function showConvSearch() {
    // 创建或显示对话内搜索栏，渲染到 header 内的插槽
    let searchBar = document.getElementById('conv-search-bar');
    if (!searchBar) {
        searchBar = document.createElement('div');
        searchBar.id = 'conv-search-bar';
        searchBar.className = 'conv-search-bar';
        searchBar.innerHTML = `
            <input type="text" id="conv-search-input" placeholder="🔍 搜索对话内容..." autocomplete="off">
            <span id="conv-search-count" class="conv-search-count"></span>
            <button id="conv-search-prev" class="conv-search-nav" title="上一个">↑</button>
            <button id="conv-search-next" class="conv-search-nav" title="下一个">↓</button>
            <button id="conv-search-clear" class="conv-search-nav" title="清空搜索">✕</button>
        `;
        // 插入到 header 内的插槽
        const slot = document.getElementById('conv-search-slot');
        if (slot) {
            slot.appendChild(searchBar);
        }

        // 事件绑定
        document.getElementById('conv-search-input').addEventListener('input', (e) => {
            doConvSearch(e.target.value);
        });
        // Enter 键立即搜索（取消防抖等待）
        document.getElementById('conv-search-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (_serverSearchTimer) {
                    clearTimeout(_serverSearchTimer);
                    _serverSearchTimer = null;
                }
                doServerSearch(state.convSearchQuery);
            }
        });
        document.getElementById('conv-search-prev').addEventListener('click', () => {
            navigateSearchResult(-1);
        });
        document.getElementById('conv-search-next').addEventListener('click', () => {
            navigateSearchResult(1);
        });
        document.getElementById('conv-search-clear').addEventListener('click', () => {
            closeConvSearch();
        });
    }
    searchBar.style.display = 'flex';
    const input = document.getElementById('conv-search-input');
    if (input) {
        input.value = '';
        input.focus();
    }
    document.getElementById('conv-search-count').textContent = '';
}

let _serverSearchTimer = null;
const SERVER_SEARCH_DEBOUNCE = 250;  // 输入停止 250ms 后触发服务端搜索

function doConvSearch(query) {
    state.convSearchQuery = query.trim().toLowerCase();
    state.convSearchResults = [];

    // 清除旧高亮
    clearAllHighlights();
    // 取消上一次待执行的搜索
    if (_serverSearchTimer) {
        clearTimeout(_serverSearchTimer);
        _serverSearchTimer = null;
    }

    const countEl = document.getElementById('conv-search-count');

    if (!state.convSearchQuery || !state.messageIndex.length) {
        countEl.textContent = '';
        return;
    }

    // 直接走服务端深度搜索（全量文本，零遗漏）—— 带防抖
    countEl.textContent = '搜索中…';
    _serverSearchTimer = setTimeout(() => {
        doServerSearch(state.convSearchQuery);
    }, SERVER_SEARCH_DEBOUNCE);
}

async function doServerSearch(query) {
    if (!query || !state.currentConvUuid) return;

    const countEl = document.getElementById('conv-search-count');
    countEl.textContent = '搜索中…';

    try {
        const resp = await fetch(`/api/conv/${state.currentConvUuid}/search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        // 将服务端结果转换为客户端格式
        const hits = (data.results || []).map(r => ({
            uuid: r.uuid,
            sender: r.sender || '',
            preview: r.preview || '',
            page: r.page || 0,
        }));

        state.convSearchResults = hits;

        if (hits.length > 0) {
            countEl.textContent = `${hits.length} 个匹配`;
            _currentSearchHitIndex = -1;
            navigateSearchResult(1);
        } else {
            countEl.textContent = '无匹配';
        }
    } catch (err) {
        countEl.textContent = '搜索失败';
        console.error('服务端搜索失败:', err);
    }
}

let _currentSearchHitIndex = -1;

function navigateSearchResult(direction) {
    const hits = state.convSearchResults;
    if (!hits.length) return;

    _currentSearchHitIndex += direction;
    if (_currentSearchHitIndex < 0) _currentSearchHitIndex = hits.length - 1;
    if (_currentSearchHitIndex >= hits.length) _currentSearchHitIndex = 0;

    const hit = hits[_currentSearchHitIndex];
    const countEl = document.getElementById('conv-search-count');
    countEl.textContent = `${_currentSearchHitIndex + 1}/${hits.length}`;

    // 先清除所有高亮
    clearAllHighlights();

    // 查找该消息是否已在 DOM 中
    let msgEl = document.querySelector(`.message[data-uuid="${hit.uuid}"]`);
    if (msgEl) {
        // 只高亮当前气泡内的匹配文本
        highlightInElement(msgEl, state.convSearchQuery);
        msgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // 脉冲提示
        msgEl.style.boxShadow = '0 0 0 3px #f59e0b';
        setTimeout(() => { msgEl.style.boxShadow = ''; }, 2000);
    } else {
        // 未渲染 → 按需加载所在页
        loadMessagePage(hit);
    }
}

function clearAllHighlights() {
    $$('.search-highlight').forEach(el => {
        const parent = el.parentNode;
        if (parent) {
            parent.replaceChild(document.createTextNode(el.textContent), el);
            parent.normalize();
        }
    });
}

function highlightInElement(el, query) {
    if (!query || !el) return;
    const lowerQuery = query.toLowerCase();

    // 遍历目标元素内的文本节点
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(node => {
        const text = node.textContent.toLowerCase();
        const idx = text.indexOf(lowerQuery);
        if (idx >= 0) {
            const span = document.createElement('span');
            span.className = 'search-highlight';
            const range = document.createRange();
            range.setStart(node, idx);
            range.setEnd(node, idx + lowerQuery.length);
            try {
                range.surroundContents(span);
            } catch (e) {
                // 跨节点情况，跳过
            }
        }
    });
}

async function loadMessagePage(hit) {
    const page = hit.page || 0;
    const offset = page * PAGE_SIZE;
    showLoading('加载搜索结果...');
    try {
        const resp = await fetch(`/api/conv/${state.currentConvUuid}?limit=${PAGE_SIZE}&offset=${offset}`);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        // 追加消息到列表
        data.messages.forEach(msg => {
            // 检查是否已存在
            if (!document.querySelector(`.message[data-uuid="${msg.uuid}"]`)) {
                const msgEl = createMessageElement(msg);
                msgEl.dataset.uuid = msg.uuid;
                dom.messageList.appendChild(msgEl);
            }
        });

        postRenderProcessing();

        // 滚动到目标消息并高亮
        const target = document.querySelector(`.message[data-uuid="${hit.uuid}"]`);
        if (target) {
            clearAllHighlights();
            highlightInElement(target, state.convSearchQuery);
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.style.boxShadow = '0 0 0 3px #f59e0b';
            setTimeout(() => { target.style.boxShadow = ''; }, 2000);
        }

        // 更新分页按钮
        const currentMsgCount = dom.messageList.querySelectorAll('.message').length;
        updateLoadMoreButton(data.has_more, currentMsgCount, data.total_messages);

        // 同步导航（搜索加载的页可能不连续）
        syncOutline();
    } catch (err) {
        console.error('加载搜索结果失败:', err);
    } finally {
        hideLoading();
    }
}

function closeConvSearch() {
    // 清除搜索状态但保持搜索栏可见
    const input = document.getElementById('conv-search-input');
    if (input) input.value = '';
    const countEl = document.getElementById('conv-search-count');
    if (countEl) countEl.textContent = '';
    state.convSearchQuery = '';
    state.convSearchResults = [];
    _currentSearchHitIndex = -1;
    // 取消待执行的服务端搜索
    if (_serverSearchTimer) {
        clearTimeout(_serverSearchTimer);
        _serverSearchTimer = null;
    }
    // 清除高亮
    clearAllHighlights();
}

// Ctrl+F / Cmd+F 打开对话内搜索
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'f' && dom.conversationView.style.display !== 'none') {
        e.preventDefault();
        showConvSearch();
        document.getElementById('conv-search-input').focus();
    }
});


// ═══════════════════════════════════════════
// 主题切换
// ═══════════════════════════════════════════

dom.btnTheme.addEventListener('click', toggleTheme);

function toggleTheme() {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    applyTheme();
    localStorage.setItem('claude-viewer-theme', state.theme);
}

function applyTheme() {
    // 全局禁用过渡动画 → 颜色在单帧内完成，无 200ms 渐变延迟
    document.documentElement.classList.add('theme-switching');
    document.documentElement.setAttribute('data-theme', state.theme);
    dom.btnTheme.textContent = state.theme === 'light' ? '🌙' : '☀️';
    // 强制同步布局/样式计算 —— 新主题以无过渡状态提交到渲染树
    void document.body.offsetHeight;
    document.documentElement.classList.remove('theme-switching');
}

// 初始化主题：data-theme 已由 <head> 阻塞脚本设置
function initTheme() {
    if (document.documentElement.getAttribute('data-theme') === 'dark') {
        state.theme = 'dark';
    }
    dom.btnTheme.textContent = state.theme === 'light' ? '🌙' : '☀️';
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
let _outlineEntryCount = 0;   // 已渲染到导航 DOM 的条目数
let _currentVisibleUuid = null;  // scroll spy 缓存的当前可见消息 UUID
let _lastActiveUuid = null;      // 上一次高亮的导航条目 UUID
let _outlineUuidToIdx = {};      // uuid → globalIndex 映射（O(1) 查找）

dom.btnOutline.addEventListener('click', toggleOutline);

function toggleOutline() {
    const visible = dom.outlinePanel.style.display === 'flex';
    if (visible) {
        closeOutline();
    } else {
        dom.outlinePanel.style.display = 'flex';
        dom.btnOutline.style.background = 'var(--bg-hover)';
        // 用 scroll spy 缓存的可见 UUID，避免 getBoundingClientRect 全量循环
        if (_currentVisibleUuid) {
            updateOutlineActive(_currentVisibleUuid);
        } else {
            // 冷启动回退（首次打开，scroll spy 尚未触发回调）
            _detectAndHighlightVisible();
        }
    }
}

function closeOutline() {
    dom.outlinePanel.style.display = 'none';
    dom.btnOutline.style.background = '';
}

function _detectAndHighlightVisible() {
    // 冷启动回退：从第一条消息开始扫描，遇到超出视口底部的消息立即停止
    // 最坏情况（用户滚到最底部）也只扫描可见区域的少量消息
    const messages = $$('.message');
    let firstUuid = null;
    let firstIdx = Infinity;
    for (const msgEl of messages) {
        const rect = msgEl.getBoundingClientRect();
        // 消息完全在视口上方 → 继续
        if (rect.bottom <= 60) continue;
        // 消息已经超出视口底部 → 后面都不可能在视口内
        if (rect.top >= window.innerHeight) break;
        // 消息在视口内
        const uuid = msgEl.dataset.uuid;
        if (uuid && _outlineUuidToIdx[uuid] !== undefined) {
            const idx = _outlineUuidToIdx[uuid];
            if (idx < firstIdx) {
                firstIdx = idx;
                firstUuid = uuid;
            }
        }
    }
    if (firstUuid) {
        _currentVisibleUuid = firstUuid;
        updateOutlineActive(firstUuid);
    }
}

function _createOutlineItem(entry, globalIndex) {
    // 从 message_index 条目创建导航项（entry 含 uuid/sender/preview/timestamp）
    // 不再从 DOM 提取 rendered_html 做 innerHTML 解析 —— 消除核心瓶颈
    const item = document.createElement('button');
    item.className = 'outline-item';
    item.dataset.uuid = entry.uuid;       // 用于 UUID 导航
    item.dataset.index = globalIndex;     // 用于 scroll spy 高亮匹配

    let roleLabel;
    switch (entry.sender) {
        case 'human': roleLabel = 'You'; break;
        case 'system': roleLabel = 'Sys'; break;
        case 'meta': roleLabel = 'M'; break;
        default: roleLabel = 'Claude'; break;
    }
    const roleClass = 'role-' + (entry.sender === 'meta' ? 'meta' : entry.sender);

    // 服务端预计算的预览文本，截断到 80 字符
    const preview = (entry.preview || '').replace(/\s+/g, ' ').trim().substring(0, 80);

    item.innerHTML = `
        <span class="outline-role ${roleClass}">${roleLabel}</span>
        <span class="outline-preview">${escapeHtml(preview)}</span>
        <span class="outline-time">${entry.timestamp || ''}</span>
    `;

    // 用 UUID 导航，避免非连续加载时 DOM 索引错位
    const targetUuid = entry.uuid;
    item.addEventListener('click', () => scrollToMessageByUuid(targetUuid));
    return item;
}

function scrollToMessageByUuid(uuid) {
    const msgEl = document.querySelector(`.message[data-uuid="${uuid}"]`);
    if (!msgEl) return;
    msgEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    updateOutlineActive(uuid);
}

function scrollToMessage(index) {
    // 按 DOM 索引滚动（用于外部直接调用）；导航面板使用 UUID 导航
    const messages = $$('.message');
    if (messages[index]) {
        const uuid = messages[index].dataset.uuid;
        messages[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (uuid) updateOutlineActive(uuid);
    }
}

function setupScrollSpy() {
    // IntersectionObserver 监听消息块，O(1) 查找（_outlineUuidToIdx map），缓存可见 UUID
    outlineObserver = new IntersectionObserver((entries) => {
        let firstVisibleUuid = null;
        let firstVisibleIdx = Infinity;
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const uuid = entry.target.dataset.uuid;
                if (uuid && _outlineUuidToIdx[uuid] !== undefined) {
                    const idx = _outlineUuidToIdx[uuid];
                    if (idx < firstVisibleIdx) {
                        firstVisibleIdx = idx;
                        firstVisibleUuid = uuid;
                    }
                }
            }
        });
        if (firstVisibleUuid !== null && firstVisibleUuid !== _currentVisibleUuid) {
            _currentVisibleUuid = firstVisibleUuid;
            updateOutlineActive(firstVisibleUuid);
        }
    }, {
        root: null,
        threshold: 0.3,
        rootMargin: '-60px 0px 0px 0px',
    });

    // 观察所有已渲染消息
    $$('.message').forEach(msg => outlineObserver.observe(msg));
}

function updateOutlineActive(uuid) {
    // O(1) 高亮：用属性选择器直接定位目标条目，不再循环 1700 个节点
    if (!uuid || uuid === _lastActiveUuid) return;

    // 清除旧高亮
    if (_lastActiveUuid) {
        const oldItem = dom.outlineList.querySelector(`.outline-item[data-uuid="${_lastActiveUuid}"]`);
        if (oldItem) oldItem.classList.remove('active');
    }

    // 设置新高亮
    const newItem = dom.outlineList.querySelector(`.outline-item[data-uuid="${uuid}"]`);
    if (newItem) newItem.classList.add('active');

    _lastActiveUuid = uuid;
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
