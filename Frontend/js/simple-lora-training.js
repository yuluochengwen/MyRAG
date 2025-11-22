/**
 * 简易 LoRA 训练页面逻辑
 */

const API_BASE = 'http://localhost:8000';

let uploadedFile = null;
let pollingInterval = null;

// 页面加载
document.addEventListener('DOMContentLoaded', async () => {
    await loadBaseModels();
    await loadTasks();
    setupUploadZone();
    
    // 开始轮询任务状态
    startPolling();
});

// 设置文件上传区域
function setupUploadZone() {
    const uploadZone = document.getElementById('uploadZone');
    const fileInput = document.getElementById('fileInput');
    
    // 点击上传
    uploadZone.addEventListener('click', () => fileInput.click());
    
    // 文件选择
    fileInput.addEventListener('change', handleFileSelect);
    
    // 拖拽上传
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });
    
    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
}

// 处理文件选择
function handleFileSelect(e) {
    const files = e.target.files;
    if (files.length > 0) {
        handleFile(files[0]);
    }
}

// 处理文件上传
async function handleFile(file) {
    // 验证文件类型
    if (!file.name.endsWith('.json') && !file.name.endsWith('.jsonl')) {
        alert('仅支持 JSON 格式文件');
        return;
    }
    
    // 显示上传中
    const uploadZone = document.getElementById('uploadZone');
    uploadZone.innerHTML = `
        <i class="fas fa-spinner fa-spin text-5xl text-blue-600 mb-3"></i>
        <p class="text-gray-600">正在上传...</p>
    `;
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('dataset_type', document.getElementById('datasetType').value);
        
        const response = await fetch(`${API_BASE}/api/simple-lora/upload-dataset`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('上传失败');
        }
        
        const data = await response.json();
        uploadedFile = data;
        
        // 显示上传成功
        document.getElementById('datasetName').textContent = data.filename;
        document.getElementById('datasetSize').textContent = `(${data.size_mb.toFixed(2)} MB)`;
        document.getElementById('uploadedDataset').classList.remove('hidden');
        
        // 恢复上传区域
        uploadZone.innerHTML = `
            <i class="fas fa-cloud-upload-alt text-5xl text-gray-400 mb-3"></i>
            <p class="text-gray-600 mb-2">拖拽 JSON 文件到此处，或点击选择文件</p>
            <p class="text-sm text-gray-500">支持 Alpaca 和 ShareGPT 格式</p>
        `;
        
        showToast('数据集上传成功', 'success');
    } catch (error) {
        console.error('上传失败:', error);
        alert('上传失败: ' + error.message);
        
        // 恢复上传区域
        uploadZone.innerHTML = `
            <i class="fas fa-cloud-upload-alt text-5xl text-gray-400 mb-3"></i>
            <p class="text-gray-600 mb-2">拖拽 JSON 文件到此处，或点击选择文件</p>
            <p class="text-sm text-gray-500">支持 Alpaca 和 ShareGPT 格式</p>
        `;
    }
}

// 清除数据集
function clearDataset() {
    uploadedFile = null;
    const datasetDiv = document.getElementById('uploadedDataset');
    if (datasetDiv) {
        datasetDiv.classList.add('hidden');
    }
    
    const fileInput = document.getElementById('fileInput');
    if (fileInput) {
        fileInput.value = '';
    }
}

// 加载基座模型列表
async function loadBaseModels() {
    try {
        const response = await fetch(`${API_BASE}/api/simple-lora/models`);
        const data = await response.json();
        
        const select = document.getElementById('baseModel');
        select.innerHTML = '<option value="">请选择基座模型</option>';
        
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.value || model.name; // 优先使用 value (真实目录名)
            option.textContent = `${model.name} (${model.size_mb.toFixed(0)} MB)`;
            select.appendChild(option);
        });
        
        if (data.models.length === 0) {
            select.innerHTML = '<option value="">暂无可用模型</option>';
        }
    } catch (error) {
        console.error('加载模型列表失败:', error);
        document.getElementById('baseModel').innerHTML = '<option value="">加载失败</option>';
    }
}

// 开始训练
async function startTraining() {
    // 验证输入
    const taskName = document.getElementById('taskName').value.trim();
    const baseModel = document.getElementById('baseModel').value;
    const datasetType = document.getElementById('datasetType').value;
    
    if (!uploadedFile) {
        alert('请先上传数据集');
        return;
    }
    
    if (!baseModel) {
        alert('请选择基座模型');
        return;
    }
    
    if (!taskName) {
        alert('请输入任务名称');
        return;
    }
    
    // 禁用按钮
    const btn = document.getElementById('startTrainingBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>创建任务中...';
    
    try {
        const formData = new FormData();
        formData.append('task_name', taskName);
        formData.append('base_model', baseModel);
        formData.append('dataset_filename', uploadedFile.filename);
        formData.append('dataset_type', datasetType);
        
        const response = await fetch(`${API_BASE}/api/simple-lora/train`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        // 调试日志
        console.log('Training response:', { status: response.status, data });
        
        if (!response.ok) {
            throw new Error(data.detail || data.message || '创建训练任务失败');
        }
        
        showToast(`训练任务已启动 (ID: ${data.task_id})，完成后请前往【模型管理】页面扫描LoRA模型`, 'info', 6000);
        
        // 重置表单
        const taskNameInput = document.getElementById('taskName');
        if (taskNameInput) {
            taskNameInput.value = '';
        }
        clearDataset();
        
        // 刷新任务列表
        await loadTasks();
        
    } catch (error) {
        console.error('启动训练失败:', error);
        alert('启动训练失败: ' + error.message);
    } finally {
        // 恢复按钮
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-play mr-2"></i>开始训练';
    }
}

// 加载训练任务列表
async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE}/api/simple-lora/tasks`);
        const data = await response.json();
        
        const container = document.getElementById('tasksList');
        
        if (data.tasks.length === 0) {
            container.innerHTML = `
                <div class="text-center text-gray-500 py-8">
                    <i class="fas fa-inbox text-4xl mb-2"></i>
                    <p>暂无训练任务</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = data.tasks.map(task => renderTaskCard(task)).join('');
        
    } catch (error) {
        console.error('加载任务列表失败:', error);
    }
}

// 渲染任务卡片
function renderTaskCard(task) {
    const statusConfig = {
        pending: { icon: 'clock', color: 'gray', text: '等待中' },
        running: { icon: 'spinner fa-spin', color: 'blue', text: '训练中' },
        completed: { icon: 'check-circle', color: 'green', text: '已完成' },
        failed: { icon: 'times-circle', color: 'red', text: '失败' }
    };
    
    const config = statusConfig[task.status] || statusConfig.pending;
    
    return `
        <div class="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
            <div class="flex items-start justify-between mb-2">
                <h3 class="font-semibold text-gray-800 truncate">${task.task_name}</h3>
                <span class="text-xs px-2 py-1 rounded-full bg-${config.color}-100 text-${config.color}-700">
                    <i class="fas fa-${config.icon}"></i> ${config.text}
                </span>
            </div>
            
            <p class="text-sm text-gray-600 mb-2">${task.base_model}</p>
            
            ${task.status === 'running' ? `
                <div class="mb-2">
                    <div class="flex items-center justify-between text-xs text-gray-600 mb-1">
                        <span>进度</span>
                        <span>${task.progress.toFixed(1)}%</span>
                    </div>
                    <div class="w-full bg-gray-200 rounded-full h-2">
                        <div class="training-progress h-2 rounded-full" style="width: ${task.progress}%"></div>
                    </div>
                </div>
            ` : ''}
            
            <div class="flex items-center justify-between text-xs text-gray-500 mt-2">
                <span><i class="far fa-calendar mr-1"></i>${new Date(task.created_at).toLocaleString('zh-CN')}</span>
                ${task.status === 'running' ? `
                    <button onclick="viewTaskDetail(${task.task_id})" class="text-blue-600 hover:text-blue-800">
                        <i class="fas fa-eye"></i> 详情
                    </button>
                ` : ''}
            </div>
        </div>
    `;
}

// 查看任务详情
async function viewTaskDetail(taskId) {
    try {
        const response = await fetch(`${API_BASE}/api/simple-lora/tasks/${taskId}`);
        const task = await response.json();
        
        alert(`任务详情\n\n` +
              `任务ID: ${task.task_id}\n` +
              `任务名称: ${task.task_name}\n` +
              `状态: ${task.status}\n` +
              `进度: ${task.progress.toFixed(2)}%\n` +
              `当前轮次: ${task.current_epoch}\n` +
              `消息: ${task.message || '无'}`);
    } catch (error) {
        console.error('获取任务详情失败:', error);
        alert('获取任务详情失败');
    }
}

// 开始轮询
function startPolling() {
    // 每 5 秒刷新任务列表
    pollingInterval = setInterval(loadTasks, 5000);
}

// 停止轮询
function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

// Toast 提示
function showToast(message, type = 'info', duration = 3000) {
    const colors = {
        success: 'bg-green-600',
        error: 'bg-red-600',
        info: 'bg-blue-600'
    };
    
    const toast = document.createElement('div');
    toast.className = `fixed top-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in max-w-md`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, duration);
}

// 页面卸载时停止轮询
window.addEventListener('beforeunload', stopPolling);
