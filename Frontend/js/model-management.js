/**
 * 模型管理页面逻辑
 */

const API_BASE_URL = '';

// 页面状态
let currentTab = 'embedding'; // embedding, llm
let embeddingModels = [];
let llmModels = { local: [], remote: [] };

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
            loadLLMModels()
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
