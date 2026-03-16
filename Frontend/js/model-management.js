/**
 * 模型管理页面逻辑
 */

const API_BASE_URL = '';

// 页面状态
let currentTab = 'embedding'; // embedding, llm, lora
let embeddingModels = [];
let llmModels = { local: [], remote: [] };
let loraModels = [];
let wsClient = null;
let pendingDownloads = { embedding: [], llm: [] };

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    initWebSocket();
    setupEventListeners();
    await loadAllModels();
});

function initWebSocket() {
    if (typeof WebSocketClient === 'undefined') {
        console.warn('WebSocketClient 未加载，模型下载进度将不可用');
        return;
    }

    wsClient = new WebSocketClient();
    wsClient.on('model_download', handleModelDownloadEvent);
    wsClient.connect();
}

async function handleModelDownloadEvent(data) {
    const modelType = data.model_type === 'llm' ? 'llm' : 'embedding';
    const taskId = data.task_id;
    const task = pendingDownloads[modelType].find(item => item.taskId === taskId);

    if (!task) {
        return;
    }

    const progress = Number.isFinite(Number(data.progress)) ? Math.max(0, Math.min(100, Number(data.progress))) : 0;

    if (data.event === 'started' || data.event === 'progress') {
        updatePendingDownload(modelType, taskId, {
            status: data.message || '正在下载',
            pendingProgress: progress,
            size: '下载中'
        });
        return;
    }

    if (data.event === 'complete') {
        updatePendingDownload(modelType, taskId, {
            status: '下载完成',
            pendingProgress: 100,
            size: '已完成'
        });

        showMessage(data.message || `模型 ${task.source_name || task.name} 下载完成`, 'success');

        setTimeout(async () => {
            removePendingDownload(modelType, taskId);
            if (modelType === 'embedding') {
                await loadEmbeddingModels();
            } else {
                await loadLLMModels();
            }
        }, 350);
        return;
    }

    if (data.event === 'error') {
        updatePendingDownload(modelType, taskId, {
            status: '下载失败',
            pendingProgress: 0,
            size: '失败'
        });

        showMessage(data.error || data.message || '模型下载失败', 'error');

        setTimeout(() => {
            removePendingDownload(modelType, taskId);
        }, 5000);
    }
}

function setupEventListeners() {
    // 移动端菜单切换
    document.getElementById('mobile-menu-btn')?.addEventListener('click', function() {
        document.getElementById('mobile-menu')?.classList.toggle('hidden');
    });
    
    // 模型类型选项卡切换
    document.querySelectorAll('.model-tab-btn').forEach(button => {
        button.addEventListener('click', function() {
            switchTab(this.getAttribute('data-tab'));
        });
    });

    // 添加模型
    document.getElementById('add-model-btn')?.addEventListener('click', function() {
        if (currentTab === 'lora') {
            // LoRA 标签页点击"训练模型"按钮，跳转到训练页面
            window.location.href = 'lora-training.html';
        } else {
            showAddModelModal();
        }
    });
    
    // 搜索功能
    setupSearchListeners();
}

function setupSearchListeners() {
    // 嵌入模型搜索
    const embeddingSearch = document.querySelector('#embedding-models-tab input[type="text"]');
    if (embeddingSearch) {
        embeddingSearch.addEventListener('input', debounce((e) => {
            filterModels('embedding', e.target.value);
        }, 300));
    }
    
    // LLM模型搜索
    const llmSearch = document.querySelector('#llm-models-tab input[type="text"]');
    if (llmSearch) {
        llmSearch.addEventListener('input', debounce((e) => {
            filterModels('llm', e.target.value);
        }, 300));
    }
    
    // LoRA模型搜索
    const loraSearch = document.querySelector('#lora-models-tab input[type="text"]');
    if (loraSearch) {
        loraSearch.addEventListener('input', debounce((e) => {
            filterModels('lora', e.target.value);
        }, 300));
    }
}

// ==================== 标签页切换 ====================

function switchTab(tabName) {
    currentTab = tabName.replace('-models', '');
    
    // 更新按钮样式
    document.querySelectorAll('.model-tab-btn').forEach(btn => {
        btn.classList.remove('border-primary', 'text-primary');
        btn.classList.add('border-transparent', 'text-gray-500');
    });
    
    const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
    if (activeBtn) {
        activeBtn.classList.remove('border-transparent', 'text-gray-500');
        activeBtn.classList.add('border-primary', 'text-primary');
    }
    
    // 切换内容
    document.querySelectorAll('.model-tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(tabName + '-tab')?.classList.remove('hidden');
    
    // 更新"添加模型"按钮文本
    const addBtn = document.getElementById('add-model-btn');
    if (addBtn) {
        if (currentTab === 'lora') {
            addBtn.innerHTML = '<i class="fa fa-plus mr-2"></i> 训练模型';
        } else {
            addBtn.innerHTML = '<i class="fa fa-plus mr-2"></i> 添加模型';
        }
    }
}

// ==================== 数据加载 ====================

async function loadAllModels() {
    showLoading(true);
    try {
        await Promise.all([
            loadEmbeddingModels(),
            loadLLMModels(),
            loadLoRAModels()
        ]);
    } catch (error) {
        showMessage('加载模型失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function loadEmbeddingModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/embedding`);
        if (!response.ok) throw new Error('加载嵌入模型失败');
        
        const data = await response.json();
        embeddingModels = data.models || [];
        renderEmbeddingModels(getEmbeddingDisplayModels());
    } catch (error) {
        console.error('加载嵌入模型失败:', error);
        throw error;
    }
}

async function loadLLMModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/llm`);
        if (!response.ok) throw new Error('加载LLM模型失败');
        
        const data = await response.json();
        llmModels = {
            local: data.local || [],
            remote: data.remote || []
        };
        renderLLMModels({
            local: getLLMDisplayModels(),
            remote: llmModels.remote || []
        });
    } catch (error) {
        console.error('加载LLM模型失败:', error);
        throw error;
    }
}

async function loadLoRAModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models`);
        if (!response.ok) throw new Error('加载LoRA模型失败');
        
        const data = await response.json();
        loraModels = data.models || [];
        renderLoRAModels(loraModels);
    } catch (error) {
        console.error('加载LoRA模型失败:', error);
        // 不抛出错误，允许其他模型继续加载
    }
}

// ==================== 渲染函数 ====================

/**
 * 渲染下载中任务的状态单元格
 * 阶段: 准备中(0%) → 下载中(>0%) → 下载完成(100%) → 下载失败
 */
function renderPendingStatusCell(model) {
    const p = model.pendingProgress || 0;
    const status = model.status || '';

    if (status === '下载失败') {
        return `<span class="px-2 py-1 bg-red-50 text-red-600 text-xs rounded-full">下载失败</span>`;
    }
    if (p >= 100 || status === '下载完成') {
        return `
            <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">下载完成</span>
            <div class="w-40 mt-2 bg-gray-200 rounded-full h-2 overflow-hidden">
                <div class="bg-success h-2 rounded-full transition-all duration-500" style="width:100%"></div>
            </div>`;
    }
    if (p > 0) {
        const pInt = Math.round(p);
        return `
            <span class="px-2 py-1 bg-yellow-50 text-yellow-700 text-xs rounded-full">下载中 ${pInt}%</span>
            <div class="w-40 mt-2 bg-gray-200 rounded-full h-2 overflow-hidden">
                <div class="bg-warning h-2 rounded-full transition-all duration-500" style="width:${pInt}%"></div>
            </div>`;
    }
    // progress=0：任务已建立但尚未收到进度推送
    return `
        <span class="px-2 py-1 bg-gray-100 text-gray-500 text-xs rounded-full">准备中...</span>
        <div class="w-40 mt-2 bg-gray-200 rounded-full h-2 overflow-hidden">
            <div class="bg-gray-400 h-2 rounded-full transition-all duration-500" style="width:5%"></div>
        </div>`;
}

function getEmbeddingDisplayModels() {
    return [...pendingDownloads.embedding, ...embeddingModels];
}

function getLLMDisplayModels() {
    return [...pendingDownloads.llm, ...(llmModels.local || [])];
}

function renderModelListByType(modelType) {
    if (modelType === 'embedding') {
        renderEmbeddingModels(getEmbeddingDisplayModels());
    } else if (modelType === 'llm') {
        renderLLMModels({
            local: getLLMDisplayModels(),
            remote: llmModels.remote || []
        });
    }
}

function startPendingDownload(modelType, modelName) {
    const taskId = `pending_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const displayName = modelName.includes('/') ? modelName.split('/').pop() : modelName;

    pendingDownloads[modelType].unshift({
        taskId,
        name: displayName,
        source_name: modelName,
        type: modelType === 'embedding' ? 'Embedding' : 'LLM',
        status: '等待下载',
        size: '下载中',
        created_at: new Date().toISOString(),
        pendingProgress: 0,
        isPending: true,
        parameters: modelType === 'llm' ? '下载中' : undefined,
        dimension: modelType === 'embedding' ? '-' : undefined
    });

    renderModelListByType(modelType);
    return taskId;
}

function replacePendingTaskId(modelType, oldTaskId, newTaskId) {
    const task = pendingDownloads[modelType].find(item => item.taskId === oldTaskId);
    if (!task) return;

    task.taskId = newTaskId;
    renderModelListByType(modelType);
}

function updatePendingDownload(modelType, taskId, updates) {
    const task = pendingDownloads[modelType].find(item => item.taskId === taskId);
    if (!task) return;
    Object.assign(task, updates);
    renderModelListByType(modelType);
}

function removePendingDownload(modelType, taskId) {
    pendingDownloads[modelType] = pendingDownloads[modelType].filter(item => item.taskId !== taskId);
    renderModelListByType(modelType);
}

function renderEmbeddingModels(models) {
    const tbody = document.querySelector('#embedding-models-tab tbody');
    if (!tbody) return;
    
    if (models.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                    <i class="fa fa-inbox text-4xl mb-2"></i>
                    <p>暂无嵌入模型</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = models.map(model => `
        <tr class="model-row" data-model-name="${escapeHtml(model.name)}">
            <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                    <div class="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center mr-4">
                        <i class="fa fa-microchip text-purple-500"></i>
                    </div>
                    <div>
                        <div class="font-medium text-gray-900">${escapeHtml(model.name)}</div>
                        <div class="text-sm text-gray-500">${escapeHtml(model.type)}</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">${escapeHtml(model.type)}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                ${model.isPending ? renderPendingStatusCell(model) : `
                    <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(model.status)}</span>
                `}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${model.dimension || 'N/A'}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHtml(model.size)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDateTime(model.created_at)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                ${model.isPending ? `
                    <span class="text-gray-400">下载中...</span>
                ` : `
                    <div class="flex space-x-2">
                        <button onclick="showModelDetail('${escapeHtml(model.name)}', 'embedding')" class="text-primary hover:text-primary/80">查看</button>
                        <button onclick="deleteModel('${escapeHtml(model.name)}', 'embedding')" class="text-danger hover:text-danger/80">删除</button>
                    </div>
                `}
            </td>
        </tr>
    `).join('');
    
    updatePagination('embedding', models.length);
}

function renderLLMModels(models) {
    const tbody = document.querySelector('#llm-models-tab tbody');
    if (!tbody) return;
    
    const allModels = models.local || [];
    
    if (allModels.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                    <i class="fa fa-inbox text-4xl mb-2"></i>
                    <p>暂无LLM模型</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = allModels.map(model => {
        return `
        <tr class="model-row" data-model-name="${escapeHtml(model.name)}">
            <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                    <div class="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center mr-4">
                        <i class="fa fa-brain text-green-500"></i>
                    </div>
                    <div>
                        <div class="font-medium text-gray-900">${escapeHtml(model.name)}</div>
                        <div class="text-sm text-gray-500">${model.isPending ? 'HuggingFace 下载任务' : '本地模型'}</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">
                    ${escapeHtml(model.type || 'Unknown')}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                ${model.isPending ? renderPendingStatusCell(model) : `
                    <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(model.status)}</span>
                `}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${model.parameters || 'N/A'}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHtml(model.size)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDateTime(model.created_at)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                ${model.isPending ? `
                    <span class="text-gray-400">下载中...</span>
                ` : `
                    <div class="flex space-x-2">
                        <button onclick="showModelDetail('${escapeHtml(model.name)}', 'llm')" class="text-primary hover:text-primary/80">查看</button>
                        <button onclick="deleteModel('${escapeHtml(model.name)}', 'llm')" class="text-danger hover:text-danger/80">删除</button>
                    </div>
                `}
            </td>
        </tr>
        `;
    }).join('');
    
    updatePagination('llm', allModels.length);
}

function renderLoRAModels(models) {
    const container = document.getElementById('lora-models-list');
    if (!container) return;
    
    if (models.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12">
                <div class="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
                    <i class="fa fa-cube text-gray-400 text-3xl"></i>
                </div>
                <h3 class="text-lg font-medium text-gray-900 mb-2">暂无 LoRA 模型</h3>
                <p class="text-gray-500 mb-4">开始训练您的第一个 LoRA 模型</p>
                <button onclick="window.location.href='lora-training.html'" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">
                    <i class="fa fa-plus mr-2"></i>训练模型
                </button>
            </div>
        `;
        return;
    }
    
    container.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            ${models.map(model => `
                <div class="border border-gray-200 rounded-lg p-5 hover:border-primary hover:shadow-md transition-custom">
                    <div class="flex items-start justify-between mb-3">
                        <div class="flex items-center">
                            <div class="w-12 h-12 rounded-lg bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center mr-3">
                                <i class="fa fa-cube text-white text-xl"></i>
                            </div>
                            <div>
                                <h3 class="font-bold text-gray-900">${escapeHtml(model.name)}</h3>
                                <p class="text-xs text-gray-500">${formatDateTime(model.created_at)}</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="space-y-2 mb-4">
                        <div class="flex items-center text-sm">
                            <i class="fa fa-brain text-gray-400 w-5"></i>
                            <span class="text-gray-600">基座: ${escapeHtml(model.base_model)}</span>
                        </div>
                        <div class="flex items-center text-sm">
                            <i class="fa fa-hdd-o text-gray-400 w-5"></i>
                            <span class="text-gray-600">大小: ${formatFileSize(model.file_size)}</span>
                        </div>
                        <div class="flex items-center text-sm">
                            <i class="fa fa-sliders text-gray-400 w-5"></i>
                            <span class="text-gray-600">Rank: ${model.lora_rank || 'N/A'}</span>
                        </div>
                    </div>
                    
                    ${model.description ? `
                        <p class="text-sm text-gray-600 mb-4 line-clamp-2">${escapeHtml(model.description)}</p>
                    ` : ''}
                    
                    <div class="flex space-x-2 pt-3 border-t border-gray-100">
                        <button onclick="viewLoRAModel(${model.id})" class="flex-1 px-3 py-2 text-sm text-primary border border-primary rounded-lg hover:bg-primary/5 transition-custom">
                            <i class="fa fa-eye mr-1"></i>查看
                        </button>
                        <button onclick="deleteLoRAModel(${model.id}, '${escapeHtml(model.name)}')" class="flex-1 px-3 py-2 text-sm text-danger border border-danger rounded-lg hover:bg-danger/5 transition-custom">
                            <i class="fa fa-trash-o mr-1"></i>删除
                        </button>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function updatePagination(type, total) {
    const paginationText = document.querySelector(`#${type}-models-tab .pagination-text`);
    if (paginationText) {
        paginationText.textContent = `显示 1 到 ${total} 项，共 ${total} 项`;
    }
}

// ==================== 搜索过滤 ====================

function filterModels(type, query) {
    const searchQuery = query.toLowerCase().trim();
    let filteredModels = [];
    
    if (type === 'embedding') {
        filteredModels = getEmbeddingDisplayModels().filter(m => 
            m.name.toLowerCase().includes(searchQuery) ||
            (m.type && m.type.toLowerCase().includes(searchQuery))
        );
        renderEmbeddingModels(filteredModels);
    } else if (type === 'llm') {
        const filteredLocal = getLLMDisplayModels().filter(m =>
            m.name.toLowerCase().includes(searchQuery) ||
            (m.type && m.type.toLowerCase().includes(searchQuery))
        );
        renderLLMModels({ local: filteredLocal, remote: [] });
    } else if (type === 'lora') {
        filteredModels = loraModels.filter(m =>
            m.name.toLowerCase().includes(searchQuery) ||
            m.base_model.toLowerCase().includes(searchQuery)
        );
        renderLoRAModels(filteredModels);
    }
}

// ==================== 模型详情 ====================

async function showModelDetail(modelName, modelType) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/${modelType}/${encodeURIComponent(modelName)}`);
        if (!response.ok) throw new Error('获取模型详情失败');
        
        const data = await response.json();
        const model = data.model;
        
        // 构建详情HTML
        let detailHTML = `
            <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onclick="closeModelDetail(event)">
                <div class="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
                    <div class="p-6 border-b border-gray-200 flex justify-between items-center">
                        <h3 class="text-xl font-bold">${escapeHtml(model.name)}</h3>
                        <button onclick="closeModelDetail()" class="text-gray-400 hover:text-gray-600">
                            <i class="fa fa-times text-xl"></i>
                        </button>
                    </div>
                    <div class="p-6">
                        <div class="space-y-4">
                            <div>
                                <label class="text-sm font-medium text-gray-500">模型类型</label>
                                <p class="mt-1">${escapeHtml(model.type || 'Unknown')}</p>
                            </div>
                            ${modelType === 'embedding' ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">向量维度</label>
                                <p class="mt-1">${model.dimension || 'N/A'}</p>
                            </div>
                            ` : ''}
                            ${modelType === 'llm' && model.parameters ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">参数规模</label>
                                <p class="mt-1">${escapeHtml(model.parameters)}</p>
                            </div>
                            ` : ''}
                            ${model.size ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">模型大小</label>
                                <p class="mt-1">${escapeHtml(model.size)}</p>
                            </div>
                            ` : ''}
                            ${model.architecture ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">架构</label>
                                <p class="mt-1">${escapeHtml(model.architecture)}</p>
                            </div>
                            ` : ''}
                            ${model.path ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">文件路径</label>
                                <p class="mt-1 text-sm break-all text-gray-600">${escapeHtml(model.path)}</p>
                            </div>
                            ` : ''}
                            ${model.usage ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">使用情况</label>
                                <div class="mt-2 space-y-2">
                                    ${model.usage.knowledge_bases && model.usage.knowledge_bases.length > 0 ? `
                                        <div>
                                            <p class="text-sm text-gray-600">被 ${model.usage.knowledge_bases.length} 个知识库使用：</p>
                                            <div class="flex flex-wrap gap-2 mt-1">
                                                ${model.usage.knowledge_bases.map(kb => `
                                                    <span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">${escapeHtml(kb.name)}</span>
                                                `).join('')}
                                            </div>
                                        </div>
                                    ` : ''}
                                    ${model.usage.assistants && model.usage.assistants.length > 0 ? `
                                        <div>
                                            <p class="text-sm text-gray-600">被 ${model.usage.assistants.length} 个助手使用：</p>
                                            <div class="flex flex-wrap gap-2 mt-1">
                                                ${model.usage.assistants.map(a => `
                                                    <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(a.name)}</span>
                                                `).join('')}
                                            </div>
                                        </div>
                                    ` : ''}
                                    ${!model.usage.is_used ? `
                                        <p class="text-sm text-gray-500">当前未被使用</p>
                                    ` : ''}
                                </div>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                    <div class="p-6 border-t border-gray-200 flex justify-end space-x-2">
                        <button onclick="closeModelDetail()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-custom">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', detailHTML);
    } catch (error) {
        showMessage('获取模型详情失败: ' + error.message, 'error');
    }
}

function closeModelDetail(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.querySelector('.fixed.inset-0');
    if (modal) modal.remove();
}

// ==================== 删除模型 ====================

async function deleteModel(modelName, modelType) {
    if (!confirm(`确定要删除模型 "${modelName}" 吗？\n\n此操作将删除模型文件，不可恢复！`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/${modelType}/${encodeURIComponent(modelName)}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showMessage(result.message, 'success');
            // 重新加载模型列表
            if (modelType === 'embedding') {
                await loadEmbeddingModels();
            } else if (modelType === 'llm') {
                await loadLLMModels();
            }
        } else {
            // 显示使用情况警告
            if (result.usage) {
                let warningMsg = `${result.message}\n\n`;
                if (result.usage.knowledge_bases && result.usage.knowledge_bases.length > 0) {
                    warningMsg += `知识库：${result.usage.knowledge_bases.map(kb => kb.name).join(', ')}\n`;
                }
                if (result.usage.assistants && result.usage.assistants.length > 0) {
                    warningMsg += `助手：${result.usage.assistants.map(a => a.name).join(', ')}`;
                }
                
                if (confirm(warningMsg + '\n\n是否强制删除？（将影响相关功能）')) {
                    // 强制删除
                    const forceResponse = await fetch(`${API_BASE_URL}/api/models/${modelType}/${encodeURIComponent(modelName)}?force=true`, {
                        method: 'DELETE'
                    });
                    const forceResult = await forceResponse.json();
                    
                    if (forceResult.success) {
                        showMessage('模型已强制删除', 'success');
                        // 重新加载
                        if (modelType === 'embedding') {
                            await loadEmbeddingModels();
                        } else if (modelType === 'llm') {
                            await loadLLMModels();
                        }
                    } else {
                        showMessage('强制删除失败: ' + forceResult.message, 'error');
                    }
                }
            } else {
                showMessage(result.message, 'error');
            }
        }
    } catch (error) {
        showMessage('删除模型失败: ' + error.message, 'error');
    }
}

// ==================== 导入指引 ====================

function showImportGuide(modelType) {
    let guideHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onclick="closeImportGuide(event)">
            <div class="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
                <div class="p-6 border-b border-gray-200 flex justify-between items-center">
                    <h3 class="text-xl font-bold">模型导入指南</h3>
                    <button onclick="closeImportGuide()" class="text-gray-400 hover:text-gray-600">
                        <i class="fa fa-times text-xl"></i>
                    </button>
                </div>
                <div class="p-6">
                    <div class="space-y-4">
                        <div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
                            <p class="text-sm text-blue-800">
                                <i class="fa fa-info-circle mr-2"></i>
                                请将模型文件放入对应的目录，系统会自动扫描并识别。
                            </p>
                        </div>
                        
                        <div>
                            <h4 class="font-medium mb-2">📁 模型目录位置：</h4>
                            <div class="bg-gray-50 p-3 rounded border border-gray-200 font-mono text-sm">
                                ${modelType === 'embedding' ? 'Models/Embedding/' : 'Models/LLM/'}
                            </div>
                        </div>
                        
                        <div>
                            <h4 class="font-medium mb-2">📝 导入步骤：</h4>
                            <ol class="list-decimal list-inside space-y-2 text-sm text-gray-600">
                                <li>下载 HuggingFace 模型到本地</li>
                                <li>将整个模型文件夹复制到上述目录</li>
                                <li>确保文件夹包含 config.json 等必要文件</li>
                                <li>点击下方"重新扫描"按钮刷新列表</li>
                            </ol>
                        </div>
                        
                        <div>
                            <h4 class="font-medium mb-2">⚠️ 注意事项：</h4>
                            <ul class="list-disc list-inside space-y-1 text-sm text-gray-600">
                                <li>模型文件夹名称将作为模型名称显示</li>
                                <li>请勿修改 config.json 文件</li>
                                <li>确保有足够的磁盘空间</li>
                            </ul>
                        </div>
                    </div>
                </div>
                <div class="p-6 border-t border-gray-200 flex justify-end space-x-2">
                    <button onclick="closeImportGuide()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-custom">关闭</button>
                    <button onclick="rescanModels('${modelType}')" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">
                        <i class="fa fa-refresh mr-2"></i>重新扫描
                    </button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', guideHTML);
}

function closeImportGuide(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.querySelector('.fixed.inset-0');
    if (modal) modal.remove();
}

function showAddModelModal() {
    const defaultType = currentTab === 'llm' ? 'llm' : 'embedding';
    const modalHTML = `
        <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onclick="closeAddModelModal(event)">
            <div class="bg-white rounded-xl max-w-lg w-full mx-4" onclick="event.stopPropagation()">
                <div class="p-6 border-b border-gray-200 flex justify-between items-center">
                    <h3 class="text-xl font-bold">添加模型</h3>
                    <button onclick="closeAddModelModal()" class="text-gray-400 hover:text-gray-600">
                        <i class="fa fa-times text-xl"></i>
                    </button>
                </div>
                <div class="p-6 space-y-4">
                    <div class="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800">
                        输入 HuggingFace 模型名称（例如：sentence-transformers/all-MiniLM-L6-v2 或 Qwen/Qwen2.5-3B-Instruct）。
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">模型类型</label>
                        <select id="add-model-type" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary">
                            <option value="embedding" ${defaultType === 'embedding' ? 'selected' : ''}>Embedding</option>
                            <option value="llm" ${defaultType === 'llm' ? 'selected' : ''}>LLM</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">HuggingFace 模型名称</label>
                        <input id="add-model-name" type="text" placeholder="org/model_name" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary">
                    </div>
                    <p class="text-xs text-gray-500">下载失败时可能是网络不稳定，或该模型需要先在 HuggingFace 申请访问权限。</p>
                </div>
                <div class="p-6 border-t border-gray-200 flex justify-end space-x-2">
                    <button onclick="closeAddModelModal()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-custom">取消</button>
                    <button onclick="submitAddModel()" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">开始添加</button>
                </div>
            </div>
        </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

function closeAddModelModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.querySelector('.fixed.inset-0');
    if (modal) modal.remove();
}

async function submitAddModel() {
    const typeEl = document.getElementById('add-model-type');
    const nameEl = document.getElementById('add-model-name');

    const modelType = typeEl?.value;
    const modelName = nameEl?.value?.trim();

    if (!modelName) {
        showMessage('请输入 HuggingFace 模型名称（格式：org/model_name）', 'warning');
        return;
    }

    closeAddModelModal();
    const normalizedType = modelType === 'llm' ? 'llm' : 'embedding';
    switchTab(normalizedType === 'embedding' ? 'embedding-models' : 'llm-models');

    if (!wsClient) {
        initWebSocket();
    }

    const localTaskId = startPendingDownload(normalizedType, modelName);

    try {
        const response = await fetch(`${API_BASE_URL}/api/models/download`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                model_name: modelName,
                model_type: normalizedType,
                client_id: wsClient?.clientId || null
            })
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || result.message || '添加失败');
        }

        const serverTaskId = result.task_id;
        if (serverTaskId) {
            replacePendingTaskId(normalizedType, localTaskId, serverTaskId);
            updatePendingDownload(normalizedType, serverTaskId, {
                status: '任务已创建，等待下载进度...'
            });
        } else {
            updatePendingDownload(normalizedType, localTaskId, {
                status: '任务已创建，等待下载进度...'
            });
        }

        showMessage(`模型 ${modelName} 下载任务已创建，正在后台下载...`, 'success');
    } catch (error) {
        updatePendingDownload(normalizedType, localTaskId, {
            status: '下载失败',
            pendingProgress: 0,
            size: '失败'
        });

        setTimeout(() => {
            removePendingDownload(normalizedType, localTaskId);
        }, 5000);

        showMessage(error.message || '添加模型失败', 'error');
    }
}

window.showAddModelModal = showAddModelModal;
window.closeAddModelModal = closeAddModelModal;
window.submitAddModel = submitAddModel;

async function rescanModels(modelType) {
    closeImportGuide();
    showLoading(true);
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/${modelType}/scan`, {
            method: 'POST'
        });
        
        if (!response.ok) throw new Error('扫描失败');
        
        const result = await response.json();
        showMessage(`扫描完成，发现 ${result.total} 个模型`, 'success');
        
        // 重新加载
        if (modelType === 'embedding') {
            await loadEmbeddingModels();
        } else if (modelType === 'llm') {
            await loadLLMModels();
        }
    } catch (error) {
        showMessage('扫描失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// ==================== 工具函数 ====================

function showLoading(show) {
    // 简单的加载状态（可以扩展）
    const loadingEl = document.getElementById('loading-indicator');
    if (loadingEl) {
        loadingEl.style.display = show ? 'block' : 'none';
    }
}

// 使用统一的Toast提示（定义在common.js中）
function showMessage(message, type = 'info') {
    showToast(message, type);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return 'N/A';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
}

// ==================== LoRA 模型操作 ====================

async function viewLoRAModel(modelId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models/${modelId}`);
        if (!response.ok) throw new Error('获取LoRA模型详情失败');
        
        const data = await response.json();
        const model = data.model;
        
        const detailHTML = `
            <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onclick="closeLoRADetail(event)">
                <div class="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
                    <div class="p-6 border-b border-gray-200 flex justify-between items-center">
                        <h3 class="text-xl font-bold">${escapeHtml(model.name)}</h3>
                        <button onclick="closeLoRADetail()" class="text-gray-400 hover:text-gray-600">
                            <i class="fa fa-times text-xl"></i>
                        </button>
                    </div>
                    <div class="p-6">
                        <div class="space-y-4">
                            <div>
                                <label class="text-sm font-medium text-gray-500">基座模型</label>
                                <p class="mt-1">${escapeHtml(model.base_model)}</p>
                            </div>
                            ${model.description ? `
                            <div>
                                <label class="text-sm font-medium text-gray-500">描述</label>
                                <p class="mt-1">${escapeHtml(model.description)}</p>
                            </div>
                            ` : ''}
                            <div>
                                <label class="text-sm font-medium text-gray-500">LoRA 配置</label>
                                <div class="mt-2 grid grid-cols-2 gap-3">
                                    <div class="bg-gray-50 p-3 rounded">
                                        <p class="text-xs text-gray-500">Rank</p>
                                        <p class="font-medium">${model.lora_rank || 'N/A'}</p>
                                    </div>
                                    <div class="bg-gray-50 p-3 rounded">
                                        <p class="text-xs text-gray-500">Alpha</p>
                                        <p class="font-medium">${model.lora_alpha || 'N/A'}</p>
                                    </div>
                                </div>
                            </div>
                            <div>
                                <label class="text-sm font-medium text-gray-500">文件信息</label>
                                <div class="mt-2 space-y-2">
                                    <div class="flex justify-between text-sm">
                                        <span class="text-gray-600">文件大小</span>
                                        <span class="font-medium">${formatFileSize(model.file_size)}</span>
                                    </div>
                                    <div class="flex justify-between text-sm">
                                        <span class="text-gray-600">创建时间</span>
                                        <span class="font-medium">${formatDateTime(model.created_at)}</span>
                                    </div>
                                    ${model.file_path ? `
                                    <div class="text-sm">
                                        <span class="text-gray-600">文件路径</span>
                                        <p class="mt-1 font-mono text-xs bg-gray-50 p-2 rounded break-all">${escapeHtml(model.file_path)}</p>
                                    </div>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="p-6 border-t border-gray-200 flex justify-end space-x-2">
                        <button onclick="closeLoRADetail()" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-custom">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', detailHTML);
    } catch (error) {
        showMessage('获取LoRA模型详情失败: ' + error.message, 'error');
    }
}

function closeLoRADetail(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.querySelector('.fixed.inset-0');
    if (modal) modal.remove();
}

async function deleteLoRAModel(modelId, modelName) {
    if (!confirm(`确定要删除 LoRA 模型 "${modelName}" 吗？\n\n此操作将删除模型文件，不可恢复！`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models/${modelId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '删除失败');
        }
        
        const result = await response.json();
        showMessage(result.message || 'LoRA 模型已删除', 'success');
        
        // 重新加载 LoRA 模型列表
        await loadLoRAModels();
    } catch (error) {
        showMessage('删除 LoRA 模型失败: ' + error.message, 'error');
    }
}

// 导出全局函数
window.viewLoRAModel = viewLoRAModel;
window.closeLoRADetail = closeLoRADetail;
window.deleteLoRAModel = deleteLoRAModel;

// formatDateTime 和 debounce 函数由 common.js 提供
