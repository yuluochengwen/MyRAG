/**
 * 智能助手页面逻辑
 */

const API_BASE_URL = '';

// 页面状态
let assistants = [];
let knowledgeBases = [];
let llmModels = { local: [], remote: [] };
let embeddingModels = [];
let promptTemplates = [];

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    await loadInitialData();
    setupEventListeners();
});

async function loadInitialData() {
    showLoading(true);
    try {
        await Promise.all([
            loadAssistants(),
            loadKnowledgeBases(),
            loadModels(),
            loadPromptTemplates()
        ]);
    } catch (error) {
        showMessage('加载数据失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function setupEventListeners() {
    // 创建模态框关闭
    document.getElementById('closeModal')?.addEventListener('click', closeCreateModal);
    document.getElementById('cancelCreate')?.addEventListener('click', closeCreateModal);
    
    // 编辑模态框关闭
    document.getElementById('closeEditModal')?.addEventListener('click', closeEditModal);
    document.getElementById('cancelEdit')?.addEventListener('click', closeEditModal);
    
    // 知识库选择变化
    document.getElementById('kbSelect')?.addEventListener('change', onKnowledgeBaseChange);
    
    // 提示词模板选择
    document.getElementById('promptTemplateSelect')?.addEventListener('change', onPromptTemplateChange);
    document.getElementById('editPromptTemplateSelect')?.addEventListener('change', onEditPromptTemplateChange);
    
    // 提交表单
    document.getElementById('createAssistantForm')?.addEventListener('submit', handleCreateAssistant);
    document.getElementById('editAssistantForm')?.addEventListener('submit', handleUpdateAssistant);
    
    // 搜索功能
    const searchInput = document.getElementById('assistantSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearchAssistants);
    }
}

// ==================== 数据加载 ====================

async function loadAssistants() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/assistants`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || '加载助手列表失败');
        }
        assistants = await response.json();
        console.log('助手列表加载成功:', assistants.length);
        renderAssistants();
    } catch (error) {
        console.error('加载助手列表失败:', error);
        showMessage('加载助手列表失败: ' + error.message, 'error');
        assistants = [];
        renderAssistants();
    }
}

async function loadKnowledgeBases() {
    const response = await fetch(`${API_BASE_URL}/api/knowledge-bases`);
    if (!response.ok) throw new Error('加载知识库列表失败');
    knowledgeBases = await response.json(); // 直接是数组
    renderKnowledgeBaseOptions();
}

async function loadModels() {
    // 加载LLM模型
    const llmResponse = await fetch(`${API_BASE_URL}/api/assistants/models/llm`);
    if (llmResponse.ok) {
        llmModels = await llmResponse.json();
        renderLLMOptions();
    }
    
    // 加载Embedding模型 - 使用知识库的统一接口，支持所有provider
    const embResponse = await fetch(`${API_BASE_URL}/api/knowledge-bases/embedding/models`);
    if (embResponse.ok) {
        const data = await embResponse.json();
        embeddingModels = data.models || [];
        renderEmbeddingOptions();
    }
}

async function loadPromptTemplates() {
    const response = await fetch(`${API_BASE_URL}/api/assistants/prompt-templates`);
    if (response.ok) {
        const data = await response.json();
        promptTemplates = data.templates || [];
        renderPromptTemplateOptions();
    }
}

// ==================== 渲染函数 ====================

function renderAssistants() {
    const grid = document.getElementById('assistantsGrid');
    if (!grid) {
        console.error('找不到 assistantsGrid 元素');
        return;
    }
    
    console.log('渲染助手列表:', assistants.length);
    
    // 图标映射
    const iconMap = {
        'blue': { bg: 'bg-blue-100', text: 'text-blue-500', icon: 'fa-robot' },
        'purple': { bg: 'bg-purple-100', text: 'text-purple-500', icon: 'fa-code' },
        'orange': { bg: 'bg-orange-100', text: 'text-orange-500', icon: 'fa-shopping-cart' },
        'green': { bg: 'bg-green-100', text: 'text-green-500', icon: 'fa-leaf' },
        'pink': { bg: 'bg-pink-100', text: 'text-pink-500', icon: 'fa-heart' }
    };
    
    let html = '';
    
    // 创建新助手卡片(始终在第一个位置)
    html += `
        <div class="bg-white rounded-xl p-6 card-shadow hover:shadow-lg transition-custom border-2 border-dashed border-gray-300 hover:border-primary cursor-pointer flex flex-col items-center justify-center text-center group" onclick="openCreateModal()">
            <div class="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-custom">
                <i class="fa fa-plus text-primary text-2xl"></i>
            </div>
            <h3 class="text-lg font-bold mb-2">创建智能助手</h3>
            <p class="text-gray-500 mb-4">配置知识库和模型，创建专属AI助手</p>
            <button type="button" class="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-custom">
                立即创建
            </button>
        </div>
    `;
    
    // 现有助手卡片
    assistants.forEach(assistant => {
        const theme = iconMap[assistant.color_theme] || iconMap['blue'];
        const statusColor = assistant.status === 'active' ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-600';
        const statusText = assistant.status === 'active' ? '已启用' : '已禁用';
        
        // 格式化日期
        const createdDate = assistant.created_at ? new Date(assistant.created_at).toLocaleDateString('zh-CN') : '未知';
        
        // 知识库标签
        let kbTags = '';
        if (assistant.kb_names && assistant.kb_names.length > 0) {
            kbTags = assistant.kb_names.map(name => 
                `<span class="px-2 py-1 bg-blue-50 text-blue-600 text-xs rounded-full">${escapeHtml(name)}</span>`
            ).join('');
        }
        
        // LLM模型标签
        const llmTag = `<span class="px-2 py-1 bg-green-50 text-green-600 text-xs rounded-full">${escapeHtml(assistant.llm_model)}</span>`;
        
        html += `
            <div class="bg-white rounded-xl p-6 card-shadow hover:shadow-lg transition-custom flex flex-col cursor-pointer" onclick="navigateToChat(${assistant.id})">
                <!-- 顶部: 图标 + 下拉菜单 -->
                <div class="flex justify-between items-start mb-4">
                    <div class="w-12 h-12 rounded-lg ${theme.bg} flex items-center justify-center">
                        <i class="fa ${theme.icon} ${theme.text} text-xl"></i>
                    </div>
                    <div class="dropdown relative">
                        <button class="p-3 rounded hover:bg-gray-100 transition-custom" onclick="toggleDropdown(event, ${assistant.id})">
                            <i class="fa fa-ellipsis-v text-gray-400 text-lg"></i>
                        </button>
                        <div id="dropdown-${assistant.id}" class="dropdown-menu absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg py-2 hidden z-10">
                            <a href="#" onclick="navigateToChat(${assistant.id}); return false;" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
                                <i class="fa fa-comments mr-2"></i>开始对话
                            </a>
                            <a href="#" onclick="editAssistant(${assistant.id}, event); return false;" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
                                <i class="fa fa-edit mr-2"></i>编辑配置
                            </a>
                            <a href="#" onclick="toggleAssistantStatus(${assistant.id}, event); return false;" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-100">
                                <i class="fa fa-toggle-on mr-2"></i>启用/禁用
                            </a>
                            <div class="border-t border-gray-200 my-1"></div>
                            <a href="#" onclick="deleteAssistant(${assistant.id}, event); return false;" class="block px-4 py-2 text-sm text-danger hover:bg-red-50">
                                <i class="fa fa-trash mr-2"></i>删除
                            </a>
                        </div>
                    </div>
                </div>
                
                <!-- 标题和描述 -->
                <h3 class="text-lg font-bold mb-1">${escapeHtml(assistant.name)}</h3>
                <p class="text-gray-500 text-sm mb-4">${escapeHtml(assistant.description || '暂无描述')}</p>
                
                <!-- 标签chips -->
                <div class="flex flex-wrap gap-2 mb-4">
                    ${kbTags}
                    ${llmTag}
                </div>
                
                <!-- 底部统计 -->
                <div class="mt-auto pt-4 border-t border-gray-100 flex justify-between items-center">
                    <div class="flex items-center">
                        <span class="text-sm text-gray-500 mr-4">
                            <i class="fa fa-comments-o mr-1"></i> ${assistant.conversation_count || 0}次对话
                        </span>
                        <span class="text-sm text-gray-500">
                            <i class="fa fa-calendar-o mr-1"></i> ${createdDate}
                        </span>
                    </div>
                    <span class="px-3 py-1 ${statusColor} text-xs rounded-full">
                        ${statusText}
                    </span>
                </div>
            </div>
        `;
    });
    
    console.log('[RENDER] 准备更新DOM, 助手数量:', assistants.length);
    grid.innerHTML = html;
    console.log('[RENDER] DOM更新完成');
}

function renderKnowledgeBaseOptions() {
    const select = document.getElementById('kbSelect');
    if (!select) return;
    
    // 按embedding_model和provider分组
    const grouped = knowledgeBases.reduce((acc, kb) => {
        const provider = kb.embedding_provider || 'transformers';
        const providerIcon = provider === 'ollama' ? '🦙' : '🤖';
        const key = `${providerIcon} ${kb.embedding_model} (${provider})`;
        if (!acc[key]) acc[key] = [];
        acc[key].push(kb);
        return acc;
    }, {});
    
    let html = '<option value="">不绑定知识库(纯对话)</option>';
    Object.entries(grouped).forEach(([label, kbs]) => {
        html += `<optgroup label="嵌入模型: ${label}">`;
        kbs.forEach(kb => {
            html += `<option value="${kb.id}" data-embedding="${kb.embedding_model}" data-provider="${kb.embedding_provider || 'transformers'}">${kb.name}</option>`;
        });
        html += '</optgroup>';
    });
    
    select.innerHTML = html;
}

function renderLLMOptions() {
    const select = document.getElementById('llmModelSelect');
    if (!select) return;
    
    let html = '';
    
    // 本地模型 (Transformers)
    if (llmModels.local && llmModels.local.length > 0) {
        html += '<optgroup label="🤖 本地模型 (Transformers)">';
        llmModels.local.forEach(model => {
            html += `<option value="${model.name}" data-provider="local">${model.name}</option>`;
        });
        html += '</optgroup>';
    }
    
    // Ollama模型
    if (llmModels.ollama && llmModels.ollama.length > 0) {
        html += '<optgroup label="🦙 Ollama模型">';
        llmModels.ollama.forEach(model => {
            html += `<option value="${model.name}" data-provider="ollama">${model.name} (${model.size}GB)</option>`;
        });
        html += '</optgroup>';
    }
    
    // 远程模型
    if (llmModels.remote && llmModels.remote.length > 0) {
        html += '<optgroup label="☁️ 远程API">';
        llmModels.remote.forEach(model => {
            html += `<option value="${model.name}" data-provider="${model.provider}">${model.name}</option>`;
        });
        html += '</optgroup>';
    }
    
    select.innerHTML = html || '<option value="">无可用模型</option>';
}

function renderEmbeddingOptions() {
    const select = document.getElementById('embeddingModelSelect');
    if (!select) return;
    
    // 按provider分组显示
    const grouped = embeddingModels.reduce((acc, model) => {
        const provider = model.provider || 'transformers';
        if (!acc[provider]) acc[provider] = [];
        acc[provider].push(model);
        return acc;
    }, {});
    
    let html = '';
    
    // Transformers模型
    if (grouped.transformers && grouped.transformers.length > 0) {
        html += '<optgroup label="🤖 Transformers (本地)">';
        grouped.transformers.forEach(model => {
            html += `<option value="${model.name}" data-provider="transformers">${model.name} (${model.dimension || '?'}维)</option>`;
        });
        html += '</optgroup>';
    }
    
    // Ollama模型
    if (grouped.ollama && grouped.ollama.length > 0) {
        html += '<optgroup label="🦙 Ollama (本地)">';
        grouped.ollama.forEach(model => {
            html += `<option value="${model.name}" data-provider="ollama">${model.name}${model.size ? ' (' + model.size + ')' : ''}</option>`;
        });
        html += '</optgroup>';
    }
    
    select.innerHTML = html || '<option value="">无可用模型</option>';
}

function renderPromptTemplateOptions() {
    const select = document.getElementById('promptTemplateSelect');
    if (!select) return;
    
    let html = '<option value="">选择提示词模板(可选)</option>';
    html += promptTemplates.map(tpl => 
        `<option value="${tpl.name}">${tpl.name} - ${tpl.description}</option>`
    ).join('');
    
    select.innerHTML = html;
}

// ==================== 事件处理 ====================

function onKnowledgeBaseChange(e) {
    const kbId = e.target.value;
    const embeddingSelect = document.getElementById('embeddingModelSelect');
    const embeddingGroup = document.getElementById('embeddingModelGroup');
    
    if (kbId) {
        // 选择了知识库,自动填充并禁用embedding选择
        const kb = knowledgeBases.find(kb => kb.id == kbId);
        if (kb && embeddingSelect) {
            // 检查模型是否在下拉框中
            const modelExists = Array.from(embeddingSelect.options).some(
                opt => opt.value === kb.embedding_model
            );
            
            // 如果模型不存在，动态添加
            if (!modelExists) {
                const provider = kb.embedding_provider || 'transformers';
                const providerLabel = provider === 'ollama' ? '🦙 Ollama' : '🤖 Transformers';
                
                // 查找或创建对应的optgroup
                let optgroup = Array.from(embeddingSelect.querySelectorAll('optgroup')).find(
                    group => group.label.includes(provider === 'ollama' ? 'Ollama' : 'Transformers')
                );
                
                if (!optgroup) {
                    optgroup = document.createElement('optgroup');
                    optgroup.label = `${providerLabel} (本地)`;
                    embeddingSelect.appendChild(optgroup);
                }
                
                // 添加选项
                const option = document.createElement('option');
                option.value = kb.embedding_model;
                option.textContent = `${kb.embedding_model} (来自知识库)`;
                option.dataset.provider = provider;
                optgroup.appendChild(option);
                
                console.log(`动态添加${provider}模型: ${kb.embedding_model}`);
            }
            
            embeddingSelect.value = kb.embedding_model;
            embeddingSelect.disabled = true;
            if (embeddingGroup) {
                embeddingGroup.classList.add('opacity-50');
            }
        }
    } else {
        // 未选择知识库,启用embedding选择
        if (embeddingSelect) {
            embeddingSelect.disabled = false;
            if (embeddingGroup) {
                embeddingGroup.classList.remove('opacity-50');
            }
        }
    }
}

function onPromptTemplateChange(e) {
    const templateName = e.target.value;
    const textarea = document.getElementById('systemPrompt');
    
    if (templateName && textarea) {
        const template = promptTemplates.find(t => t.name === templateName);
        if (template) {
            textarea.value = template.content;
        }
    }
}

async function handleCreateAssistant(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const kbIds = formData.get('kb_id') ? [parseInt(formData.get('kb_id'))] : null;
    
    const data = {
        name: formData.get('name'),
        description: formData.get('description'),
        kb_ids: kbIds,
        embedding_model: kbIds ? null : formData.get('embedding_model'),
        llm_model: formData.get('llm_model'),
        llm_provider: document.querySelector('#llmModelSelect option:checked')?.dataset.provider || 'local',
        system_prompt: formData.get('system_prompt') || null,
        color_theme: formData.get('color_theme')
    };
    
    try {
        console.log('[CREATE] 开始创建智能助手:', data);
        
        const response = await fetch(`${API_BASE_URL}/api/assistants`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '创建失败');
        }
        
        const result = await response.json();
        console.log('[CREATE] 创建成功:', result);
        
        // 关闭模态框
        console.log('[CREATE] 关闭模态框');
        closeCreateModal();
        
        // 显示成功消息
        console.log('[CREATE] 显示成功消息');
        showMessage('智能助手创建成功！', 'success');
        
        // 重新加载助手列表
        console.log('[CREATE] 开始重新加载助手列表');
        await loadAssistants();
        console.log('[CREATE] 助手列表加载完成');
        
    } catch (error) {
        console.error('[CREATE] 创建失败:', error);
        showMessage('创建失败: ' + error.message, 'error');
    }
}

async function handleUpdateAssistant(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const assistantId = document.getElementById('editAssistantId').value;
    
    // 获取多选知识库ID
    const editKbSelect = document.getElementById('editKbSelect');
    const selectedKbIds = Array.from(editKbSelect.selectedOptions)
        .map(opt => parseInt(opt.value))
        .filter(id => !isNaN(id));
    
    const data = {
        name: formData.get('name'),
        description: formData.get('description'),
        kb_ids: selectedKbIds.length > 0 ? selectedKbIds : null,
        llm_model: formData.get('llm_model'),
        llm_provider: document.querySelector('#editLlmModelSelect option:checked')?.dataset.provider || 'local',
        system_prompt: formData.get('system_prompt') || null,
        color_theme: formData.get('color_theme')
    };
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/assistants/${assistantId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '更新失败');
        }
        
        showMessage('助手配置已更新！', 'success');
        closeEditModal();
        await loadAssistants();
    } catch (error) {
        showMessage('更新失败: ' + error.message, 'error');
    }
}

// ==================== 页面跳转 ====================

function navigateToChat(assistantId) {
    window.location.href = `chat.html?assistant_id=${assistantId}`;
}

// ==================== 助手操作 ====================

async function deleteAssistant(id, event) {
    // 阻止事件冒泡，避免触发卡片的navigateToChat
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    if (!confirm('确定要删除这个助手吗？')) {
        console.log('[DELETE] 用户取消删除');
        return;
    }
    
    try {
        console.log('[DELETE] 开始删除智能助手:', id);
        
        const response = await fetch(`${API_BASE_URL}/api/assistants/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || '删除失败');
        }
        
        console.log('[DELETE] 删除成功:', id);
        
        // 显示成功消息
        console.log('[DELETE] 显示成功消息');
        showMessage('助手已删除', 'success');
        
        // 重新加载助手列表
        console.log('[DELETE] 开始重新加载助手列表');
        await loadAssistants();
        console.log('[DELETE] 助手列表加载完成');
        
    } catch (error) {
        console.error('[DELETE] 删除失败:', error);
        showMessage('删除失败: ' + error.message, 'error');
    }
}

function startChat(assistantId) {
    // TODO: 跳转到对话页面或打开对话窗口
    showMessage(`即将开始与助手 #${assistantId} 的对话`, 'info');
    console.log('Start chat with assistant:', assistantId);
}

async function editAssistant(id, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    try {
        // 加载助手详情
        const response = await fetch(`${API_BASE_URL}/api/assistants/${id}`);
        if (!response.ok) throw new Error('加载助手信息失败');
        
        const assistant = await response.json();
        
        // 填充表单
        document.getElementById('editAssistantId').value = assistant.id;
        document.getElementById('editName').value = assistant.name;
        document.getElementById('editDescription').value = assistant.description || '';
        document.getElementById('editSystemPrompt').value = assistant.system_prompt || '';
        
        // 填充LLM模型
        renderEditLLMOptions();
        document.getElementById('editLlmModelSelect').value = assistant.llm_model;
        
        // 填充知识库选择（多选）
        renderEditKnowledgeBaseOptions();
        const editKbSelect = document.getElementById('editKbSelect');
        if (assistant.kb_ids && Array.isArray(assistant.kb_ids)) {
            Array.from(editKbSelect.options).forEach(option => {
                option.selected = assistant.kb_ids.includes(parseInt(option.value));
            });
        }
        
        // 填充配色主题
        const colorRadio = document.querySelector(`#editAssistantForm input[name="color_theme"][value="${assistant.color_theme}"]`);
        if (colorRadio) colorRadio.checked = true;
        
        // 填充提示词模板选项
        renderEditPromptTemplateOptions();
        
        // 打开模态框
        document.getElementById('editAssistantModal').classList.remove('hidden');
        
    } catch (error) {
        showMessage('加载助手信息失败: ' + error.message, 'error');
    }
}

async function toggleAssistantStatus(id, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    try {
        // TODO: 实现状态切换API
        showMessage('状态切换功能开发中...', 'info');
        console.log('Toggle status for assistant:', id);
    } catch (error) {
        showMessage('操作失败: ' + error.message, 'error');
    }
}

function toggleDropdown(event, assistantId) {
    event.stopPropagation();
    const dropdown = document.getElementById(`dropdown-${assistantId}`);
    
    // 关闭所有其他下拉菜单
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
        if (menu.id !== `dropdown-${assistantId}`) {
            menu.classList.add('hidden');
        }
    });
    
    // 切换当前下拉菜单
    dropdown.classList.toggle('hidden');
}

// 点击外部关闭所有下拉菜单
document.addEventListener('click', () => {
    document.querySelectorAll('.dropdown-menu').forEach(menu => {
        menu.classList.add('hidden');
    });
});

function startChat(assistantId) {
    // TODO: 跳转到对话页面或打开对话界面
    alert(`助手对话功能待实现 (Assistant ID: ${assistantId})`);
}

// ==================== UI 辅助函数 ====================

function openCreateModal() {
    document.getElementById('createAssistantModal').classList.remove('hidden');
    document.getElementById('createAssistantForm').reset();
    
    // 重置embedding选择状态
    const embeddingSelect = document.getElementById('embeddingModelSelect');
    if (embeddingSelect) embeddingSelect.disabled = false;
}

function closeCreateModal() {
    document.getElementById('createAssistantModal').classList.add('hidden');
}

function closeEditModal() {
    document.getElementById('editAssistantModal').classList.add('hidden');
}

function renderEditKnowledgeBaseOptions() {
    const select = document.getElementById('editKbSelect');
    if (!select) return;
    
    let html = '';
    knowledgeBases.forEach(kb => {
        html += `<option value="${kb.id}">${kb.name} (${kb.embedding_model})</option>`;
    });
    
    select.innerHTML = html;
}

function renderEditLLMOptions() {
    const select = document.getElementById('editLlmModelSelect');
    if (!select) return;
    
    let html = '';
    
    // 本地模型 (Transformers)
    if (llmModels.local && llmModels.local.length > 0) {
        html += '<optgroup label="🤖 本地模型 (Transformers)">';
        llmModels.local.forEach(model => {
            html += `<option value="${model.name}" data-provider="local">${model.name}</option>`;
        });
        html += '</optgroup>';
    }
    
    // Ollama模型
    if (llmModels.ollama && llmModels.ollama.length > 0) {
        html += '<optgroup label="🦙 Ollama模型">';
        llmModels.ollama.forEach(model => {
            html += `<option value="${model.name}" data-provider="ollama">${model.name} (${model.size}GB)</option>`;
        });
        html += '</optgroup>';
    }
    
    // 远程模型
    if (llmModels.remote && llmModels.remote.length > 0) {
        html += '<optgroup label="☁️ 远程API">';
        llmModels.remote.forEach(model => {
            html += `<option value="${model.name}" data-provider="${model.provider}">${model.name}</option>`;
        });
        html += '</optgroup>';
    }
    
    select.innerHTML = html || '<option value="">无可用模型</option>';
}

function renderEditPromptTemplateOptions() {
    const select = document.getElementById('editPromptTemplateSelect');
    if (!select) return;
    
    let html = '<option value="">选择提示词模板(可选)</option>';
    html += promptTemplates.map(tpl => 
        `<option value="${tpl.name}">${tpl.name} - ${tpl.description}</option>`
    ).join('');
    
    select.innerHTML = html;
}

function onEditPromptTemplateChange(e) {
    const templateName = e.target.value;
    const textarea = document.getElementById('editSystemPrompt');
    
    if (templateName && textarea) {
        const template = promptTemplates.find(t => t.name === templateName);
        if (template) {
            textarea.value = template.content;
        }
    }
}

function showLoading(show) {
    // TODO: 实现loading效果
    console.log('Loading:', show);
}

// 使用统一的Toast提示（定义在common.js中）
function showMessage(message, type = 'info') {
    showToast(message, type);
}

// ==================== 搜索功能 ====================

function handleSearchAssistants(e) {
    const keyword = e.target.value.toLowerCase();
    
    const cards = document.querySelectorAll('#assistantsGrid > div');
    
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
