/**
 * LoRA 训练页面逻辑
 */

const API_BASE_URL = '';

// 页面状态
let baseModels = [];
let selectedFile = null;
let validationPassed = false;
let currentJobId = null;
let currentClientId = null;
let ws = null;
let lossChart = null;
let lossData = [];

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    setupEventListeners();
    await loadBaseModels();
});

function setupEventListeners() {
    // 移动端菜单切换
    document.getElementById('mobile-menu-btn')?.addEventListener('click', function() {
        document.getElementById('mobile-menu')?.classList.toggle('hidden');
    });
    
    // 文件上传
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('dataset-file');
    
    uploadArea?.addEventListener('click', () => fileInput?.click());
    
    fileInput?.addEventListener('change', handleFileSelect);
    
    // 拖拽上传
    uploadArea?.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea?.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea?.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect({ target: fileInput });
        }
    });
    
    // 移除文件
    document.getElementById('remove-file-btn')?.addEventListener('click', removeFile);
    
    // 高级参数折叠
    document.getElementById('advanced-toggle')?.addEventListener('click', toggleAdvancedParams);
    
    // 表单提交
    document.getElementById('training-form')?.addEventListener('submit', handleFormSubmit);
    
    // 取消训练
    document.getElementById('cancel-training-btn')?.addEventListener('click', cancelTraining);
}

// ==================== 加载基座模型 ====================

async function loadBaseModels() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/base-models`);
        if (!response.ok) throw new Error('加载基座模型失败');
        
        const data = await response.json();
        baseModels = data.models || [];
        
        const select = document.getElementById('base-model-select');
        if (select) {
            select.innerHTML = '<option value="">选择基座模型...</option>' +
                baseModels.map(model => 
                    `<option value="${model.name}">${model.name}</option>`
                ).join('');
        }
    } catch (error) {
        console.error('加载基座模型失败:', error);
        showMessage('加载基座模型失败: ' + error.message, 'error');
    }
}

// ==================== 文件处理 ====================

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!file.name.endsWith('.json')) {
        showMessage('请上传 JSON 格式的数据集文件', 'warning');
        return;
    }
    
    selectedFile = file;
    document.getElementById('file-name').textContent = file.name;
    document.getElementById('file-info').classList.remove('hidden');
    
    // 验证数据集
    validateDataset(file);
}

function removeFile() {
    selectedFile = null;
    validationPassed = false;
    document.getElementById('dataset-file').value = '';
    document.getElementById('file-info').classList.add('hidden');
    updateSubmitButton();
}

async function validateDataset(file) {
    const validationResult = document.getElementById('validation-result');
    validationResult.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i>正在验证数据集...';
    validationPassed = false;
    updateSubmitButton();
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE_URL}/api/lora/validate-dataset`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok && result.valid) {
            validationPassed = true;
            validationResult.innerHTML = `
                <div class="text-green-600">
                    <i class="fa fa-check-circle mr-2"></i>
                    验证通过 - ${result.format_type} 格式，共 ${result.sample_count} 条样本
                </div>
            `;
        } else {
            validationPassed = false;
            const errors = result.errors || [result.detail || '验证失败'];
            validationResult.innerHTML = `
                <div class="text-danger">
                    <i class="fa fa-exclamation-circle mr-2"></i>
                    验证失败：${errors.join('; ')}
                </div>
            `;
        }
    } catch (error) {
        validationPassed = false;
        validationResult.innerHTML = `
            <div class="text-danger">
                <i class="fa fa-exclamation-circle mr-2"></i>
                验证失败: ${error.message}
            </div>
        `;
    }
    
    updateSubmitButton();
}

function updateSubmitButton() {
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) {
        submitBtn.disabled = !validationPassed;
    }
}

// ==================== 高级参数折叠 ====================

function toggleAdvancedParams() {
    const params = document.getElementById('advanced-params');
    const icon = document.getElementById('advanced-icon');
    
    if (params.classList.contains('hidden')) {
        params.classList.remove('hidden');
        icon.classList.add('rotated');
    } else {
        params.classList.add('hidden');
        icon.classList.remove('rotated');
    }
}

// ==================== 表单提交 ====================

async function handleFormSubmit(event) {
    event.preventDefault();
    
    if (!validationPassed) {
        showMessage('请先上传并验证数据集', 'warning');
        return;
    }
    
    const baseModel = document.getElementById('base-model-select').value;
    const loraName = document.getElementById('lora-name').value.trim();
    const trainingMode = document.querySelector('input[name="training-mode"]:checked').value;
    
    if (!baseModel || !loraName) {
        showMessage('请填写所有必填项', 'warning');
        return;
    }
    
    // 收集训练参数
    const trainingConfig = {
        base_model: baseModel,
        lora_name: loraName,
        training_mode: trainingMode,
        lora_rank: parseInt(document.getElementById('lora-rank').value),
        lora_alpha: parseInt(document.getElementById('lora-alpha').value),
        lora_dropout: parseFloat(document.getElementById('lora-dropout').value),
        learning_rate: parseFloat(document.getElementById('learning-rate').value),
        batch_size: parseInt(document.getElementById('batch-size').value),
        epochs: parseInt(document.getElementById('epochs').value),
        max_seq_length: parseInt(document.getElementById('max-seq-length').value),
        description: document.getElementById('lora-description').value.trim()
    };
    
    // 提交训练任务
    await submitTrainingJob(trainingConfig);
}

async function submitTrainingJob(config) {
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin mr-2"></i>提交中...';
    
    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('config', JSON.stringify(config));
        
        const response = await fetch(`${API_BASE_URL}/api/lora/train`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '提交训练任务失败');
        }
        
        const result = await response.json();
        currentJobId = result.job_id;
        currentClientId = result.client_id;
        
        showMessage('训练任务已提交', 'success');
        
        // 切换到进度显示区域
        document.getElementById('training-config-section').classList.add('hidden');
        document.getElementById('training-progress-section').classList.remove('hidden');
        
        // 初始化 Loss 图表
        initLossChart();
        
        // 建立 WebSocket 连接
        connectWebSocket();
        
    } catch (error) {
        showMessage('提交训练任务失败: ' + error.message, 'error');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa fa-rocket mr-2"></i>开始训练';
    }
}

// ==================== WebSocket 连接 ====================

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/training/${currentClientId}`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket 连接已建立');
        addLog('WebSocket 连接成功');
    };
    
    ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (error) {
            console.error('解析 WebSocket 消息失败:', error);
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
        addLog('WebSocket 连接错误', 'error');
    };
    
    ws.onclose = () => {
        console.log('WebSocket 连接已关闭');
        addLog('WebSocket 连接已关闭');
    };
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'progress':
            updateProgress(message.data);
            break;
        case 'log':
            addLog(message.data.message, message.data.level);
            break;
        case 'loss':
            updateLossChart(message.data.step, message.data.loss);
            break;
        case 'completed':
            handleTrainingCompleted(message.data);
            break;
        case 'error':
            handleTrainingError(message.data);
            break;
        case 'cancelled':
            handleTrainingCancelled();
            break;
        default:
            console.log('未知消息类型:', message.type);
    }
}

// ==================== 进度更新 ====================

function updateProgress(data) {
    const percentage = data.percentage || 0;
    const currentEpoch = data.current_epoch || 0;
    const totalEpochs = data.total_epochs || 0;
    const currentStep = data.current_step || 0;
    const totalSteps = data.total_steps || 0;
    const eta = data.eta || '--';
    
    // 更新进度条
    document.getElementById('progress-bar').style.width = `${percentage}%`;
    document.getElementById('progress-percentage').textContent = `${percentage.toFixed(1)}%`;
    
    // 更新步骤信息
    document.getElementById('current-step').textContent = 
        `Epoch ${currentEpoch}/${totalEpochs} - Step ${currentStep}/${totalSteps}`;
    
    // 更新预计剩余时间
    document.getElementById('eta').textContent = `预计剩余: ${eta}`;
}

// ==================== Loss 图表 ====================

function initLossChart() {
    const ctx = document.getElementById('loss-chart');
    if (!ctx) return;
    
    lossChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Training Loss',
                data: [],
                borderColor: '#165DFF',
                backgroundColor: 'rgba(22, 93, 255, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Step'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Loss'
                    },
                    beginAtZero: false
                }
            }
        }
    });
}

function updateLossChart(step, loss) {
    if (!lossChart) return;
    
    lossData.push({ step, loss });
    
    // 只保留最近 100 个数据点
    if (lossData.length > 100) {
        lossData.shift();
    }
    
    lossChart.data.labels = lossData.map(d => d.step);
    lossChart.data.datasets[0].data = lossData.map(d => d.loss);
    lossChart.update('none'); // 'none' 模式避免动画，提高性能
}

// ==================== 日志输出 ====================

function addLog(message, level = 'info') {
    const logsContainer = document.getElementById('training-logs');
    if (!logsContainer) return;
    
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    
    const timestamp = new Date().toLocaleTimeString();
    let color = 'text-green-400';
    
    if (level === 'error') {
        color = 'text-red-400';
    } else if (level === 'warning') {
        color = 'text-yellow-400';
    }
    
    logEntry.innerHTML = `<span class="text-gray-500">[${timestamp}]</span> <span class="${color}">${escapeHtml(message)}</span>`;
    
    logsContainer.appendChild(logEntry);
    
    // 自动滚动到底部
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

// ==================== 训练完成/错误处理 ====================

function handleTrainingCompleted(data) {
    addLog('训练完成！', 'info');
    document.getElementById('cancel-training-btn').disabled = true;
    
    showMessage('LoRA 训练已完成！', 'success');
    
    // 3秒后跳转到模型管理页面
    setTimeout(() => {
        window.location.href = 'model-management.html';
    }, 3000);
}

function handleTrainingError(data) {
    const errorMessage = data.error || '训练过程中发生错误';
    addLog(`错误: ${errorMessage}`, 'error');
    
    document.getElementById('cancel-training-btn').disabled = true;
    
    // 检查是否是 OOM 错误
    if (errorMessage.toLowerCase().includes('out of memory') || 
        errorMessage.toLowerCase().includes('oom')) {
        showMessage(
            '显存不足！建议使用 QLoRA 模式或减小 batch_size',
            'error'
        );
    } else {
        showMessage(`训练失败: ${errorMessage}`, 'error');
    }
    
    // 显示返回配置的按钮
    setTimeout(() => {
        if (confirm('训练失败，是否返回配置页面重新设置？')) {
            window.location.reload();
        }
    }, 2000);
}

function handleTrainingCancelled() {
    addLog('训练已取消', 'warning');
    showMessage('训练已取消', 'warning');
    
    setTimeout(() => {
        window.location.href = 'model-management.html';
    }, 2000);
}

// ==================== 取消训练 ====================

async function cancelTraining() {
    if (!confirm('确定要取消训练吗？已训练的进度将会丢失。')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/api/lora/training-jobs/${currentJobId}/cancel`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('取消训练失败');
        }
        
        document.getElementById('cancel-training-btn').disabled = true;
        addLog('正在取消训练...', 'warning');
        
    } catch (error) {
        showMessage('取消训练失败: ' + error.message, 'error');
    }
}

// ==================== 工具函数 ====================

function showMessage(message, type = 'info') {
    showToast(message, type);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// formatDateTime 和 showToast 函数由 common.js 提供
