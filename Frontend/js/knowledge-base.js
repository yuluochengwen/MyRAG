/**
 * 知识库管理页面脚本
 */

// API基础URL
const API_BASE_URL = '/api';

// WebSocket客户端
let wsClient = null;

// 当前处理中的知识库
let processingKB = new Set();

/**
 * 初始化
 */
document.addEventListener('DOMContentLoaded', () => {
    // 初始化WebSocket
    initWebSocket();
    
    // 加载知识库列表
    loadKnowledgeBases();
    
    // 加载嵌入模型列表
    loadEmbeddingModels();
    
    // 绑定事件
    bindEvents();
});

/**
 * 初始化WebSocket
 */
function initWebSocket() {
    wsClient = new WebSocketClient();
    
    // 注册消息处理器
    wsClient.on('progress', handleProgress);
    wsClient.on('error', handleError);
    wsClient.on('complete', handleComplete);
    
    // 连接
    wsClient.connect();
}

/**
 * 处理进度消息
 */
function handleProgress(data) {
    console.log('处理进度:', data);
    
    const { kb_id, stage, progress, message } = data;
    
    // 更新进度条
    updateProgress(kb_id, progress, message);
    
    // 标记为处理中
    processingKB.add(kb_id);
}

/**
 * 处理错误消息
 */
function handleError(data) {
    console.error('处理错误:', data);
    
    const { kb_id, error, detail } = data;
    
    // 显示错误
    showNotification(`错误: ${error}${detail ? ' - ' + detail : ''}`, 'error');
    
    // 移除处理中标记
    processingKB.delete(kb_id);
    
    // 重新加载列表
    loadKnowledgeBases();
}

/**
 * 处理完成消息
 */
function handleComplete(data) {
    console.log('处理完成:', data);
    
    const { kb_id, message } = data;
    
    // 显示通知
    showNotification(message, 'success');
    
    // 移除处理中标记
    processingKB.delete(kb_id);
    
    // 重新加载列表
    loadKnowledgeBases();
}

/**
 * 更新进度
 */
function updateProgress(kbId, progress, message) {
    // TODO: 实现进度条UI更新
    console.log(`知识库 ${kbId}: ${progress}% - ${message}`);
}

/**
 * 绑定事件
 */
function bindEvents() {
    // 创建知识库按钮
    const createBtn = document.getElementById('createKBBtn');
    if (createBtn) {
        createBtn.addEventListener('click', showCreateModal);
    }
    
    // 关闭模态框按钮
    const closeBtn = document.getElementById('closeModalBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeCreateModal);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeCreateModal);
    }
    
    // 点击遮罩关闭模态框
    const modal = document.getElementById('createKBModal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeCreateModal();
            }
        });
    }
    
    // Provider切换监听
    const providerSelect = document.getElementById('embeddingProvider');
    if (providerSelect) {
        providerSelect.addEventListener('change', (e) => {
            const provider = e.target.value;
            console.log('Provider切换:', provider);
            loadEmbeddingModels(provider);
        });
    }
    
    // 创建知识库表单提交
    const form = document.getElementById('createKBForm');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const name = formData.get('name').trim();
            const description = formData.get('description').trim();
            const embeddingModel = formData.get('embedding_model');
            const embeddingProvider = formData.get('embedding_provider');
            
            // 验证名称格式
            const namePattern = /^[\u4e00-\u9fa5a-zA-Z0-9_-]+$/;
            if (!namePattern.test(name)) {
                showNotification('知识库名称只能包含中文、英文、数字、下划线和连字符', 'error');
                return;
            }
            
            await createKnowledgeBase(name, description || null, embeddingModel, embeddingProvider);
        });
    }
    
    // 搜索框
    const searchInput = document.querySelector('input[type="text"][placeholder*="搜索"]');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearch);
    }
}

/**
 * 加载知识库列表
 */
async function loadKnowledgeBases() {
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases`);
        
        if (!response.ok) {
            throw new Error('获取知识库列表失败');
        }
        
        const kbs = await response.json();
        
        renderKnowledgeBases(kbs);
        
    } catch (error) {
        console.error('加载知识库失败:', error);
        showNotification('加载知识库失败', 'error');
    }
}

/**
 * 加载嵌入模型列表
 */
async function loadEmbeddingModels(provider = 'transformers') {
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/embedding/models?provider=${provider}`);
        
        if (!response.ok) {
            console.error('获取嵌入模型列表失败:', response.status, response.statusText);
            return;
        }
        
        const data = await response.json();
        const models = data.models || [];
        console.log(`加载的${provider}嵌入模型:`, models);
        
        const selectElement = document.getElementById('embeddingModel');
        const modelHint = document.getElementById('modelHint');
        
        if (!selectElement) {
            console.error('找不到 embeddingModel 选择器');
            return;
        }
        
        selectElement.innerHTML = ''; // 清空现有选项
        
        if (models && models.length > 0) {
            models.forEach((model, index) => {
                const option = document.createElement('option');
                option.value = model.name;
                
                // 根据provider显示不同的格式
                if (provider === 'ollama') {
                    option.textContent = `🦙 ${model.name}${model.size ? ` (${model.size})` : ''}`;
                } else {
                    option.textContent = `🤖 ${model.name}${model.dimension ? ` (${model.dimension}维)` : ''}${model.size ? ` - ${model.size}` : ''}`;
                }
                
                option.dataset.provider = model.provider || provider;
                option.dataset.dimension = model.dimension || '';
                
                // 默认选中第一个
                if (index === 0) {
                    option.selected = true;
                }
                
                selectElement.appendChild(option);
            });
            
            // 更新提示文本
            if (modelHint) {
                if (provider === 'ollama') {
                    modelHint.textContent = `找到 ${models.length} 个Ollama模型`;
                } else {
                    modelHint.textContent = `找到 ${models.length} 个Transformers模型`;
                }
            }
            
            console.log(`已添加 ${models.length} 个${provider}嵌入模型到选择器`);
        } else {
            // 如果没有模型，显示提示
            const option = document.createElement('option');
            option.value = '';
            if (provider === 'ollama') {
                option.textContent = '⚠️ Ollama服务不可用或无嵌入模型';
            } else {
                option.textContent = '⚠️ 没有可用的模型';
            }
            option.disabled = true;
            selectElement.appendChild(option);
            
            if (modelHint) {
                if (provider === 'ollama') {
                    modelHint.textContent = '请确保Ollama服务运行并且已安装嵌入模型';
                    modelHint.className = 'mt-1 text-xs text-warning';
                } else {
                    modelHint.textContent = '未找到本地模型';
                    modelHint.className = 'mt-1 text-xs text-gray-500';
                }
            }
        }
        
    } catch (error) {
        console.error('加载嵌入模型失败:', error);
        showNotification('加载模型失败', 'error');
    }
}

/**
 * 显示模型下载警告
 */
function showDownloadWarning(modelName, sizeText) {
    const warningHtml = `
        <div class="bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-4" id="downloadWarning">
            <div class="flex">
                <div class="flex-shrink-0">
                    <svg class="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
                    </svg>
                </div>
                <div class="ml-3">
                    <p class="text-sm text-yellow-700">
                        <strong>注意：</strong>模型 <code class="bg-yellow-100 px-1 rounded">${modelName}</code> 未下载，首次使用将从 HuggingFace 自动下载（${sizeText}），请确保网络畅通。
                    </p>
                </div>
                <div class="ml-auto pl-3">
                    <button onclick="this.closest('#downloadWarning').remove()" class="text-yellow-400 hover:text-yellow-600">
                        <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                            <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    // 移除旧警告
    const oldWarning = document.getElementById('downloadWarning');
    if (oldWarning) {
        oldWarning.remove();
    }
    
    // 在表单前插入新警告
    const form = document.getElementById('createKBForm');
    if (form) {
        form.insertAdjacentHTML('beforebegin', warningHtml);
    }
}

/**
 * 渲染知识库列表
 */
function renderKnowledgeBases(kbs) {
    const container = document.getElementById('kbList');
    const createCard = document.getElementById('createKBCard');
    
    if (!container) {
        console.error('未找到知识库列表容器');
        return;
    }
    
    // 保存创建卡片的引用
    const createCardClone = createCard ? createCard.cloneNode(true) : null;
    
    // 清空容器
    container.innerHTML = '';
    
    // 先添加创建卡片
    if (createCardClone) {
        container.appendChild(createCardClone);
        // 重新绑定创建按钮事件
        const createBtn = createCardClone.querySelector('#createKBBtn');
        if (createBtn) {
            createBtn.addEventListener('click', showCreateModal);
        }
    }
    
    // 如果没有知识库，不显示任何提示，只保留创建卡片
    if (kbs.length === 0) {
        return;
    }
    
    // 渲染知识库卡片
    kbs.forEach(kb => {
        const card = document.createElement('div');
        card.className = 'bg-white rounded-xl p-6 card-shadow hover:shadow-lg transition-custom flex flex-col';
        card.setAttribute('data-kb-id', kb.id);
        
        card.innerHTML = `
            <div class="flex justify-between items-start mb-4">
                <div class="w-12 h-12 rounded-lg bg-primary/10 flex items-center justify-center">
                    <i class="fa fa-database text-primary text-xl"></i>
                </div>
                <span class="px-2 py-1 text-xs rounded-full ${getStatusClass(kb.status)}">
                    ${getStatusText(kb.status)}
                </span>
            </div>
            
            <h3 class="text-lg font-bold mb-1">${escapeHtml(kb.name)}</h3>
            <p class="text-gray-500 text-sm mb-4 line-clamp-2">
                ${escapeHtml(kb.description || '暂无描述')}
            </p>
            
            <div class="flex flex-wrap gap-2 mb-4">
                <span onclick="viewFiles(${kb.id}, event)" class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full cursor-pointer hover:bg-blue-100 transition-custom" title="点击查看文件列表">
                    <i class="fa fa-file-o mr-1"></i>${kb.file_count} 文件
                </span>
                <span onclick="viewChunks(${kb.id}, event)" class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full cursor-pointer hover:bg-green-100 transition-custom" title="点击查看分块详情">
                    <i class="fa fa-cubes mr-1"></i>${kb.chunk_count} 块
                </span>
            </div>
            
            <div class="mt-auto pt-4 border-t border-gray-100">
                <div class="text-xs text-gray-400 mb-3">
                    <i class="fa fa-microchip mr-1"></i>${escapeHtml(kb.embedding_model.split('/').pop())}
                </div>
                <div class="flex space-x-2">
                    <button onclick="testSearch(${kb.id})" 
                            class="flex-1 px-3 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition-custom text-sm"
                            title="测试检索功能">
                        <i class="fa fa-search mr-1"></i>检索
                    </button>
                    <button onclick="uploadFile(${kb.id})" 
                            class="flex-1 px-3 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom text-sm">
                        <i class="fa fa-upload mr-1"></i>上传
                    </button>
                    <button onclick="deleteKB(${kb.id}, '${escapeHtml(kb.name)}')" 
                            class="px-3 py-2 bg-danger text-white rounded-lg hover:bg-danger/90 transition-custom text-sm">
                        <i class="fa fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        
        container.appendChild(card);
    });
}

/**
 * 获取状态样式类
 */
function getStatusClass(status) {
    const classes = {
        'ready': 'bg-success/10 text-success',
        'processing': 'bg-warning/10 text-warning',
        'error': 'bg-danger/10 text-danger'
    };
    return classes[status] || 'bg-gray-100 text-gray-800';
}

/**
 * 获取状态文本
 */
function getStatusText(status) {
    const texts = {
        'ready': '就绪',
        'processing': '处理中',
        'error': '错误'
    };
    return texts[status] || status;
}

/**
 * 显示创建模态框
 */
function showCreateModal() {
    const modal = document.getElementById('createKBModal');
    if (modal) {
        modal.classList.remove('hidden');
        // 清空表单
        document.getElementById('createKBForm').reset();
    }
}

/**
 * 关闭创建模态框
 */
function closeCreateModal() {
    const modal = document.getElementById('createKBModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

/**
 * 创建知识库
 */
async function createKnowledgeBase(name, description, embeddingModel, embeddingProvider = 'transformers') {
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name,
                description: description || null,
                embedding_model: embeddingModel || 'paraphrase-multilingual-MiniLM-L12-v2',
                embedding_provider: embeddingProvider
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '创建知识库失败');
        }
        
        const kb = await response.json();
        
        showNotification(`知识库 "${kb.name}" 创建成功`, 'success');
        
        // 关闭模态框
        closeCreateModal();
        
        // 重新加载列表
        loadKnowledgeBases();
        
    } catch (error) {
        console.error('创建知识库失败:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * 上传文件
 */
async function uploadFile(kbId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.pdf,.docx,.html,.md';
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch(
                `${API_BASE_URL}/knowledge-bases/${kbId}/upload?client_id=${wsClient.clientId}`,
                {
                    method: 'POST',
                    body: formData
                }
            );
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '文件上传失败');
            }
            
            const result = await response.json();
            
            showNotification(result.message, 'success');
            
        } catch (error) {
            console.error('上传文件失败:', error);
            showNotification(error.message, 'error');
        }
    };
    
    input.click();
}

/**
 * 查看知识库详情
 */
function viewKB(kbId) {
    // TODO: 实现详情页面
    console.log('查看知识库:', kbId);
}

/**
 * 删除知识库
 */
async function deleteKB(kbId, name) {
    if (!confirm(`确定要删除知识库 "${name}" 吗？此操作不可恢复。`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '删除知识库失败');
        }
        
        const result = await response.json();
        
        showNotification(result.message, 'success');
        
        // 重新加载列表
        loadKnowledgeBases();
        
    } catch (error) {
        console.error('删除知识库失败:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * 搜索处理
 */
function handleSearch(e) {
    const keyword = e.target.value.toLowerCase();
    
    const cards = document.querySelectorAll('#kbList > div');
    
    cards.forEach(card => {
        const name = card.querySelector('h3').textContent.toLowerCase();
        const description = card.querySelector('p').textContent.toLowerCase();
        
        if (name.includes(keyword) || description.includes(keyword)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-4 rounded-lg shadow-lg z-50 flex items-center space-x-3 animate-slide-in`;
    
    // 根据类型设置样式和图标
    const config = {
        'success': { bg: 'bg-success', icon: 'fa-check-circle' },
        'error': { bg: 'bg-danger', icon: 'fa-exclamation-circle' },
        'warning': { bg: 'bg-warning', icon: 'fa-exclamation-triangle' },
        'info': { bg: 'bg-primary', icon: 'fa-info-circle' }
    };
    
    const { bg, icon } = config[type] || config.info;
    notification.className += ` ${bg} text-white`;
    
    notification.innerHTML = `
        <i class="fa ${icon} text-xl"></i>
        <span class="font-medium">${escapeHtml(message)}</span>
    `;
    
    document.body.appendChild(notification);
    
    // 3秒后自动移除
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

/**
 * 转义HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 测试知识库检索
 */
async function testSearch(kbId) {
    const query = prompt('请输入测试问题:');
    if (!query || !query.trim()) return;
    
    try {
        showNotification('正在检索...', 'info');
        
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query.trim(),
                top_k: 5,
                score_threshold: 0.3
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '检索失败');
        }
        
        const result = await response.json();
        
        // 显示检索结果
        showSearchResults(result);
        
    } catch (error) {
        console.error('检索失败:', error);
        showNotification(error.message, 'error');
    }
}

/**
 * 显示检索结果
 */
function showSearchResults(result) {
    const resultsHtml = result.results.length > 0 
        ? result.results.map((r, i) => `
            <div class="border-l-4 border-primary pl-4 mb-4 bg-gray-50 p-3 rounded">
                <div class="flex justify-between items-center mb-2">
                    <span class="font-bold text-gray-700">#${i+1}</span>
                    <span class="text-sm px-2 py-1 rounded-full ${
                        r.similarity > 0.7 ? 'bg-green-100 text-green-700' : 
                        r.similarity > 0.5 ? 'bg-yellow-100 text-yellow-700' : 
                        'bg-gray-100 text-gray-700'
                    }">
                        相似度: ${(r.similarity * 100).toFixed(1)}%
                    </span>
                </div>
                <p class="text-sm text-gray-700 whitespace-pre-wrap">${escapeHtml(r.content)}</p>
                <div class="text-xs text-gray-500 mt-2">
                    <i class="fa fa-file-o mr-1"></i>文件ID: ${r.metadata.file_id} | 
                    <i class="fa fa-bookmark-o mr-1"></i>块索引: ${r.metadata.chunk_index}
                </div>
            </div>
        `).join('')
        : '<div class="text-center text-gray-500 py-8"><i class="fa fa-search text-4xl mb-2"></i><p>未找到相关内容</p></div>';
    
    const html = `
        <div class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onclick="this.remove()">
            <div class="bg-white rounded-xl p-6 max-w-4xl w-full max-h-[85vh] overflow-y-auto" onclick="event.stopPropagation()">
                <div class="flex justify-between items-start mb-4">
                    <div>
                        <h3 class="text-xl font-bold mb-2">检索结果</h3>
                        <div class="flex flex-wrap gap-2 text-sm text-gray-600">
                            <span><i class="fa fa-database mr-1"></i>${escapeHtml(result.kb_name)}</span>
                            <span>|</span>
                            <span><i class="fa fa-microchip mr-1"></i>${escapeHtml(result.embedding_model)}</span>
                            <span>|</span>
                            <span><i class="fa fa-search mr-1"></i>${result.total} 个结果</span>
                        </div>
                    </div>
                    <button onclick="this.closest('.fixed').remove()" 
                            class="p-2 hover:bg-gray-100 rounded-lg transition-custom">
                        <i class="fa fa-times text-xl text-gray-400"></i>
                    </button>
                </div>
                
                <div class="mb-4 p-3 bg-blue-50 rounded-lg">
                    <div class="text-sm text-blue-800">
                        <i class="fa fa-question-circle mr-1"></i>
                        <strong>查询:</strong> ${escapeHtml(result.query)}
                    </div>
                </div>
                
                <div class="space-y-3">
                    ${resultsHtml}
                </div>
                
                <div class="mt-4 pt-4 border-t">
                    <button onclick="this.closest('.fixed').remove()" 
                            class="w-full px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">
                        关闭
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', html);
}

/**
 * 查看文件列表
 */
async function viewFiles(kbId, event) {
    event.stopPropagation();
    
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/files`);
        if (!response.ok) throw new Error('获取文件列表失败');
        
        const files = await response.json();
        
        const modal = document.getElementById('filesModal');
        const content = document.getElementById('filesContent');
        
        if (files.length === 0) {
            content.innerHTML = '<p class="text-center text-gray-500 py-8">暂无文件</p>';
        } else {
            content.innerHTML = files.map(file => `
                <div class="p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-custom cursor-pointer" onclick="viewFileContent(${kbId}, ${file.id}, '${escapeHtml(file.filename)}')">
                    <div class="flex items-center justify-between">
                        <div class="flex-1">
                            <div class="flex items-center space-x-2 mb-2">
                                <i class="fa fa-file-o text-blue-500"></i>
                                <span class="font-medium hover:text-primary">${escapeHtml(file.filename)}</span>
                                <span class="px-2 py-0.5 bg-blue-100 text-blue-600 text-xs rounded">${escapeHtml(file.file_type)}</span>
                                <span class="px-2 py-0.5 ${getFileStatusClass(file.status)} text-xs rounded">${getFileStatusText(file.status)}</span>
                            </div>
                            <div class="text-sm text-gray-500">
                                <span>大小: ${formatFileSize(file.file_size)}</span>
                                <span class="ml-3 text-xs text-primary">点击查看内容 →</span>
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        modal.classList.remove('hidden');
        
    } catch (error) {
        console.error('加载文件列表失败:', error);
        alert('加载文件列表失败: ' + error.message);
    }
}

/**
 * 查看文本块列表
 */
async function viewChunks(kbId, event) {
    event.stopPropagation();
    
    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/chunks`);
        if (!response.ok) throw new Error('获取文本块列表失败');
        
        const data = await response.json();
        const chunks = data.chunks || [];
        
        const modal = document.getElementById('chunksModal');
        const content = document.getElementById('chunksContent');
        
        if (chunks.length === 0) {
            content.innerHTML = '<div class="text-center py-8"><div class="text-gray-400 mb-2"><i class="fa fa-inbox text-4xl"></i></div><p class="text-gray-500">暂无文本块</p><p class="text-sm text-gray-400 mt-2">文件处理完成后会自动生成文本块</p></div>';
        } else {
            // 按文件分组显示
            const groupedChunks = {};
            chunks.forEach(chunk => {
                if (!groupedChunks[chunk.file_id]) {
                    groupedChunks[chunk.file_id] = {
                        filename: chunk.filename,
                        file_type: chunk.file_type,
                        chunks: []
                    };
                }
                groupedChunks[chunk.file_id].chunks.push(chunk);
            });
            
            content.innerHTML = `
                <div class="mb-4 p-3 bg-blue-50 rounded-lg text-sm text-blue-800">
                    <i class="fa fa-info-circle mr-2"></i>共 ${chunks.length} 个文本块，来自 ${Object.keys(groupedChunks).length} 个文件
                </div>
            ` + Object.entries(groupedChunks).map(([fileId, fileData]) => `
                <div class="border border-gray-200 rounded-lg overflow-hidden mb-4">
                    <div class="bg-gradient-to-r from-blue-50 to-blue-100 px-4 py-3 flex items-center justify-between">
                        <div class="flex items-center space-x-2">
                            <i class="fa fa-file-text-o text-blue-600"></i>
                            <span class="font-medium text-blue-900">${escapeHtml(fileData.filename)}</span>
                            <span class="px-2 py-0.5 bg-white text-blue-600 text-xs rounded shadow-sm">${escapeHtml(fileData.file_type)}</span>
                        </div>
                        <span class="text-sm font-medium text-blue-700 bg-white px-3 py-1 rounded-full shadow-sm">${fileData.chunks.length} 个块</span>
                    </div>
                    <div class="divide-y divide-gray-200">
                        ${fileData.chunks.map((chunk, idx) => `
                            <div class="p-4 hover:bg-gray-50 transition-custom ${idx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}">
                                <div class="flex items-start justify-between mb-3">
                                    <div class="flex items-center space-x-2">
                                        <span class="px-2 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded">块 #${chunk.chunk_index + 1}</span>
                                        <span class="text-xs text-gray-500">${chunk.content.length} 字符</span>
                                    </div>
                                    <span class="text-xs text-gray-400">${new Date(chunk.created_at).toLocaleString('zh-CN')}</span>
                                </div>
                                <div class="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap bg-white p-3 rounded border border-gray-100">${escapeHtml(chunk.content.substring(0, 500))}${chunk.content.length > 500 ? '<span class="text-gray-400">...</span>' : ''}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        }
        
        modal.classList.remove('hidden');
        
    } catch (error) {
        console.error('加载文本块列表失败:', error);
        alert('加载文本块列表失败: ' + error.message);
    }
}

/**
 * 关闭文件列表模态框
 */
function closeFilesModal() {
    document.getElementById('filesModal').classList.add('hidden');
}

/**
 * 关闭文本块模态框
 */
function closeChunksModal() {
    document.getElementById('chunksModal').classList.add('hidden');
}

/**
 * 获取文件状态样式
 */
function getFileStatusClass(status) {
    const statusMap = {
        'uploaded': 'bg-blue-100 text-blue-600',
        'parsing': 'bg-yellow-100 text-yellow-600',
        'parsed': 'bg-blue-100 text-blue-600',
        'embedding': 'bg-purple-100 text-purple-600',
        'completed': 'bg-green-100 text-green-600',
        'error': 'bg-red-100 text-red-600'
    };
    return statusMap[status] || 'bg-gray-100 text-gray-600';
}

/**
 * 获取文件状态文本
 */
function getFileStatusText(status) {
    const statusMap = {
        'uploaded': '已上传',
        'parsing': '解析中',
        'parsed': '已解析',
        'embedding': '向量化中',
        'completed': '已完成',
        'error': '错误'
    };
    return statusMap[status] || status;
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * 查看文件内容
 */
async function viewFileContent(kbId, fileId, filename) {
    try {
        // 显示加载状态
        const modal = document.getElementById('fileContentModal');
        const titleEl = document.getElementById('fileContentTitle');
        const infoEl = document.getElementById('fileContentInfo');
        const bodyEl = document.getElementById('fileContentBody');
        
        titleEl.textContent = filename;
        infoEl.textContent = '加载中...';
        bodyEl.innerHTML = '<div class="flex items-center justify-center py-12"><i class="fa fa-spinner fa-spin text-3xl text-primary"></i></div>';
        
        modal.classList.remove('hidden');
        
        // 获取文件内容
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/files/${fileId}/content`);
        if (!response.ok) throw new Error('获取文件内容失败');
        
        const data = await response.json();
        
        // 更新信息
        infoEl.textContent = `${data.file_type} | ${formatFileSize(data.file_size)} | ${data.chunk_count} 个文本块`;
        
        // 显示内容 - 根据文件类型使用不同的显示方式
        const fileType = data.file_type.toLowerCase();
        if (fileType === 'pdf' || fileType === 'docx' || fileType === 'doc') {
            // 对于 PDF 和 Word 文档，使用段落分隔显示
            const paragraphs = data.content.split('\n').filter(p => p.trim());
            bodyEl.innerHTML = paragraphs.map(p => 
                `<p class="mb-3 text-sm leading-relaxed text-gray-700">${escapeHtml(p)}</p>`
            ).join('');
        } else if (fileType === 'html' || fileType === 'htm') {
            // HTML 文件显示代码
            bodyEl.innerHTML = `<pre class="whitespace-pre-wrap text-xs leading-relaxed text-gray-700 font-mono bg-gray-100 p-4 rounded">${escapeHtml(data.content)}</pre>`;
        } else if (fileType === 'json') {
            // JSON 格式化显示
            try {
                const jsonObj = JSON.parse(data.content);
                const formatted = JSON.stringify(jsonObj, null, 2);
                bodyEl.innerHTML = `<pre class="whitespace-pre-wrap text-xs leading-relaxed text-gray-700 font-mono bg-gray-100 p-4 rounded">${escapeHtml(formatted)}</pre>`;
            } catch (e) {
                bodyEl.innerHTML = `<pre class="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">${escapeHtml(data.content)}</pre>`;
            }
        } else if (fileType === 'md') {
            // Markdown 保留格式
            bodyEl.innerHTML = `<pre class="whitespace-pre-wrap text-sm leading-relaxed text-gray-700 font-mono">${escapeHtml(data.content)}</pre>`;
        } else {
            // 默认文本显示（txt等）
            bodyEl.innerHTML = `<pre class="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">${escapeHtml(data.content)}</pre>`;
        }
        
    } catch (error) {
        console.error('加载文件内容失败:', error);
        const bodyEl = document.getElementById('fileContentBody');
        bodyEl.innerHTML = `<div class="text-center text-red-500 py-8"><i class="fa fa-exclamation-triangle mr-2"></i>加载失败: ${error.message}</div>`;
    }
}

/**
 * 关闭文件内容模态框
 */
function closeFileContentModal() {
    document.getElementById('fileContentModal').classList.add('hidden');
}

