// Agent 交互界面 JavaScript

class AgentChat {
    constructor() {
        this.apiUrl = 'http://localhost:8000/api/agent';
        this.sessionId = this.generateSessionId();
        this.init();
    }

    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    init() {
        this.setupEventListeners();
        this.loadTools();
    }

    setupEventListeners() {
        const sendBtn = document.getElementById('send-agent-query');
        const queryInput = document.getElementById('agent-query-input');

        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendQuery());
        }

        if (queryInput) {
            queryInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendQuery();
                }
            });
        }

        // 示例问题点击
        document.querySelectorAll('.example-question').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const question = e.target.textContent;
                document.getElementById('agent-query-input').value = question;
                this.sendQuery();
            });
        });
    }

    async loadTools() {
        try {
            const response = await fetch(`${this.apiUrl}/tools`);
            if (!response.ok) throw new Error('获取工具列表失败');
            
            const tools = await response.json();
            this.displayTools(tools);
        } catch (error) {
            console.error('加载工具失败:', error);
        }
    }

    displayTools(tools) {
        const container = document.getElementById('tools-list');
        if (!container) return;

        container.innerHTML = tools.map(tool => `
            <div class="bg-gray-50 rounded-lg p-4 border border-gray-200">
                <div class="flex items-center mb-2">
                    <i class="fa fa-wrench text-primary mr-2"></i>
                    <h4 class="font-bold">${tool.name}</h4>
                </div>
                <p class="text-sm text-gray-600">${tool.description}</p>
            </div>
        `).join('');
    }

    async sendQuery() {
        const queryInput = document.getElementById('agent-query-input');
        const query = queryInput.value.trim();

        if (!query) {
            this.showError('请输入问题');
            return;
        }

        // 清空输入框
        queryInput.value = '';

        // 添加用户消息到界面
        this.addMessage('user', query);

        // 显示思考中状态
        const thinkingId = this.addThinking();

        try {
            const response = await fetch(`${this.apiUrl}/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    session_id: this.sessionId,
                    max_iterations: 5
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();

            // 移除思考状态
            this.removeThinking(thinkingId);

            // 显示执行步骤
            this.displaySteps(result.steps);

            // 显示最终答案
            this.addMessage('agent', result.answer, result.success);

            // 显示统计信息
            this.showStats(result.iterations, result.steps.length);

        } catch (error) {
            console.error('Agent 查询失败:', error);
            this.removeThinking(thinkingId);
            this.showError('查询失败: ' + error.message);
        }
    }

    addMessage(role, content, success = true) {
        const chatBox = document.getElementById('agent-chat-box');
        if (!chatBox) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `mb-4 ${role === 'user' ? 'text-right' : 'text-left'}`;

        const bubble = document.createElement('div');
        bubble.className = `inline-block max-w-[80%] p-4 rounded-lg ${
            role === 'user' 
                ? 'bg-primary text-white' 
                : success 
                    ? 'bg-white border border-gray-200' 
                    : 'bg-red-50 border border-red-200'
        }`;

        // 处理 Markdown 和换行
        bubble.innerHTML = this.formatMessage(content);

        messageDiv.appendChild(bubble);
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    addThinking() {
        const chatBox = document.getElementById('agent-chat-box');
        if (!chatBox) return null;

        const thinkingDiv = document.createElement('div');
        const thinkingId = 'thinking-' + Date.now();
        thinkingDiv.id = thinkingId;
        thinkingDiv.className = 'mb-4 text-left';

        thinkingDiv.innerHTML = `
            <div class="inline-block max-w-[80%] p-4 rounded-lg bg-blue-50 border border-blue-200">
                <div class="flex items-center">
                    <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-primary mr-3"></div>
                    <span class="text-sm text-gray-600">Agent 正在思考...</span>
                </div>
            </div>
        `;

        chatBox.appendChild(thinkingDiv);
        chatBox.scrollTop = chatBox.scrollHeight;

        return thinkingId;
    }

    removeThinking(thinkingId) {
        if (!thinkingId) return;
        const element = document.getElementById(thinkingId);
        if (element) element.remove();
    }

    displaySteps(steps) {
        const chatBox = document.getElementById('agent-chat-box');
        if (!chatBox || !steps.length) return;

        const stepsDiv = document.createElement('div');
        stepsDiv.className = 'mb-4 text-left';

        const stepsContainer = document.createElement('div');
        stepsContainer.className = 'inline-block max-w-[80%] bg-gray-50 border border-gray-200 rounded-lg p-4';

        stepsContainer.innerHTML = `
            <div class="flex items-center mb-3">
                <i class="fa fa-tasks text-gray-600 mr-2"></i>
                <span class="font-bold text-sm text-gray-700">执行步骤</span>
            </div>
            <div class="space-y-2">
                ${steps.map((step, index) => this.formatStep(step, index + 1)).join('')}
            </div>
        `;

        stepsDiv.appendChild(stepsContainer);
        chatBox.appendChild(stepsDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    formatStep(step, index) {
        const icons = {
            thought: 'fa-lightbulb-o',
            action: 'fa-play',
            observation: 'fa-eye',
            final_answer: 'fa-check',
            error: 'fa-exclamation-triangle'
        };

        const colors = {
            thought: 'text-yellow-600',
            action: 'text-blue-600',
            observation: 'text-green-600',
            final_answer: 'text-primary',
            error: 'text-red-600'
        };

        const icon = icons[step.type] || 'fa-circle';
        const color = colors[step.type] || 'text-gray-600';

        let content = '';
        if (step.type === 'action') {
            content = `<strong>工具:</strong> ${step.tool}<br><strong>参数:</strong> <code class="text-xs">${step.input}</code>`;
        } else {
            content = step.content || '';
        }

        return `
            <div class="flex items-start text-sm">
                <i class="fa ${icon} ${color} mr-2 mt-1"></i>
                <div class="flex-1">
                    <span class="font-medium text-gray-700">${this.getStepLabel(step.type)}</span>
                    <div class="text-gray-600 text-xs mt-1">${content}</div>
                </div>
            </div>
        `;
    }

    getStepLabel(type) {
        const labels = {
            thought: '思考',
            action: '执行工具',
            observation: '观察结果',
            final_answer: '最终答案',
            error: '错误'
        };
        return labels[type] || type;
    }

    formatMessage(text) {
        // 简单的格式化
        return text
            .replace(/\n/g, '<br>')
            .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm">$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/\*([^*]+)\*/g, '<em>$1</em>');
    }

    showStats(iterations, steps) {
        const statsDiv = document.getElementById('agent-stats');
        if (!statsDiv) return;

        statsDiv.innerHTML = `
            <div class="flex items-center justify-center space-x-6 text-sm text-gray-600">
                <div class="flex items-center">
                    <i class="fa fa-refresh mr-2"></i>
                    <span>迭代次数: ${iterations}</span>
                </div>
                <div class="flex items-center">
                    <i class="fa fa-list mr-2"></i>
                    <span>执行步骤: ${steps}</span>
                </div>
            </div>
        `;
    }

    showError(message) {
        const chatBox = document.getElementById('agent-chat-box');
        if (!chatBox) {
            alert(message);
            return;
        }

        const errorDiv = document.createElement('div');
        errorDiv.className = 'mb-4 text-center';
        errorDiv.innerHTML = `
            <div class="inline-block px-4 py-2 rounded-lg bg-red-50 text-red-600 border border-red-200">
                <i class="fa fa-exclamation-circle mr-2"></i>
                ${message}
            </div>
        `;

        chatBox.appendChild(errorDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    const agentChat = new AgentChat();
});
