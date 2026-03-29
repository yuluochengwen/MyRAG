/**
 * 知识库管理页面脚本
 */

// API基础URL
const API_BASE_URL = '/api';

// WebSocket客户端
let wsClient = null;

// 当前处理中的知识库
let processingKB = new Set();

// 当前详情中的知识库
let activeKBId = null;
let kbGraphSimulation = null;
let activeKBTab = 'graph';
let kbFilesLoaded = false;
let kbChunksLoaded = false;
let kbCurrentGraphNodes = [];
let kbCurrentGraphLinks = [];

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
 * 确保WebSocket连接可用（上传前调用）
 */
async function ensureWebSocketReady(timeoutMs = 5000) {
    if (!wsClient) {
        initWebSocket();
    }

    if (wsClient && wsClient.isConnected()) {
        return true;
    }

    if (wsClient) {
        wsClient.connect();
    }

    const startAt = Date.now();
    while (Date.now() - startAt < timeoutMs) {
        if (wsClient && wsClient.isConnected()) {
            return true;
        }
        await new Promise((resolve) => setTimeout(resolve, 100));
    }

    return false;
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

    // 详情弹窗：点击遮罩关闭
    const detailModal = document.getElementById('kbDetailModal');
    if (detailModal) {
        detailModal.addEventListener('click', (e) => {
            if (e.target === detailModal) {
                closeKBDetailModal();
            }
        });
    }

    // 详情弹窗：刷新图谱
    const refreshBtn = document.getElementById('kbGraphRefreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            if (activeKBId) {
                loadKBGraphPreview(activeKBId, true);
            }
        });
    }

    // 详情页标签切换
    const tabsRoot = document.getElementById('kbDetailTabs');
    if (tabsRoot) {
        tabsRoot.addEventListener('click', (event) => {
            const btn = event.target.closest('[data-tab]');
            if (!btn) return;
            const tab = btn.getAttribute('data-tab');
            setKBDetailTab(tab);
        });
    }

    const filesPanel = document.getElementById('kbFilesPanelContent');
    if (filesPanel) {
        filesPanel.addEventListener('click', async (event) => {
            const actionBtn = event.target.closest('[data-action]');
            if (!actionBtn || !activeKBId) return;

            const fileId = Number(actionBtn.getAttribute('data-file-id'));
            const filename = actionBtn.getAttribute('data-filename') || '未命名文件';
            if (!Number.isFinite(fileId) || fileId <= 0) return;

            const action = actionBtn.getAttribute('data-action');
            if (action === 'preview-file') {
                await viewFileContent(activeKBId, fileId, filename);
                return;
            }
            if (action === 'delete-file') {
                await deleteKBFile(activeKBId, fileId, filename);
            }
        });
    }

    const previewCloseBtn = document.getElementById('kbFilePreviewCloseBtn');
    if (previewCloseBtn) {
        previewCloseBtn.addEventListener('click', () => {
            closeKBFilePreview();
        });
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
        card.className = 'bg-white rounded-xl p-6 card-shadow hover:shadow-lg transition-custom flex flex-col kb-card-clickable';
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
                <span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full" title="文件数量">
                    <i class="fa fa-file-o mr-1"></i>${kb.file_count} 文件
                </span>
                <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full" title="文本块数量">
                    <i class="fa fa-cubes mr-1"></i>${kb.chunk_count} 块
                </span>
                ${renderGraphStats(kb)}
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

        card.addEventListener('click', (event) => {
            // 卡片中的按钮/标签行为优先，不触发详情弹窗
            if (event.target.closest('button') || event.target.closest('[onclick]')) {
                return;
            }
            openKBDetailModal(kb.id);
        });
        
        container.appendChild(card);
    });
}

/**
 * 渲染知识图谱统计信息
 */
function renderGraphStats(kb) {
    if (!kb.graph_stats) {
        return '';
    }
    
    const stats = kb.graph_stats;
    const nodeCount = stats.node_count || 0;
    const edgeCount = stats.edge_count || 0;
    
    if (nodeCount === 0 && edgeCount === 0) {
        return '';
    }
    
    return `
        <span class="px-2 py-1 bg-purple-50 text-purple-600 text-xs rounded-full" title="图谱统计">
            <i class="fa fa-sitemap mr-1"></i>${nodeCount} 节点 / ${edgeCount} 关系
        </span>
    `;
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
        
        // 显示处理提示
        showNotification('正在处理文件...', 'info');
        
        try {
            const wsReady = await ensureWebSocketReady();
            if (!wsReady) {
                showNotification('进度通道未连接，任务仍会执行但不会实时显示进度', 'warning');
            }

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
            
            // 注意：实际的成功消息会由 WebSocket 的 handleComplete 显示
            // showNotification(result.message, 'success');
            
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
    openKBDetailModal(kbId);
}

/**
 * 打开知识库详情弹窗
 */
async function openKBDetailModal(kbId) {
    activeKBId = kbId;

    const modal = document.getElementById('kbDetailModal');
    const titleEl = document.getElementById('kbDetailTitle');
    const subTitleEl = document.getElementById('kbDetailSubTitle');
    const metaEl = document.getElementById('kbDetailMeta');
    const statsEl = document.getElementById('kbDetailStats');
    const entityTypeEl = document.getElementById('kbEntityTypeList');
    const inspectorEl = document.getElementById('kbEntityInspector');

    if (!modal) return;

    kbFilesLoaded = false;
    kbChunksLoaded = false;
    kbCurrentGraphNodes = [];
    kbCurrentGraphLinks = [];

    titleEl.textContent = '知识库详情';
    subTitleEl.textContent = `知识库 #${kbId}`;
    metaEl.innerHTML = '<p class="text-gray-500">加载中...</p>';
    statsEl.innerHTML = '';
    entityTypeEl.innerHTML = '<p class="text-gray-500 text-sm">加载中...</p>';
    if (inspectorEl) {
        inspectorEl.textContent = '点击图谱节点后，这里会显示实体属性和关联关系。';
    }

    modal.classList.remove('hidden');
    setKBDetailTab('graph');

    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`);
        if (!response.ok) {
            throw new Error('获取知识库详情失败');
        }

        const kb = await response.json();
        const stats = kb.graph_stats || {};

        titleEl.textContent = kb.name || `知识库 #${kbId}`;
        subTitleEl.textContent = kb.description
            ? kb.description
            : '暂无描述';

        metaEl.innerHTML = `
            <div><span class="text-gray-500">状态：</span><span class="font-medium">${escapeHtml(getStatusText(kb.status || 'ready'))}</span></div>
            <div><span class="text-gray-500">向量模型：</span><span class="font-medium">${escapeHtml((kb.embedding_model || '').split('/').pop() || '未知')}</span></div>
            <div><span class="text-gray-500">创建时间：</span><span class="font-medium">${formatDateTime(kb.created_at)}</span></div>
            <div><span class="text-gray-500">更新时间：</span><span class="font-medium">${formatDateTime(kb.updated_at)}</span></div>
        `;

        statsEl.innerHTML = `
            ${renderStatChip(stats.node_count || 0, '实体节点')}
            ${renderStatChip(stats.edge_count || 0, '关系边')}
            ${renderStatChip(kb.file_count || 0, '文件数')}
            ${renderStatChip(kb.chunk_count || 0, '文本块')}
        `;

        const entityTypes = Object.entries(stats.entity_types || {})
            .sort((a, b) => b[1] - a[1])
            .slice(0, 8);

        entityTypeEl.innerHTML = entityTypes.length > 0
            ? entityTypes.map(([type, count]) => `
                <div class="flex items-center justify-between px-3 py-2 rounded-lg bg-gray-50 border border-gray-100">
                    <span class="text-sm text-gray-700"><i class="fa fa-tag text-primary mr-2"></i>${escapeHtml(type)}</span>
                    <span class="text-sm font-semibold text-gray-800">${count}</span>
                </div>
            `).join('')
            : '<p class="text-gray-500 text-sm">暂无实体类型数据</p>';

        await loadKBGraphPreview(kbId, false);
    } catch (error) {
        console.error('加载知识库详情失败:', error);
        showNotification(error.message || '加载详情失败', 'error');
    }
}

/**
 * 关闭知识库详情弹窗
 */
function closeKBDetailModal() {
    activeKBId = null;
    const modal = document.getElementById('kbDetailModal');
    if (modal) {
        modal.classList.add('hidden');
    }

    if (kbGraphSimulation) {
        kbGraphSimulation.stop();
        kbGraphSimulation = null;
    }
}

function setKBDetailTab(tab) {
    const validTabs = ['graph', 'files', 'chunks'];
    if (!validTabs.includes(tab)) return;
    activeKBTab = tab;

    const titleMap = {
        graph: '知识图谱预览',
        files: '文件清单',
        chunks: '文本块浏览'
    };

    const hintMap = {
        graph: '展示全量实体关系（不含文本块节点）',
        files: '展示该知识库中已上传文件',
        chunks: '浏览文本切分结果（前80条）'
    };

    const titleEl = document.getElementById('kbWorkbenchTitle');
    const hintEl = document.getElementById('kbGraphHint');
    if (titleEl) {
        titleEl.textContent = titleMap[tab] || '知识库详情';
    }
    if (hintEl) {
        hintEl.textContent = hintMap[tab] || '';
    }

    document.querySelectorAll('.kb-detail-tab').forEach((btn) => {
        btn.classList.toggle('active', btn.getAttribute('data-tab') === tab);
    });

    const graphPanel = document.getElementById('kbTabPanelGraph');
    const filesPanel = document.getElementById('kbTabPanelFiles');
    const chunksPanel = document.getElementById('kbTabPanelChunks');

    if (graphPanel) graphPanel.classList.toggle('hidden', tab !== 'graph');
    if (filesPanel) filesPanel.classList.toggle('hidden', tab !== 'files');
    if (chunksPanel) chunksPanel.classList.toggle('hidden', tab !== 'chunks');

    const refreshBtn = document.getElementById('kbGraphRefreshBtn');
    if (refreshBtn) {
        refreshBtn.classList.toggle('hidden', tab !== 'graph');
    }

    if (tab === 'files' && activeKBId && !kbFilesLoaded) {
        loadKBFilesPanel(activeKBId);
    }
    if (tab === 'chunks' && activeKBId && !kbChunksLoaded) {
        loadKBChunksPanel(activeKBId);
    }

    if (tab !== 'files') {
        closeKBFilePreview();
    }
}

async function loadKBFilesPanel(kbId) {
    const panel = document.getElementById('kbFilesPanelContent');
    if (!panel) return;

    panel.innerHTML = '<div class="kb-list-item text-gray-500">正在加载文件列表...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/files`);
        if (!response.ok) {
            throw new Error('获取文件列表失败');
        }

        const files = await response.json();
        kbFilesLoaded = true;

        if (!Array.isArray(files) || files.length === 0) {
            panel.innerHTML = '<div class="kb-list-item text-gray-500">暂无文件</div>';
            return;
        }

        panel.innerHTML = files.map((file) => `
            <div class="kb-list-item">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <div class="kb-list-title"><i class="fa fa-file-o text-blue-500 mr-2"></i>${escapeHtml(file.filename || '未命名文件')}</div>
                        <div class="kb-list-sub">
                            类型：${escapeHtml(file.file_type || '未知')} | 大小：${formatFileSize(file.file_size || 0)} | 状态：${escapeHtml(getFileStatusText(file.status || 'uploaded'))}
                        </div>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <button
                            type="button"
                            class="px-3 py-1.5 text-xs rounded-lg border border-blue-200 text-blue-600 hover:bg-blue-50 transition-custom"
                            data-action="preview-file"
                            data-file-id="${file.id}"
                            data-filename="${escapeHtml(file.filename || '未命名文件')}"
                        >
                            <i class="fa fa-eye mr-1"></i>查看原文
                        </button>
                        <button
                            type="button"
                            class="px-3 py-1.5 text-xs rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition-custom"
                            data-action="delete-file"
                            data-file-id="${file.id}"
                            data-filename="${escapeHtml(file.filename || '未命名文件')}"
                        >
                            <i class="fa fa-trash mr-1"></i>删除
                        </button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        panel.innerHTML = `<div class="kb-list-item text-red-500">加载失败：${escapeHtml(error.message || '未知错误')}</div>`;
    }
}

async function loadKBChunksPanel(kbId) {
    const panel = document.getElementById('kbChunksPanelContent');
    if (!panel) return;

    panel.innerHTML = '<div class="kb-list-item text-gray-500">正在加载文本块...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/chunks`);
        if (!response.ok) {
            throw new Error('获取文本块失败');
        }

        const data = await response.json();
        const chunks = Array.isArray(data.chunks) ? data.chunks : [];
        kbChunksLoaded = true;

        if (chunks.length === 0) {
            panel.innerHTML = '<div class="kb-list-item text-gray-500">暂无文本块</div>';
            return;
        }

        panel.innerHTML = chunks.slice(0, 80).map((chunk) => `
            <div class="kb-list-item">
                <div class="kb-list-title">
                    <i class="fa fa-cube text-green-600 mr-2"></i>
                    ${escapeHtml(chunk.filename || '未知文件')} · 块 #${(chunk.chunk_index || 0) + 1}
                </div>
                <div class="kb-list-sub">${escapeHtml((chunk.content || '').slice(0, 180))}${(chunk.content || '').length > 180 ? '...' : ''}</div>
            </div>
        `).join('');
    } catch (error) {
        panel.innerHTML = `<div class="kb-list-item text-red-500">加载失败：${escapeHtml(error.message || '未知错误')}</div>`;
    }
}

/**
 * 加载知识库图谱预览
 */
async function loadKBGraphPreview(kbId, forceRefresh = false) {
    const loadingEl = document.getElementById('kbGraphLoading');
    const emptyEl = document.getElementById('kbGraphEmpty');
    const hintEl = document.getElementById('kbGraphHint');

    if (loadingEl) loadingEl.classList.remove('hidden');
    if (emptyEl) emptyEl.classList.add('hidden');

    try {
        const query = forceRefresh ? '&_ts=' + Date.now() : '';
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/graph/preview?include_all=true${query}`);
        if (!response.ok) {
            throw new Error('获取图谱预览失败');
        }

        const data = await response.json();
        const preview = data.preview || {};
        const nodes = Array.isArray(preview.nodes) ? preview.nodes : [];
        const links = Array.isArray(preview.links) ? preview.links : [];

        if (hintEl) {
            hintEl.textContent = `全量实体关系图：${nodes.length} 个实体，${links.length} 条关系（不含文本块节点）`;
        }

        renderKBGraphPreview(nodes, links);
    } catch (error) {
        console.error('加载图谱预览失败:', error);
        showNotification(error.message || '加载图谱失败', 'error');
        renderKBGraphPreview([], []);
    } finally {
        if (loadingEl) loadingEl.classList.add('hidden');
    }
}

/**
 * 渲染知识库图谱预览
 */
function renderKBGraphPreview(nodes, links) {
    const svgEl = document.getElementById('kbGraphSvg');
    const emptyEl = document.getElementById('kbGraphEmpty');
    const viewport = document.getElementById('kbGraphViewport');

    if (!svgEl || !viewport || typeof d3 === 'undefined') {
        return;
    }

    if (kbGraphSimulation) {
        kbGraphSimulation.stop();
        kbGraphSimulation = null;
    }

    const width = Math.max(360, viewport.clientWidth || 360);
    const height = Math.max(420, viewport.clientHeight || 420);

    const svg = d3.select(svgEl);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width} ${height}`);

    if (!Array.isArray(nodes) || nodes.length === 0) {
        if (emptyEl) emptyEl.classList.remove('hidden');
        return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');

    const nodeMap = new Map(nodes.map(n => [String(n.id), {
        id: String(n.id),
        name: String(n.name || n.id),
        type: String(n.type || 'Unknown'),
        mention_count: Number(n.mention_count || 0)
    }]));

    const graphLinks = (Array.isArray(links) ? links : [])
        .filter(l => nodeMap.has(String(l.source)) && nodeMap.has(String(l.target)))
        .map(l => ({
            source: String(l.source),
            target: String(l.target),
            relation: String(l.relation || '关联'),
            evidence_count: Number(l.evidence_count || 1)
        }));

    const graphNodes = Array.from(nodeMap.values());
    kbCurrentGraphNodes = graphNodes;
    kbCurrentGraphLinks = graphLinks;

    const defs = svg.append('defs');
    defs.append('marker')
        .attr('id', 'kb-arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#94a3b8');

    const g = svg.append('g');

    // 允许拖动画布与滚轮缩放，便于查看远处节点
    const zoomBehavior = d3.zoom()
        .scaleExtent([0.35, 3.2])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });

    svg
        .call(zoomBehavior)
        .on('dblclick.zoom', null)
        .style('cursor', 'grab')
        .on('mousedown', () => {
            svg.style('cursor', 'grabbing');
        })
        .on('mouseup', () => {
            svg.style('cursor', 'grab');
        })
        .on('mouseleave', () => {
            svg.style('cursor', 'grab');
        });

    // 初始化一个略微缩小并居中的视角，避免大图超出视野
    const initialTransform = d3.zoomIdentity
        .translate(width * 0.08, height * 0.06)
        .scale(0.95);
    svg.call(zoomBehavior.transform, initialTransform);

    const link = g.append('g')
        .selectAll('line')
        .data(graphLinks)
        .join('line')
        .attr('class', 'kb-graph-link')
        .attr('stroke-width', d => 1 + Math.min(2.2, d.evidence_count * 0.2))
        .attr('marker-end', 'url(#kb-arrowhead)');

    const node = g.append('g')
        .selectAll('g')
        .data(graphNodes)
        .join('g')
        .attr('class', 'kb-graph-node')
        .style('cursor', 'grab');

    node.append('circle')
        .attr('r', d => d.mention_count > 0 ? Math.min(18, 11 + Math.sqrt(d.mention_count)) : 11)
        .attr('fill', d => getTypeColor(d.type))
        .attr('stroke', '#fff')
        .attr('stroke-width', 2);

    node.append('text')
        .attr('dy', d => d.mention_count > 0 ? 28 : 24)
        .attr('text-anchor', 'middle')
        .text(d => d.name.length > 8 ? `${d.name.slice(0, 8)}...` : d.name);

    node.append('title')
        .text(d => `${d.name} (${d.type})`);

    node.on('click', (event, d) => {
        event.stopPropagation();

        node.selectAll('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .attr('opacity', 0.45);

        d3.select(event.currentTarget)
            .select('circle')
            .attr('stroke', '#0f172a')
            .attr('stroke-width', 3)
            .attr('opacity', 1);

        renderKBEntityInspector(d, graphLinks);
    });

    svg.on('click', () => {
        node.selectAll('circle')
            .attr('stroke', '#fff')
            .attr('stroke-width', 2)
            .attr('opacity', 1);
        const inspector = document.getElementById('kbEntityInspector');
        if (inspector) {
            inspector.textContent = '点击图谱节点后，这里会显示实体属性和关联关系。';
        }
    });

    kbGraphSimulation = d3.forceSimulation(graphNodes)
        .force('link', d3.forceLink(graphLinks).id(d => d.id).distance(100).strength(0.45))
        .force('charge', d3.forceManyBody().strength(-320))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collide', d3.forceCollide().radius(d => (d.mention_count > 0 ? Math.min(18, 11 + Math.sqrt(d.mention_count)) : 11) + 10));

    node.call(
        d3.drag()
            .on('start', (event) => {
                if (!event.active) kbGraphSimulation.alphaTarget(0.3).restart();
                event.sourceEvent && event.sourceEvent.stopPropagation();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
            })
            .on('drag', (event) => {
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            })
            .on('end', (event) => {
                if (!event.active) kbGraphSimulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
            })
    );

    kbGraphSimulation.on('tick', () => {
        link
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);

        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    // 默认展示第一个节点信息
    if (graphNodes.length > 0) {
        renderKBEntityInspector(graphNodes[0], graphLinks);
    }
}

function renderKBEntityInspector(node, links) {
    const inspector = document.getElementById('kbEntityInspector');
    if (!inspector || !node) return;

    const related = (Array.isArray(links) ? links : []).filter((link) => {
        const source = typeof link.source === 'object' ? link.source.id : link.source;
        const target = typeof link.target === 'object' ? link.target.id : link.target;
        return source === node.id || target === node.id;
    });

    const relationsHtml = related.length > 0
        ? related.slice(0, 12).map((link) => {
            const source = typeof link.source === 'object' ? link.source.name : link.source;
            const target = typeof link.target === 'object' ? link.target.name : link.target;
            return `<div class="kb-relation-item">${escapeHtml(String(source))} <strong>${escapeHtml(String(link.relation || '关联'))}</strong> ${escapeHtml(String(target))}</div>`;
        }).join('')
        : '<div class="text-gray-500 text-xs">暂无关联关系</div>';

    inspector.innerHTML = `
        <div class="kb-entity-card">
            <div>
                <span class="kb-entity-title">${escapeHtml(node.name)}</span>
                <span class="kb-entity-type">${escapeHtml(node.type)}</span>
            </div>
            <div class="kb-entity-row"><span class="kb-entity-k">实体ID</span><span class="kb-entity-v">${escapeHtml(node.id.slice(0, 20))}${node.id.length > 20 ? '...' : ''}</span></div>
            <div class="kb-entity-row"><span class="kb-entity-k">提及次数</span><span class="kb-entity-v">${node.mention_count || 0}</span></div>
            <div class="kb-entity-row"><span class="kb-entity-k">关联边数量</span><span class="kb-entity-v">${related.length}</span></div>
            <div class="mt-2 text-xs text-gray-500">关联关系</div>
            ${relationsHtml}
        </div>
    `;
}

function renderStatChip(value, label) {
    return `
        <div class="kb-stat-chip">
            <span class="kb-stat-value">${value}</span>
            <span class="kb-stat-label">${label}</span>
        </div>
    `;
}

function formatDateTime(dateString) {
    if (!dateString) return '未知';
    try {
        return new Date(dateString).toLocaleString('zh-CN');
    } catch (e) {
        return '未知';
    }
}

function getTypeColor(type) {
    const colorMap = {
        Person: '#2563eb',
        Organization: '#0f766e',
        Location: '#dc2626',
        Product: '#d97706',
        Concept: '#7c3aed',
        Event: '#db2777',
        Unknown: '#64748b'
    };
    return colorMap[type] || '#64748b';
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
 * 显示通知（使用统一的Toast提示）
 */
function showNotification(message, type = 'info') {
    showToast(message, type);
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
 * 在详情弹窗中删除文件
 */
async function deleteKBFile(kbId, fileId, filename) {
    if (!confirm(`确定要删除文件 "${filename}" 吗？\n\n删除后将无法恢复，相关的文本块和向量数据也会被删除。`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}/files/${fileId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '删除失败');
        }

        const result = await response.json();
        showNotification(result.message || '文件删除成功', 'success');

        await Promise.all([
            loadKBFilesPanel(kbId),
            loadKnowledgeBases()
        ]);

        kbChunksLoaded = false;
        if (activeKBId === kbId && activeKBTab === 'chunks') {
            await loadKBChunksPanel(kbId);
        }
        if (activeKBId === kbId) {
            await loadKBGraphPreview(kbId, true);
        }

        if (activeKBId === kbId) {
            const detailResp = await fetch(`${API_BASE_URL}/knowledge-bases/${kbId}`);
            if (detailResp.ok) {
                const kb = await detailResp.json();
                const stats = kb.graph_stats || {};
                const statsEl = document.getElementById('kbDetailStats');
                if (statsEl) {
                    statsEl.innerHTML = `
                        ${renderStatChip(stats.node_count || 0, '实体节点')}
                        ${renderStatChip(stats.edge_count || 0, '关系边')}
                        ${renderStatChip(kb.file_count || 0, '文件数')}
                        ${renderStatChip(kb.chunk_count || 0, '文本块')}
                    `;
                }
            }
        }
    } catch (error) {
        console.error('删除文件失败:', error);
        showNotification('删除文件失败: ' + (error.message || '未知错误'), 'error');
    }
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
        const previewPanel = document.getElementById('kbFilePreviewPanel');
        const titleEl = document.getElementById('kbFilePreviewTitle');
        const infoEl = document.getElementById('kbFilePreviewInfo');
        const bodyEl = document.getElementById('kbFilePreviewBody');

        if (!previewPanel || !titleEl || !infoEl || !bodyEl) {
            showNotification('文件预览容器不存在', 'error');
            return;
        }

        titleEl.textContent = filename || '文件原文';
        infoEl.textContent = '加载中...';
        bodyEl.innerHTML = '<div class="flex items-center justify-center py-8 text-primary"><i class="fa fa-spinner fa-spin mr-2"></i>原文加载中</div>';
        previewPanel.classList.remove('hidden');
        
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

        previewPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
    } catch (error) {
        console.error('加载文件内容失败:', error);
        const previewPanel = document.getElementById('kbFilePreviewPanel');
        const bodyEl = document.getElementById('kbFilePreviewBody');
        const infoEl = document.getElementById('kbFilePreviewInfo');
        if (previewPanel) previewPanel.classList.remove('hidden');
        if (infoEl) infoEl.textContent = '加载失败';
        if (bodyEl) {
            bodyEl.innerHTML = `<div class="text-center text-red-500 py-8"><i class="fa fa-exclamation-triangle mr-2"></i>加载失败: ${escapeHtml(error.message || '未知错误')}</div>`;
        }
    }
}

/**
 * 关闭文件内嵌预览
 */
function closeKBFilePreview() {
    const previewPanel = document.getElementById('kbFilePreviewPanel');
    const titleEl = document.getElementById('kbFilePreviewTitle');
    const infoEl = document.getElementById('kbFilePreviewInfo');
    const bodyEl = document.getElementById('kbFilePreviewBody');

    if (previewPanel) previewPanel.classList.add('hidden');
    if (titleEl) titleEl.textContent = '文件原文';
    if (infoEl) infoEl.textContent = '';
    if (bodyEl) bodyEl.innerHTML = '';
}

