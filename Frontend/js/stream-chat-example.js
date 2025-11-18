/**
 * 流式聊天功能示例
 * 
 * 在 chat.js 中集成流式响应的示例代码
 */

// ==================== 流式聊天请求 ====================

/**
 * 发送流式聊天请求（SSE - Server-Sent Events）
 * @param {number} conversationId - 对话ID
 * @param {string} query - 用户问题
 * @param {number} temperature - 温度参数
 */
async function sendChatRequestStream(conversationId, query, temperature = 0.7) {
    try {
        const url = `${API_BASE_URL}/api/conversations/${conversationId}/chat/stream`;
        
        // 创建EventSource或使用fetch API
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                temperature: temperature,
                max_tokens: 2048
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // 获取reader用于流式读取
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        let buffer = '';
        let currentMessageDiv = null;
        let sourcesDisplayed = false;
        
        // 创建AI消息容器
        currentMessageDiv = appendAIMessagePlaceholder();
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                console.log('Stream complete');
                break;
            }
            
            // 解码数据
            buffer += decoder.decode(value, { stream: true });
            
            // 处理SSE格式的数据 (data: {...}\n\n)
            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // 保留未完成的行
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const jsonStr = line.slice(6); // 移除 "data: " 前缀
                    
                    try {
                        const chunk = JSON.parse(jsonStr);
                        
                        // 处理不同类型的消息
                        switch (chunk.type) {
                            case 'sources':
                                // 显示检索来源
                                if (!sourcesDisplayed) {
                                    displaySources(currentMessageDiv, chunk.data);
                                    sourcesDisplayed = true;
                                }
                                break;
                            
                            case 'text':
                                // 逐步显示生成的文本
                                appendTextToMessage(currentMessageDiv, chunk.data);
                                scrollToBottom();
                                break;
                            
                            case 'done':
                                // 完成，进行最后的格式化
                                finalizeMessage(currentMessageDiv);
                                break;
                            
                            case 'error':
                                // 显示错误
                                showError(chunk.data.error);
                                break;
                        }
                    } catch (e) {
                        console.error('JSON parse error:', e, jsonStr);
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('Stream error:', error);
        throw error;
    }
}


// ==================== 辅助函数 ====================

/**
 * 创建AI消息占位符
 */
function appendAIMessagePlaceholder() {
    const container = document.getElementById('messagesContainer');
    const time = formatTime(new Date().toISOString());
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'flex justify-start';
    messageDiv.innerHTML = `
        <div class="message-assistant">
            <div class="flex items-center space-x-2 mb-2">
                <i class="fa fa-robot text-primary"></i>
                <span class="text-xs font-medium text-gray-500">AI助手</span>
            </div>
            <div class="markdown-content" id="streaming-content"></div>
            <div class="sources-container"></div>
            <div class="text-xs text-gray-400 mt-2">${time}</div>
        </div>
    `;
    
    container.appendChild(messageDiv);
    return messageDiv;
}

/**
 * 追加文本到消息中
 */
function appendTextToMessage(messageDiv, text) {
    const contentDiv = messageDiv.querySelector('#streaming-content');
    if (contentDiv) {
        // 直接追加文本（稍后会统一渲染Markdown）
        contentDiv.textContent += text;
    }
}

/**
 * 显示检索来源
 */
function displaySources(messageDiv, sourcesData) {
    const sourcesContainer = messageDiv.querySelector('.sources-container');
    if (sourcesContainer && sourcesData.sources && sourcesData.sources.length > 0) {
        const sourcesHtml = `
            <div class="flex flex-wrap gap-2 mt-2">
                ${sourcesData.sources.map((src, i) => `
                    <span class="source-tag" title="${escapeHtml(src.content || '')}">
                        <i class="fa fa-file-text-o"></i>
                        来源${i + 1} (${(src.similarity * 100).toFixed(1)}%)
                    </span>
                `).join('')}
            </div>
        `;
        sourcesContainer.innerHTML = sourcesHtml;
    }
}

/**
 * 完成消息渲染
 */
function finalizeMessage(messageDiv) {
    const contentDiv = messageDiv.querySelector('#streaming-content');
    if (contentDiv) {
        // 渲染Markdown
        const text = contentDiv.textContent;
        contentDiv.innerHTML = marked.parse(text);
        
        // 代码高亮
        contentDiv.querySelectorAll('pre code').forEach(block => {
            hljs.highlightElement(block);
        });
        
        // 移除ID（不再需要流式更新）
        contentDiv.removeAttribute('id');
    }
}

/**
 * 显示错误
 */
function showError(errorMsg) {
    const container = document.getElementById('messagesContainer');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded';
    errorDiv.textContent = `错误: ${errorMsg}`;
    container.appendChild(errorDiv);
    scrollToBottom();
}


// ==================== 使用示例 ====================

/**
 * 替换原来的 sendChatRequest 函数
 * 
 * 在 handleSendMessage 中调用：
 * 
 * async function handleSendMessage(e) {
 *     e.preventDefault();
 *     
 *     if (isProcessing) return;
 *     if (!currentConversation) return;
 *     
 *     const input = document.getElementById('messageInput');
 *     const message = input.value.trim();
 *     if (!message) return;
 *     
 *     try {
 *         isProcessing = true;
 *         input.value = '';
 *         
 *         // 显示用户消息
 *         appendUserMessage(message);
 *         
 *         // 调用流式API
 *         await sendChatRequestStream(currentConversation.id, message, 0.7);
 *         
 *         // 更新对话列表
 *         await loadConversations(currentAssistant.id);
 *         
 *     } catch (error) {
 *         console.error('发送消息失败:', error);
 *         showMessage('发送失败: ' + error.message, 'error');
 *     } finally {
 *         isProcessing = false;
 *         document.getElementById('sendBtn').disabled = false;
 *     }
 * }
 */


// ==================== 兼容性说明 ====================

/**
 * 流式响应的优势：
 * 1. 实时反馈：用户可以立即看到AI开始回答
 * 2. 更好体验：类似ChatGPT的打字机效果
 * 3. 降低超时：长文本生成不会超时
 * 
 * 浏览器兼容性：
 * - 支持所有现代浏览器（Chrome、Firefox、Safari、Edge）
 * - 使用Fetch API + ReadableStream
 * - SSE (Server-Sent Events) 格式
 * 
 * 注意事项：
 * - Nginx需要配置 proxy_buffering off; 来禁用缓冲
 * - 确保设置正确的CORS头
 * - 客户端需要处理连接中断和重连
 */
