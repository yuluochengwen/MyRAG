/**
 * 模型管理页面逻辑
 */

const API_BASE_URL = 'http://localhost:8000';

// 页面状态
let currentTab = 'embedding'; // embedding, llm, lora
let embeddingModels = [];
let llmModels = { local: [], remote: [] };
let loraModels = [];

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    await loadAllModels();
});

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
        renderEmbeddingModels(embeddingModels);
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
        renderLLMModels(llmModels);
    } catch (error) {
        console.error('加载LLM模型失败:', error);
        throw error;
    }
}

async function loadLoRAModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/models/lora`);
        if (!response.ok) throw new Error('加载LoRA模型失败');
        
        const data = await response.json();
        loraModels = data.models || [];
        renderLoRAModels(loraModels);
    } catch (error) {
        console.error('加载LoRA模型失败:', error);
        throw error;
    }
}

// ==================== 渲染函数 ====================

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
                <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(model.status)}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${model.dimension || 'N/A'}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHtml(model.size)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDateTime(model.created_at)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <div class="flex space-x-2">
                    <button onclick="showModelDetail('${escapeHtml(model.name)}', 'embedding')" class="text-primary hover:text-primary/80">查看</button>
                    <button onclick="deleteModel('${escapeHtml(model.name)}', 'embedding')" class="text-danger hover:text-danger/80">删除</button>
                </div>
            </td>
        </tr>
    `).join('');
    
    updatePagination('embedding', models.length);
}

function renderLLMModels(models) {
    const tbody = document.querySelector('#llm-models-tab tbody');
    if (!tbody) return;
    
    const allModels = [...models.local, ...models.remote];
    
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
        const isRemote = model.provider !== 'local';
        const canDelete = !isRemote;
        
        return `
        <tr class="model-row" data-model-name="${escapeHtml(model.name)}">
            <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                    <div class="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center mr-4">
                        <i class="fa fa-brain text-green-500"></i>
                    </div>
                    <div>
                        <div class="font-medium text-gray-900">${escapeHtml(model.name)}</div>
                        <div class="text-sm text-gray-500">${isRemote ? '远程模型' : '本地模型'}</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 ${isRemote ? 'bg-orange-50 text-orange-600' : 'bg-blue-50 text-blue-600'} text-xs rounded-full">
                    ${escapeHtml(model.type || 'Unknown')}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(model.status)}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${model.parameters || 'N/A'}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${isRemote ? '-' : escapeHtml(model.size)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${isRemote ? '-' : formatDateTime(model.created_at)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <div class="flex space-x-2">
                    <button onclick="showModelDetail('${escapeHtml(model.name)}', 'llm')" class="text-primary hover:text-primary/80">查看</button>
                    ${canDelete ? `<button onclick="deleteModel('${escapeHtml(model.name)}', 'llm')" class="text-danger hover:text-danger/80">删除</button>` : ''}
                </div>
            </td>
        </tr>
        `;
    }).join('');
    
    updatePagination('llm', allModels.length);
}

function renderLoRAModels(models) {
    const tbody = document.querySelector('#lora-models-tab tbody');
    if (!tbody) return;
    
    if (models.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="px-6 py-12 text-center text-gray-500">
                    <div class="flex flex-col items-center">
                        <i class="fa fa-inbox text-4xl mb-4 text-gray-400"></i>
                        <p class="text-lg font-medium mb-2">暂无LoRA模型</p>
                        <p class="text-sm text-gray-400 mb-4">LoRA (Low-Rank Adaptation) 模型可以微调基础模型</p>
                        <button onclick="showImportGuide('lora')" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">
                            <i class="fa fa-info-circle mr-2"></i>了解如何导入
                        </button>
                    </div>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = models.map(model => `
        <tr class="model-row" data-model-name="${escapeHtml(model.name)}">
            <td class="px-6 py-4 whitespace-nowrap">
                <div class="flex items-center">
                    <div class="w-10 h-10 rounded-lg bg-yellow-100 flex items-center justify-center mr-4">
                        <i class="fa fa-cogs text-yellow-500"></i>
                    </div>
                    <div>
                        <div class="font-medium text-gray-900">${escapeHtml(model.name)}</div>
                        <div class="text-sm text-gray-500">LoRA Adapter</div>
                    </div>
                </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHtml(model.base_model)}</td>
            <td class="px-6 py-4 whitespace-nowrap">
                <span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(model.status)}</span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${model.rank}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${escapeHtml(model.size)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${formatDateTime(model.created_at)}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                <div class="flex space-x-2">
                    <button onclick="showModelDetail('${escapeHtml(model.name)}', 'lora')" class="text-primary hover:text-primary/80">查看</button>
                    <button onclick="deleteModel('${escapeHtml(model.name)}', 'lora')" class="text-danger hover:text-danger/80">删除</button>
                </div>
            </td>
        </tr>
    `).join('');
    
    updatePagination('lora', models.length);
}

function updatePagination(type, total) {
    const paginationText = document.querySelector(`#${type}-models-tab .text-sm.text-gray-500`);
    if (paginationText) {
        paginationText.textContent = `显示 1 到 ${total} 项，共 ${total} 项`;
    }
}

// ==================== 搜索过滤 ====================

function filterModels(type, query) {
    const searchQuery = query.toLowerCase().trim();
    let filteredModels = [];
    
    if (type === 'embedding') {
        filteredModels = embeddingModels.filter(m => 
            m.name.toLowerCase().includes(searchQuery) ||
            m.type.toLowerCase().includes(searchQuery)
        );
        renderEmbeddingModels(filteredModels);
    } else if (type === 'llm') {
        const filteredLocal = llmModels.local.filter(m =>
            m.name.toLowerCase().includes(searchQuery) ||
            (m.type && m.type.toLowerCase().includes(searchQuery))
        );
        const filteredRemote = llmModels.remote.filter(m =>
            m.name.toLowerCase().includes(searchQuery) ||
            (m.type && m.type.toLowerCase().includes(searchQuery))
        );
        renderLLMModels({ local: filteredLocal, remote: filteredRemote });
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
            } else if (modelType === 'lora') {
                await loadLoRAModels();
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
                        } else if (modelType === 'lora') {
                            await loadLoRAModels();
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
                                ${modelType === 'embedding' ? 'Models/Embedding/' : modelType === 'llm' ? 'Models/LLM/' : 'Models/LoRA/'}
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
        } else if (modelType === 'lora') {
            await loadLoRAModels();
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

// formatDateTime 和 debounce 函数由 common.js 提供

// ==================== LoRA 训练服务管理 ====================

let serviceCheckInterval = null;

// 启动训练服务
async function startTrainingService() {
    const btn = document.getElementById('startTrainingBtn');
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i> 启动中...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/service/start`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showMessage('训练平台启动成功！正在等待服务就绪...', 'success');
            updateServiceStatus();
            startServiceMonitoring();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('启动失败: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// 停止训练服务
async function stopTrainingService() {
    if (!confirm('确定要停止训练平台吗？这将关闭 LLaMA-Factory Web UI。')) return;
    
    const btn = document.getElementById('stopTrainingBtn');
    const originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/service/stop`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showMessage('训练平台已停止', 'success');
            updateServiceStatus();
            stopServiceMonitoring();
        } else {
            showMessage(data.message, 'error');
        }
    } catch (error) {
        showMessage('停止失败: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
}

// 打开训练界面
function openTrainingUI() {
    window.open('http://localhost:7860', '_blank');
    showMessage('已在新标签页打开训练界面', 'info');
}

// 更新服务状态
async function updateServiceStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/service/status`);
        const status = await response.json();
        
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        const startBtn = document.getElementById('startTrainingBtn');
        const openBtn = document.getElementById('openTrainingUIBtn');
        const stopBtn = document.getElementById('stopTrainingBtn');
        
        if (status.running) {
            // 服务运行中
            dot.className = 'w-3 h-3 rounded-full bg-green-500 animate-pulse';
            text.textContent = '运行中';
            text.className = 'text-sm text-green-600 font-medium';
            
            startBtn.classList.add('hidden');
            openBtn.classList.remove('hidden');
            stopBtn.classList.remove('hidden');
        } else {
            // 服务未运行
            dot.className = 'w-3 h-3 rounded-full bg-gray-400';
            text.textContent = '未运行';
            text.className = 'text-sm text-gray-600';
            
            startBtn.classList.remove('hidden');
            openBtn.classList.add('hidden');
            stopBtn.classList.add('hidden');
        }
    } catch (error) {
        console.error('获取服务状态失败:', error);
    }
}

// 开始监控服务
function startServiceMonitoring() {
    if (serviceCheckInterval) return;
    serviceCheckInterval = setInterval(updateServiceStatus, 5000); // 每5秒检查一次
}

// 停止监控服务
function stopServiceMonitoring() {
    if (serviceCheckInterval) {
        clearInterval(serviceCheckInterval);
        serviceCheckInterval = null;
    }
}

// ==================== LoRA 模型管理 ====================

// 扫描新模型
async function scanLoRAModels() {
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models/scan`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            if (data.count > 0) {
                showMessage(`发现 ${data.count} 个新模型`, 'success');
            } else {
                showMessage('没有发现新模型', 'info');
            }
            await loadLoRAModels();
        } else {
            showMessage(data.message || '扫描失败', 'error');
        }
    } catch (error) {
        showMessage('扫描失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 加载 LoRA 模型列表
async function loadLoRAModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models`);
        const data = await response.json();
        
        if (data.success) {
            loraModels = data.models || [];
            renderLoRAModels(loraModels);
        } else {
            throw new Error(data.message || '加载失败');
        }
    } catch (error) {
        console.error('加载 LoRA 模型失败:', error);
        const container = document.getElementById('loraModelsList');
        if (container) {
            container.innerHTML = `
                <div class="text-center py-12 text-red-400">
                    <i class="fa fa-exclamation-triangle text-5xl mb-4"></i>
                    <p>加载失败: ${error.message}</p>
                </div>
            `;
        }
    }
}

// 渲染 LoRA 模型列表
function renderLoRAModels(models) {
    const container = document.getElementById('loraModelsList');
    
    if (!models || models.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 text-gray-400">
                <i class="fa fa-folder-open text-5xl mb-4"></i>
                <p class="text-lg mb-2">暂无 LoRA 模型</p>
                <p class="text-sm">点击"启动训练平台"开始训练，或点击"扫描新模型"发现已有模型</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = models.map(model => {
        const statusInfo = getStatusInfo(model.status);
        const createdDate = new Date(model.created_at).toLocaleString('zh-CN');
        
        return `
            <div class="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-custom bg-white">
                <div class="flex items-start justify-between">
                    <div class="flex-1">
                        <div class="flex items-center space-x-3 mb-2">
                            <div class="w-10 h-10 rounded-lg ${statusInfo.bgClass} flex items-center justify-center flex-shrink-0">
                                <i class="fa fa-cogs ${statusInfo.iconClass}"></i>
                            </div>
                            <div class="flex-1 min-w-0">
                                <h4 class="font-bold text-gray-800 truncate">${escapeHtml(model.model_name)}</h4>
                                <span class="px-2 py-1 text-xs rounded-full ${statusInfo.badgeClass} inline-block">
                                    ${statusInfo.text}
                                </span>
                            </div>
                        </div>
                        
                        <div class="text-sm text-gray-600 space-y-1 ml-13">
                            <div class="flex items-center">
                                <i class="fa fa-cube text-gray-400 w-5"></i>
                                <span>基座: ${escapeHtml(model.base_model)}</span>
                            </div>
                            <div class="flex items-center">
                                <i class="fa fa-database text-gray-400 w-5"></i>
                                <span>大小: ${model.file_size_mb.toFixed(2)} MB</span>
                            </div>
                            ${model.lora_rank ? `
                                <div class="flex items-center">
                                    <i class="fa fa-sliders text-gray-400 w-5"></i>
                                    <span>Rank: ${model.lora_rank} / Alpha: ${model.lora_alpha || 'N/A'}</span>
                                </div>
                            ` : ''}
                            <div class="flex items-center">
                                <i class="fa fa-clock-o text-gray-400 w-5"></i>
                                <span>创建: ${createdDate}</span>
                            </div>
                            ${model.is_deployed ? `
                                <div class="flex items-center text-green-600">
                                    <i class="fa fa-check-circle w-5"></i>
                                    <span>已激活</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                    
                    <div class="flex flex-col space-y-2 ml-4 flex-shrink-0">
                        ${model.is_deployed ? `
                            <button onclick="window.location.href='lora-test.html'" 
                                    class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-custom text-sm whitespace-nowrap">
                                <i class="fa fa-vial mr-1"></i> 测试推理
                            </button>
                        ` : ''}
                        
                        ${!model.is_deployed ? `
                            <button onclick="activateLoRAModel(${model.id})" 
                                    class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-custom text-sm whitespace-nowrap">
                                <i class="fa fa-play mr-1"></i> 激活
                            </button>
                        ` : `
                            <button disabled
                                    class="px-4 py-2 bg-gray-100 text-gray-400 rounded cursor-not-allowed text-sm whitespace-nowrap">
                                <i class="fa fa-check mr-1"></i> 已激活
                            </button>
                        `}
                        
                        <button onclick="deleteLoRAModel(${model.id})" 
                                class="px-3 py-2 bg-red-100 text-red-600 rounded hover:bg-red-200 transition-custom text-sm">
                            <i class="fa fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// 激活 LoRA 模型
async function activateLoRAModel(modelId) {
    if (!confirm('确定要激活此 LoRA 模型吗？激活后可用于推理。')) return;
    
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models/${modelId}/activate`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            showMessage(`LoRA 模型激活成功！模型名: ${data.model_name}`, 'success');
            await loadLoRAModels();
        } else {
            showMessage('激活失败: ' + data.message, 'error');
        }
    } catch (error) {
        showMessage('激活失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 删除 LoRA 模型
async function deleteLoRAModel(modelId) {
    if (!confirm('确定要删除此模型吗？此操作不可恢复！\n\n如果模型正在被助手使用，将无法删除。')) return;
    
    showLoading(true);
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/models/${modelId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            showMessage('模型已删除', 'success');
            await loadLoRAModels();
        } else {
            if (data.in_use) {
                showMessage(`无法删除: ${data.message}\n\n提示: 您可以先解除助手与此模型的关联`, 'error');
            } else {
                showMessage('删除失败: ' + data.message, 'error');
            }
        }
    } catch (error) {
        showMessage('删除失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 获取状态信息
function getStatusInfo(status) {
    const statusMap = {
        'discovered': {
            text: '已发现',
            badgeClass: 'bg-blue-100 text-blue-700',
            bgClass: 'bg-blue-100',
            iconClass: 'text-blue-500'
        },
        'active': {
            text: '已激活',
            badgeClass: 'bg-green-100 text-green-700',
            bgClass: 'bg-green-100',
            iconClass: 'text-green-500'
        },
        'failed': {
            text: '失败',
            badgeClass: 'bg-red-100 text-red-700',
            bgClass: 'bg-red-100',
            iconClass: 'text-red-500'
        }
    };
    
    return statusMap[status] || statusMap['discovered'];
}

// ==================== 页面初始化扩展 ====================

// 修改原有的 DOMContentLoaded 事件，添加 LoRA 初始化
document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    await loadAllModels();
    
    // 初始化 LoRA 相关
    await updateServiceStatus();
    await loadLoRAModels();
    
    // 检查服务状态，如果运行中则开始监控
    const statusResponse = await fetch(`${API_BASE_URL}/api/lora/service/status`).catch(() => null);
    if (statusResponse) {
        const status = await statusResponse.json();
        if (status.running) {
            startServiceMonitoring();
        }
    }
});
