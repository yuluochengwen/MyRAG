/**
 * 聊天界面逻辑
 */

const API_BASE_URL = 'http://localhost:8000';
const WS_BASE_URL = 'ws://localhost:8000';

// 页面状态
let currentAssistant = null;
let currentConversation = null;
let conversations = [];
let isProcessing = false;

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    // 从URL获取assistant_id
    const urlParams = new URLSearchParams(window.location.search);
    const assistantId = urlParams.get('assistant_id');
    
    if (!assistantId) {
        alert('缺少助手ID参数');
        window.location.href = 'intelligent-assistant.html';
        return;
    }
    
    await loadAssistant(assistantId);
    await loadConversations(assistantId);
    setupEventListeners();
    
    // 初始化记忆状态显示
    updateMemoryStatus();
    
    // 自动创建第一个对话或选择最近的对话
    if (conversations.length === 0) {
        await createNewConversation();
    } else {
        await switchConversation(conversations[0].id);
    }
});

function setupEventListeners() {
    // 新建对话
    document.getElementById('newConversationBtn')?.addEventListener('click', createNewConversation);
    
    // 发送消息
    document.getElementById('messageForm')?.addEventListener('submit', handleSendMessage);
    
    // 历史记忆开关
    document.getElementById('memoryToggle')?.addEventListener('change', function() {
        const maxHistoryInput = document.getElementById('maxHistoryTurns');
        if (this.checked) {
            maxHistoryInput.disabled = false;
            maxHistoryInput.value = maxHistoryInput.value === '0' ? '10' : maxHistoryInput.value;
        } else {
            maxHistoryInput.disabled = true;
            maxHistoryInput.value = '0';
        }
        updateMemoryStatus();
    });
    
    // 记忆轮数输入框变化时更新状态提示
    document.getElementById('maxHistoryTurns')?.addEventListener('input', updateMemoryStatus);
    document.getElementById('maxHistoryTurns')?.addEventListener('change', updateMemoryStatus);
    
    // 设置菜单切换
    document.getElementById('settingsMenuBtn')?.addEventListener('click', function(e) {
        e.stopPropagation();
        const menu = document.getElementById('settingsMenu');
        menu?.classList.toggle('hidden');
    });
    
    // 关闭设置菜单
    document.getElementById('closeSettingsMenu')?.addEventListener('click', function() {
        document.getElementById('settingsMenu')?.classList.add('hidden');
    });
    
    // 点击外部关闭菜单
    document.addEventListener('click', function(e) {
        const menu = document.getElementById('settingsMenu');
        const btn = document.getElementById('settingsMenuBtn');
        if (menu && !menu.contains(e.target) && !btn?.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });
    
    // 输入框自动调整高度
    const input = document.getElementById('messageInput');
    input?.addEventListener('input', function() {
        this.style.height = 'auto';
        const newHeight = Math.min(this.scrollHeight, 200);
        this.style.height = newHeight + 'px';
        // 保持最小高度48px
        if (newHeight < 48) {
            this.style.height = '48px';
        }
    });
    
    // Enter发送, Shift+Enter换行
    input?.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            document.getElementById('messageForm').dispatchEvent(new Event('submit'));
        }
    });
}

// ==================== 数据加载 ====================

async function loadAssistant(assistantId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/assistants/${assistantId}`);
        if (!response.ok) throw new Error('加载助手信息失败');
        
        currentAssistant = await response.json();
        renderAssistantInfo();
        renderChatHeader();
    } catch (error) {
        console.error('加载助手失败:', error);
        alert('加载助手信息失败: ' + error.message);
        window.location.href = 'intelligent-assistant.html';
    }
}

async function loadConversations(assistantId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations?assistant_id=${assistantId}`);
        if (!response.ok) throw new Error('加载对话列表失败');
        
        const data = await response.json();
        conversations = data.conversations || [];
        renderConversationList();
    } catch (error) {
        console.error('加载对话列表失败:', error);
        showMessage('加载对话列表失败', 'error');
    }
}

async function loadMessages(conversationId) {
    try {
        console.log('[loadMessages] 加载对话消息:', conversationId);
        
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/messages`);
        if (!response.ok) throw new Error('加载消息失败');
        
        const data = await response.json();
        const messages = data.messages || [];
        
        console.log('[loadMessages] 消息加载成功，数量:', messages.length);
        
        renderMessages(messages);
        scrollToBottom();
    } catch (error) {
        console.error('加载消息失败:', error);
        showMessage('加载消息失败', 'error');
    }
}

// ==================== 渲染函数 ====================

function renderAssistantInfo() {
    const container = document.getElementById('assistantInfo');
    if (!container || !currentAssistant) return;
    
    const iconMap = {
        'blue': { bg: 'bg-blue-100', text: 'text-blue-500', icon: 'fa-robot' },
        'purple': { bg: 'bg-purple-100', text: 'text-purple-500', icon: 'fa-code' },
        'orange': { bg: 'bg-orange-100', text: 'text-orange-500', icon: 'fa-shopping-cart' },
        'green': { bg: 'bg-green-100', text: 'text-green-500', icon: 'fa-leaf' },
        'pink': { bg: 'bg-pink-100', text: 'text-pink-500', icon: 'fa-heart' }
    };
    
    const theme = iconMap[currentAssistant.color_theme] || iconMap['blue'];
    const statusColor = currentAssistant.status === 'active' ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-600';
    const statusText = currentAssistant.status === 'active' ? '已启用' : '已禁用';
    
    // 知识库标签
    let kbInfo = '<span class="text-gray-500 text-xs">无绑定知识库</span>';
    if (currentAssistant.kb_names && currentAssistant.kb_names.length > 0) {
        kbInfo = currentAssistant.kb_names.map(name => 
            `<span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">${escapeHtml(name)}</span>`
        ).join(' ');
    }
    
    container.innerHTML = `
        <div class="flex items-start space-x-3">
            <div class="w-12 h-12 rounded-lg ${theme.bg} flex items-center justify-center flex-shrink-0">
                <i class="fa ${theme.icon} ${theme.text} text-xl"></i>
            </div>
            <div class="flex-grow min-w-0">
                <div class="flex items-center space-x-2 mb-1">
                    <h2 class="font-bold truncate">${escapeHtml(currentAssistant.name)}</h2>
                    <span class="px-2 py-0.5 ${statusColor} text-xs rounded-full flex-shrink-0">${statusText}</span>
                </div>
                <p class="text-sm text-gray-500 mb-2 line-clamp-2">${escapeHtml(currentAssistant.description || '')}</p>
                <div class="space-y-1 text-xs">
                    <div class="flex items-center flex-wrap gap-1">
                        <span class="text-gray-400">知识库:</span>
                        ${kbInfo}
                    </div>
                    <div class="flex items-center">
                        <span class="text-gray-400">模型:</span>
                        <span class="ml-1 px-2 py-0.5 bg-green-50 text-green-600 rounded-full">${escapeHtml(currentAssistant.llm_model)}</span>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function renderChatHeader() {
    const container = document.getElementById('chatHeaderContent');
    if (!container || !currentAssistant) return;
    
    container.innerHTML = `
        <div class="flex items-center space-x-3">
            <i class="fa fa-robot text-primary text-xl"></i>
            <div>
                <h3 class="font-bold">${escapeHtml(currentAssistant.name)}</h3>
                <p class="text-xs text-gray-500">${currentConversation ? escapeHtml(currentConversation.title) : '加载中...'}</p>
            </div>
        </div>
    `;
}

function renderConversationList() {
    const container = document.getElementById('conversationList');
    if (!container) return;
    
    if (conversations.length === 0) {
        container.innerHTML = '<p class="text-sm text-gray-400 text-center py-4">暂无对话历史</p>';
        return;
    }
    
    // 按日期分组
    const grouped = groupConversationsByDate(conversations);
    
    let html = '';
    for (const [dateLabel, convs] of Object.entries(grouped)) {
        html += `
            <div class="mb-4">
                <h4 class="text-xs font-bold text-gray-400 mb-2">${dateLabel}</h4>
                ${convs.map(conv => renderConversationItem(conv)).join('')}
            </div>
        `;
    }
    
    container.innerHTML = html;
}

function renderConversationItem(conv) {
    const isActive = currentConversation && currentConversation.id === conv.id;
    const time = formatTime(conv.updated_at);
    
    return `
        <div class="conversation-item ${isActive ? 'active' : ''}" data-id="${conv.id}">
            <div class="flex items-start justify-between">
                <div class="flex-grow min-w-0 cursor-pointer" onclick="switchConversation(${conv.id})">
                    <h5 class="font-medium text-sm truncate">${escapeHtml(conv.title)}</h5>
                    <div class="flex items-center space-x-2 text-xs text-gray-500 mt-1">
                        <span><i class="fa fa-comments-o mr-1"></i>${conv.message_count}条消息</span>
                        <span>${time}</span>
                    </div>
                </div>
                <div class="conversation-actions flex items-center space-x-1">
                    <button class="action-btn p-1 rounded hover:bg-blue-50 text-gray-400 hover:text-blue-500" 
                            onclick="renameConversation(${conv.id}); event.stopPropagation();" 
                            title="重命名">
                        <i class="fa fa-edit text-sm"></i>
                    </button>
                    <button class="action-btn p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500" 
                            onclick="deleteConversation(${conv.id}); event.stopPropagation();" 
                            title="删除">
                        <i class="fa fa-trash text-sm"></i>
                    </button>
                </div>
            </div>
        </div>
    `;
}

function renderMessages(messages) {
    const container = document.getElementById('messagesContainer');
    if (!container) return;
    
    // 隐藏欢迎消息
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) welcome.style.display = 'none';
    
    if (messages.length === 0) {
        container.innerHTML = '';
        if (welcome) welcome.style.display = 'block';
        updateMessageCount(0);
        return;
    }
    
    let html = '';
    messages.forEach(msg => {
        html += renderMessageBubble(msg);
    });
    
    container.innerHTML = html;
    
    // 渲染Markdown
    document.querySelectorAll('.markdown-content').forEach(el => {
        el.innerHTML = marked.parse(el.textContent || '');
    });
    
    // 代码高亮
    document.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
    
    // 更新消息计数
    updateMessageCount(messages.length);
}

function updateMessageCount(count) {
    const countElement = document.getElementById('messageCount');
    if (countElement) {
        countElement.textContent = count || 0;
    }
}

function renderMessageBubble(msg) {
    const isUser = msg.role === 'user';
    const time = formatTime(msg.created_at);
    
    if (isUser) {
        return `
            <div class="flex justify-end">
                <div class="message-user">
                    <div class="markdown-content">${escapeHtml(msg.content)}</div>
                    <div class="text-xs opacity-70 mt-1">${time}</div>
                </div>
            </div>
        `;
    } else {
        let sourcesHtml = '';
        if (msg.sources && msg.sources.length > 0) {
            sourcesHtml = `
                <div class="flex flex-wrap gap-2 mt-2">
                    ${msg.sources.map((src, i) => `
                        <span class="source-tag" title="${escapeHtml(src.content || '')}">
                            <i class="fa fa-file-text-o"></i>
                            来源${i + 1} (${(src.similarity * 100).toFixed(1)}%)
                        </span>
                    `).join('')}
                </div>
            `;
        }
        
        return `
            <div class="flex justify-start">
                <div class="message-assistant">
                    <div class="flex items-center space-x-2 mb-2">
                        <i class="fa fa-robot text-primary"></i>
                        <span class="text-xs font-medium text-gray-500">AI助手</span>
                    </div>
                    <div class="markdown-content">${escapeHtml(msg.content)}</div>
                    ${sourcesHtml}
                    <div class="text-xs text-gray-400 mt-2">${time}</div>
                </div>
            </div>
        `;
    }
}

// ==================== 对话操作 ====================

async function createNewConversation() {
    if (isProcessing) return;
    
    try {
        isProcessing = true;
        console.log('[createNewConversation] 开始创建新对话');
        
        const response = await fetch(`${API_BASE_URL}/api/conversations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                assistant_id: currentAssistant.id,
                title: '新对话'
            })
        });
        
        if (!response.ok) throw new Error('创建对话失败');
        
        const newConv = await response.json();
        console.log('[createNewConversation] 新对话创建成功:', newConv);
        
        conversations.unshift(newConv);
        
        // 立即切换到新对话（这会清空消息区域并加载新对话的消息）
        console.log('[createNewConversation] 切换到新对话 ID:', newConv.id);
        await switchConversation(newConv.id);
        
        // 更新对话列表显示
        console.log('[createNewConversation] 更新对话列表');
        renderConversationList();
        
        console.log('[createNewConversation] 新对话创建完成');
    } catch (error) {
        console.error('创建对话失败:', error);
        showMessage('创建对话失败', 'error');
    } finally {
        isProcessing = false;
    }
}

async function switchConversation(conversationId) {
    if (isProcessing) return;
    
    try {
        console.log('[switchConversation] 切换到对话:', conversationId);
        
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`);
        if (!response.ok) throw new Error('加载对话失败');
        
        currentConversation = await response.json();
        console.log('[switchConversation] 对话信息加载成功:', currentConversation);
        
        // 加载消息（会清空并重新渲染消息区域）
        await loadMessages(conversationId);
        
        // 更新对话列表（高亮选中的对话）
        renderConversationList();
        
        // 更新聊天标题
        renderChatHeader();
        
        console.log('[switchConversation] 切换完成');
    } catch (error) {
        console.error('切换对话失败:', error);
        showMessage('切换对话失败', 'error');
    }
}

async function deleteConversation(conversationId) {
    if (!confirm('确定要删除这个对话吗？')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('删除对话失败');
        
        // 从列表中移除
        conversations = conversations.filter(c => c.id !== conversationId);
        
        // 如果删除的是当前对话,切换到第一个或创建新对话
        if (currentConversation && currentConversation.id === conversationId) {
            if (conversations.length > 0) {
                await switchConversation(conversations[0].id);
            } else {
                await createNewConversation();
            }
        }
        
        renderConversationList();
        showMessage('对话已删除', 'success');
    } catch (error) {
        console.error('删除对话失败:', error);
        showMessage('删除对话失败', 'error');
    }
}

async function renameConversation(conversationId) {
    const conv = conversations.find(c => c.id === conversationId);
    if (!conv) return;
    
    const newTitle = prompt('请输入新的对话标题:', conv.title);
    if (!newTitle || newTitle.trim() === '' || newTitle === conv.title) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                assistant_id: currentAssistant.id, 
                title: newTitle.trim() 
            })
        });
        
        if (!response.ok) throw new Error('重命名失败');
        
        const updatedConv = await response.json();
        
        // 更新本地数据
        const index = conversations.findIndex(c => c.id === conversationId);
        if (index !== -1) {
            conversations[index] = updatedConv;
        }
        
        if (currentConversation && currentConversation.id === conversationId) {
            currentConversation = updatedConv;
            renderChatHeader();
        }
        
        renderConversationList();
        showMessage('重命名成功', 'success');
    } catch (error) {
        console.error('重命名失败:', error);
        showMessage('重命名失败', 'error');
    }
}

async function clearCurrentConversation() {
    if (!currentConversation) return;
    
    if (!confirm('确定要清除当前对话的所有消息吗？')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${currentConversation.id}/messages`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('清除对话失败');
        
        // 重新加载消息
        await loadMessages(currentConversation.id);
        await loadConversations(currentAssistant.id);
        
        showMessage('对话已清除', 'success');
    } catch (error) {
        console.error('清除对话失败:', error);
        showMessage('清除对话失败', 'error');
    }
}

function copyLastMessage() {
    const messages = document.querySelectorAll('.message-assistant .markdown-content');
    if (messages.length === 0) {
        showMessage('没有可复制的消息', 'warning');
        return;
    }
    
    const lastMessage = messages[messages.length - 1];
    const text = lastMessage.textContent || lastMessage.innerText;
    
    navigator.clipboard.writeText(text).then(() => {
        showMessage('已复制到剪贴板', 'success');
    }).catch(() => {
        showMessage('复制失败', 'error');
    });
}

function getMessageCount() {
    const messages = document.querySelectorAll('.message-user, .message-assistant');
    return messages.length;
}

// 获取当前记忆轮数设置
function getCurrentMemoryTurns() {
    return parseInt(document.getElementById('maxHistoryTurns')?.value || '10');
}

// 更新记忆状态提示
function updateMemoryStatus() {
    const turns = getCurrentMemoryTurns();
    const input = document.getElementById('maxHistoryTurns');
    if (input) {
        if (turns === 0) {
            input.title = '上下文记忆已禁用 - AI不会记住之前的对话';
            input.style.borderColor = '#ef4444'; // red
        } else if (turns <= 5) {
            input.title = `短期记忆 - 记住最近${turns}轮对话（${turns*2}条消息）`;
            input.style.borderColor = '#f59e0b'; // yellow
        } else {
            input.title = `标准记忆 - 记住最近${turns}轮对话（${turns*2}条消息）`;
            input.style.borderColor = '#10b981'; // green
        }
    }
}

async function deleteConversation(conversationId) {
    if (!confirm('确定要删除这个对话吗？')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('删除对话失败');
        
        // 从列表中移除
        conversations = conversations.filter(c => c.id !== conversationId);
        
        // 如果删除的是当前对话,切换到第一个或创建新对话
        if (currentConversation && currentConversation.id === conversationId) {
            if (conversations.length > 0) {
                await switchConversation(conversations[0].id);
            } else {
                await createNewConversation();
            }
        }
        
        renderConversationList();
        showMessage('对话已删除', 'success');
    } catch (error) {
        console.error('删除对话失败:', error);
        showMessage('删除对话失败', 'error');
    }
}

// ==================== 消息发送 ====================

async function handleSendMessage(e) {
    e.preventDefault();
    
    if (isProcessing) return;
    if (!currentConversation) {
        showMessage('请先创建对话', 'warning');
        return;
    }
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    try {
        isProcessing = true;
        input.value = '';
        input.style.height = 'auto';
        
        // 禁用发送按钮
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.disabled = true;
        
        // 显示用户消息
        appendUserMessage(message);
        
        // 显示AI思考中
        const thinkingId = showThinkingIndicator();
        
        // 检查是否启用流式响应
        const streamEnabled = document.getElementById('streamToggle')?.checked ?? true;
        
        if (streamEnabled) {
            // 调用流式聊天API
            await sendChatRequestStream(message, thinkingId);
        } else {
            // 调用普通聊天API
            await sendChatRequest(message, thinkingId);
        }
        
    } catch (error) {
        console.error('发送消息失败:', error);
        showMessage('发送失败: ' + error.message, 'error');
    } finally {
        isProcessing = false;
        document.getElementById('sendBtn').disabled = false;
    }
}

function appendUserMessage(content) {
    const container = document.getElementById('messagesContainer');
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) welcome.style.display = 'none';
    
    const time = formatTime(new Date().toISOString());
    const messageHtml = `
        <div class="flex justify-end">
            <div class="message-user">
                <div class="markdown-content">${escapeHtml(content)}</div>
                <div class="text-xs opacity-70 mt-1">${time}</div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHtml);
    scrollToBottom();
}

function showThinkingIndicator() {
    const container = document.getElementById('messagesContainer');
    const thinkingId = 'thinking-' + Date.now();
    
    const thinkingHtml = `
        <div class="flex justify-start" id="${thinkingId}">
            <div class="message-assistant">
                <div class="flex items-center space-x-2 mb-2">
                    <i class="fa fa-robot text-primary"></i>
                    <span class="text-xs font-medium text-gray-500">AI助手</span>
                </div>
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', thinkingHtml);
    scrollToBottom();
    
    return thinkingId;
}

async function sendChatRequest(query, thinkingId) {
    try {
        // 调用智能助手专用聊天API
        const memoryEnabled = document.getElementById('memoryToggle')?.checked ?? true;
        const maxHistoryTurns = memoryEnabled ? parseInt(document.getElementById('maxHistoryTurns')?.value || '10') : 0;
        console.log('[Chat] 发送非流式请求:', {
            conversation_id: currentConversation.id,
            query: query,
            memory_enabled: memoryEnabled,
            max_history_turns: maxHistoryTurns
        });
        const response = await fetch(`${API_BASE_URL}/api/conversations/${currentConversation.id}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                temperature: 0.7,
                max_tokens: 2048,
                max_history_turns: maxHistoryTurns
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '对话失败');
        }
        
        const data = await response.json();
        
        // 移除思考指示器
        document.getElementById(thinkingId)?.remove();
        
        // 显示AI回复
        appendAssistantMessage(data.answer, data.sources);
        
        // 后端已经保存了消息，不需要前端再次保存
        
        // 更新对话列表
        await loadConversations(currentAssistant.id);
        
    } catch (error) {
        document.getElementById(thinkingId)?.remove();
        throw error;
    }
}

// 流式聊天请求
async function sendChatRequestStream(query, thinkingId) {
    let messageId = null;
    let collectedText = '';
    let sourcesData = null;
    
    try {
        const memoryEnabled = document.getElementById('memoryToggle')?.checked ?? true;
        const maxHistoryTurns = memoryEnabled ? parseInt(document.getElementById('maxHistoryTurns')?.value || '10') : 0;
        console.log('[Chat] 发送流式请求:', {
            conversation_id: currentConversation.id,
            query: query,
            memory_enabled: memoryEnabled,
            max_history_turns: maxHistoryTurns
        });
        const response = await fetch(`${API_BASE_URL}/api/conversations/${currentConversation.id}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                temperature: 0.7,
                max_tokens: 2048,
                max_history_turns: maxHistoryTurns
            })
        });
        
        if (!response.ok) {
            const error = await response.text();
            throw new Error(error || '流式对话失败');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            // 解码数据
            buffer += decoder.decode(value, { stream: true });
            
            // 按行分割SSE数据
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // 保留不完整的行
            
            for (const line of lines) {
                if (!line.trim() || !line.startsWith('data: ')) continue;
                
                try {
                    const jsonStr = line.substring(6); // 移除 "data: " 前缀
                    const chunk = JSON.parse(jsonStr);
                    const chunkType = chunk.type;
                    const chunkData = chunk.data;
                    
                    if (chunkType === 'sources') {
                        // 接收到检索来源
                        sourcesData = chunkData.sources || [];
                        console.log(`检索到 ${chunkData.retrieval_count} 个相关文档`);
                        
                        // 移除思考指示器，创建消息占位符
                        document.getElementById(thinkingId)?.remove();
                        messageId = appendAIMessagePlaceholder();
                        
                        // 显示来源信息
                        if (sourcesData.length > 0) {
                            displaySourcesInMessage(messageId, sourcesData);
                        }
                    } 
                    else if (chunkType === 'text') {
                        // 接收到文本片段
                        if (!messageId) {
                            document.getElementById(thinkingId)?.remove();
                            messageId = appendAIMessagePlaceholder();
                        }
                        
                        collectedText += chunkData;
                        appendTextToMessage(messageId, chunkData);
                    } 
                    else if (chunkType === 'done') {
                        // 生成完成
                        if (messageId) {
                            finalizeMessage(messageId, collectedText);
                        }
                        
                        // 更新对话列表
                        await loadConversations(currentAssistant.id);
                        break;
                    } 
                    else if (chunkType === 'error') {
                        throw new Error(chunkData.error || '流式生成出错');
                    }
                    
                } catch (parseError) {
                    console.error('解析SSE数据失败:', parseError, 'Line:', line);
                }
            }
        }
        
    } catch (error) {
        document.getElementById(thinkingId)?.remove();
        if (messageId) {
            document.getElementById(messageId)?.remove();
        }
        throw error;
    }
}

// 创建AI消息占位符
function appendAIMessagePlaceholder() {
    const container = document.getElementById('messagesContainer');
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) welcome.style.display = 'none';
    
    const messageId = 'ai-msg-' + Date.now();
    const time = formatTime(new Date().toISOString());
    
    const messageHtml = `
        <div class="flex justify-start" id="${messageId}">
            <div class="message-assistant">
                <div class="flex items-center space-x-2 mb-2">
                    <i class="fa fa-robot text-primary"></i>
                    <span class="text-xs font-medium text-gray-500">AI助手</span>
                </div>
                <div class="markdown-content" data-raw-content=""></div>
                <div class="sources-container"></div>
                <div class="text-xs text-gray-400 mt-2">${time}</div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHtml);
    scrollToBottom();
    
    return messageId;
}

// 实时追加文本到消息
function appendTextToMessage(messageId, text) {
    const messageEl = document.getElementById(messageId);
    if (!messageEl) return;
    
    const contentEl = messageEl.querySelector('.markdown-content');
    if (!contentEl) return;
    
    // 追加原始文本
    const currentRaw = contentEl.getAttribute('data-raw-content') || '';
    const newRaw = currentRaw + text;
    contentEl.setAttribute('data-raw-content', newRaw);
    
    // 实时渲染Markdown（提供流畅的实时体验）
    try {
        contentEl.innerHTML = marked.parse(newRaw);
        
        // 代码高亮（仅对新增的代码块）
        contentEl.querySelectorAll('pre code:not(.hljs)').forEach(block => {
            hljs.highlightElement(block);
        });
    } catch (e) {
        // 如果Markdown解析失败（可能是不完整的语法），回退到纯文本
        contentEl.textContent = newRaw;
    }
    
    scrollToBottom();
}

// 在消息中显示来源
function displaySourcesInMessage(messageId, sources) {
    const messageEl = document.getElementById(messageId);
    if (!messageEl || !sources || sources.length === 0) return;
    
    const sourcesContainer = messageEl.querySelector('.sources-container');
    if (!sourcesContainer) return;
    
    const sourcesHtml = `
        <div class="flex flex-wrap gap-2 mt-2">
            ${sources.map((src, i) => `
                <span class="source-tag" title="${escapeHtml(src.content || '')}">
                    <i class="fa fa-file-text-o"></i>
                    来源${i + 1} (${(src.similarity * 100).toFixed(1)}%)
                </span>
            `).join('')}
        </div>
    `;
    
    sourcesContainer.innerHTML = sourcesHtml;
}

// 完成消息（渲染Markdown）
function finalizeMessage(messageId, fullText) {
    const messageEl = document.getElementById(messageId);
    if (!messageEl) return;
    
    const contentEl = messageEl.querySelector('.markdown-content');
    if (!contentEl) return;
    
    // 渲染Markdown
    contentEl.innerHTML = marked.parse(fullText);
    
    // 代码高亮
    contentEl.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
    
    scrollToBottom();
}

function appendAssistantMessage(content, sources = []) {
    const container = document.getElementById('messagesContainer');
    const time = formatTime(new Date().toISOString());
    
    let sourcesHtml = '';
    if (sources && sources.length > 0) {
        sourcesHtml = `
            <div class="flex flex-wrap gap-2 mt-2">
                ${sources.map((src, i) => `
                    <span class="source-tag" title="${escapeHtml(src.content || '')}">
                        <i class="fa fa-file-text-o"></i>
                        来源${i + 1} (${(src.similarity * 100).toFixed(1)}%)
                    </span>
                `).join('')}
            </div>
        `;
    }
    
    const messageHtml = `
        <div class="flex justify-start">
            <div class="message-assistant">
                <div class="flex items-center space-x-2 mb-2">
                    <i class="fa fa-robot text-primary"></i>
                    <span class="text-xs font-medium text-gray-500">AI助手</span>
                </div>
                <div class="markdown-content">${escapeHtml(content)}</div>
                ${sourcesHtml}
                <div class="text-xs text-gray-400 mt-2">${time}</div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHtml);
    
    // 渲染Markdown
    const lastMessage = container.lastElementChild.querySelector('.markdown-content');
    if (lastMessage) {
        lastMessage.innerHTML = marked.parse(content);
        
        // 代码高亮
        lastMessage.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
    }
    
    scrollToBottom();
}

// ==================== 工具函数 ====================

function groupConversationsByDate(convs) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(today);
    lastWeek.setDate(lastWeek.getDate() - 7);
    
    const groups = {
        '今天': [],
        '昨天': [],
        '最近7天': [],
        '更早': []
    };
    
    convs.forEach(conv => {
        const date = new Date(conv.updated_at);
        if (date >= today) {
            groups['今天'].push(conv);
        } else if (date >= yesterday) {
            groups['昨天'].push(conv);
        } else if (date >= lastWeek) {
            groups['最近7天'].push(conv);
        } else {
            groups['更早'].push(conv);
        }
    });
    
    // 移除空分组
    Object.keys(groups).forEach(key => {
        if (groups[key].length === 0) delete groups[key];
    });
    
    return groups;
}

function formatTime(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
    if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
    
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (date >= today) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    
    return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) {
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 100);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showMessage(message, type = 'info') {
    // 简单的消息提示
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };
    
    const toast = document.createElement('div');
    toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 transition-opacity`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
