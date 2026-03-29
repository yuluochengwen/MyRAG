// Agent 工作台 JavaScript

class AgentChat {
    constructor() {
        const cfg = window.APP_CONFIG || {};
        this.apiUrl = cfg.buildAgentUrl ? cfg.buildAgentUrl("").replace(/\/$/, "") : "/api/agent";
        this.kbApiUrl = cfg.buildUrl ? cfg.buildUrl("/api/knowledge-bases") : "/api/knowledge-bases";
        this.storageKey = "agent_workbench_sessions_v1";
        this.activeSessionIdKey = "agent_workbench_active_session_id_v1";
        this.settingsKey = "agent_workbench_settings_v1";
        this.defaultModel = "qwen2.5:7b";
        this.preferredModel = this.defaultModel;
        this.preferredKbIds = [];
        this.sessions = [];
        this.activeSessionId = null;
        this.lastQuery = "";
        this.isPending = false;
        this.init();
    }

    init() {
        this.loadSessions();
        this.setupEventListeners();
        this.loadRuntimeSettings();
        this.loadKnowledgeBases();
        this.loadModels();
        this.loadTools();
        this.ensureActiveSession();
        this.renderSessionList();
        this.renderCurrentSessionMessages();
    }

    generateSessionId() {
        return "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 11);
    }

    getSessionById(sessionId) {
        return this.sessions.find((item) => item.id === sessionId) || null;
    }

    getActiveSession() {
        return this.getSessionById(this.activeSessionId);
    }

    createSession(initialTitle = "新会话") {
        const now = new Date().toISOString();
        const session = {
            id: this.generateSessionId(),
            title: initialTitle,
            createdAt: now,
            updatedAt: now,
            messages: [],
            lastStats: null
        };
        this.sessions.unshift(session);
        this.activeSessionId = session.id;
        this.saveSessions();
        this.renderSessionList();
        this.renderCurrentSessionMessages();
        this.updateStatusHint("已创建新会话");
        return session;
    }

    ensureActiveSession() {
        if (!this.sessions.length) {
            this.createSession();
            return;
        }

        if (!this.activeSessionId || !this.getSessionById(this.activeSessionId)) {
            this.activeSessionId = this.sessions[0].id;
        }
    }

    saveSessions() {
        localStorage.setItem(this.storageKey, JSON.stringify(this.sessions));
        if (this.activeSessionId) {
            localStorage.setItem(this.activeSessionIdKey, this.activeSessionId);
        }
    }

    loadSessions() {
        try {
            const sessionRaw = localStorage.getItem(this.storageKey);
            this.sessions = sessionRaw ? JSON.parse(sessionRaw) : [];
        } catch (error) {
            console.error("会话解析失败:", error);
            this.sessions = [];
        }
        this.activeSessionId = localStorage.getItem(this.activeSessionIdKey);
    }

    setupEventListeners() {
        const sendBtn = document.getElementById("send-agent-query");
        const queryInput = document.getElementById("agent-query-input");
        const newSessionBtn = document.getElementById("new-agent-session");
        const clearSessionBtn = document.getElementById("clear-agent-session");
        const newSessionMainBtn = document.getElementById("new-agent-session-main");
        const modelNode = document.getElementById("agent-model");
        const maxIterationsNode = document.getElementById("agent-max-iterations");
        const temperatureNode = document.getElementById("agent-temperature");
        const showStepsNode = document.getElementById("agent-show-steps");

        if (sendBtn) {
            sendBtn.addEventListener("click", () => this.sendQuery());
        }

        if (queryInput) {
            queryInput.addEventListener("keypress", (event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    this.sendQuery();
                }
            });
        }

        if (newSessionBtn) {
            newSessionBtn.addEventListener("click", () => this.createSession());
        }



        if (clearSessionBtn) {
            clearSessionBtn.addEventListener("click", () => {
                const session = this.getActiveSession();
                if (!session) {
                    return;
                }
                session.messages = [];
                session.lastStats = null;
                session.updatedAt = new Date().toISOString();
                this.saveSessions();
                this.renderCurrentSessionMessages();
                this.updateStatusHint("当前会话已清空");
            });
        }



        [modelNode, maxIterationsNode, temperatureNode, showStepsNode].forEach((node) => {
            node?.addEventListener("change", () => this.saveRuntimeSettings());
        });

        this.setupKbDropdownEvents();

        modelNode?.addEventListener("change", () => {
            const value = (modelNode.value || "").trim();
            if (value) {
                this.preferredModel = value;
            }
        });
    }

    setupKbDropdownEvents() {
        const wrapper = document.getElementById("agent-kb-dropdown");
        const toggle = document.getElementById("agent-kb-dropdown-toggle");
        const menu = document.getElementById("agent-kb-dropdown-menu");
        const selectAllNode = document.getElementById("agent-kb-select-all");
        const optionsContainer = document.getElementById("agent-kb-options");
        if (!wrapper || !toggle || !menu || !selectAllNode || !optionsContainer) return;

        toggle.addEventListener("click", (event) => {
            event.preventDefault();
            menu.classList.toggle("hidden");
        });

        selectAllNode.addEventListener("change", () => {
            if (selectAllNode.checked) {
                optionsContainer.querySelectorAll('input[type="checkbox"]').forEach((node) => {
                    node.checked = false;
                });
            }
            this.updateKbDropdownLabel();
            this.saveRuntimeSettings();
        });

        optionsContainer.addEventListener("change", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLInputElement)) {
                return;
            }

            if (target.checked) {
                selectAllNode.checked = false;
            }

            this.syncKbSelectAllState();
            this.updateKbDropdownLabel();
            this.saveRuntimeSettings();
        });

        document.addEventListener("click", (event) => {
            if (!wrapper.contains(event.target)) {
                menu.classList.add("hidden");
            }
        });
    }

    getSelectedKbIds() {
        const optionsContainer = document.getElementById("agent-kb-options");
        if (!optionsContainer) return [];

        return [...optionsContainer.querySelectorAll('input[type="checkbox"]:checked')]
            .map((node) => Number(node.getAttribute("data-kb-id")))
            .filter((v) => Number.isInteger(v) && v > 0);
    }

    syncKbSelectAllState() {
        const selectAllNode = document.getElementById("agent-kb-select-all");
        if (!selectAllNode) return;

        const selectedCount = this.getSelectedKbIds().length;
        if (selectedCount === 0) {
            selectAllNode.checked = true;
        }
    }

    updateKbDropdownLabel() {
        const labelNode = document.getElementById("agent-kb-dropdown-label");
        const selectAllNode = document.getElementById("agent-kb-select-all");
        if (!labelNode || !selectAllNode) return;

        const selectedCount = this.getSelectedKbIds().length;
        if (selectAllNode.checked || selectedCount === 0) {
            labelNode.textContent = "全部知识库";
            return;
        }

        labelNode.textContent = `已选 ${selectedCount} 个知识库`;
    }

    loadRuntimeSettings() {
        const modelNode = document.getElementById("agent-model");
        const maxIterationsNode = document.getElementById("agent-max-iterations");
        const temperatureNode = document.getElementById("agent-temperature");
        const showStepsNode = document.getElementById("agent-show-steps");

        try {
            const raw = localStorage.getItem(this.settingsKey);
            const settings = raw ? JSON.parse(raw) : {};
            if (maxIterationsNode && Number.isFinite(Number(settings.max_iterations))) {
                maxIterationsNode.value = String(settings.max_iterations);
            }
            if (temperatureNode && Number.isFinite(Number(settings.temperature))) {
                temperatureNode.value = String(settings.temperature);
            }
            if (showStepsNode && typeof settings.show_steps === "boolean") {
                showStepsNode.checked = settings.show_steps;
            }
            if (modelNode && typeof settings.llm_model === "string" && settings.llm_model.trim()) {
                this.preferredModel = settings.llm_model.trim();
                if ([...modelNode.options].some((option) => option.value === this.preferredModel)) {
                    modelNode.value = this.preferredModel;
                }
            }
            if (Array.isArray(settings.kb_ids)) {
                this.preferredKbIds = settings.kb_ids
                    .map((v) => Number(v))
                    .filter((v) => Number.isInteger(v) && v > 0);
            }
        } catch (error) {
            console.error("配置加载失败:", error);
        }
    }

    async loadKnowledgeBases() {
        const optionsContainer = document.getElementById("agent-kb-options");
        const selectAllNode = document.getElementById("agent-kb-select-all");
        if (!optionsContainer || !selectAllNode) return;

        const selectedSet = new Set((this.preferredKbIds || []).map((id) => Number(id)));
        const setFallback = () => {
            optionsContainer.innerHTML = "";
            this.preferredKbIds.forEach((id) => {
                const item = document.createElement("label");
                item.className = "flex items-center px-2 py-1 rounded hover:bg-gray-50 text-sm text-gray-700";
                item.innerHTML = `<input type="checkbox" class="mr-2" data-kb-id="${id}" checked>知识库 #${id} (ID: ${id})`;
                optionsContainer.appendChild(item);
            });
            selectAllNode.checked = this.preferredKbIds.length === 0;
            this.updateKbDropdownLabel();
        };

        try {
            const response = await fetch(this.kbApiUrl);
            if (!response.ok) throw new Error("获取知识库列表失败");

            const kbs = await response.json();
            if (!Array.isArray(kbs) || !kbs.length) {
                optionsContainer.innerHTML = "<div class=\"px-2 py-2 text-xs text-gray-500\">暂无知识库</div>";
                selectAllNode.checked = true;
                this.updateKbDropdownLabel();
                return;
            }

            optionsContainer.innerHTML = kbs
                .map((kb) => {
                    const id = Number(kb?.id);
                    const name = String(kb?.name || "").trim() || `知识库 #${id}`;
                    const checked = selectedSet.has(id) ? " checked" : "";
                    return `<label class="flex items-center px-2 py-1 rounded hover:bg-gray-50 text-sm text-gray-700"><input type="checkbox" class="mr-2" data-kb-id="${id}"${checked}>${this.escapeHtml(name)} (ID: ${id})</label>`;
                })
                .join("");

            // 保存当前选中的知识库ID
            this.preferredKbIds = [...selectedSet];
            this.saveRuntimeSettings();

            selectAllNode.checked = selectedSet.size === 0;
            this.syncKbSelectAllState();
            this.updateKbDropdownLabel();
            this.saveRuntimeSettings();
        } catch (error) {
            console.error("加载知识库列表失败:", error);
            setFallback();
        }
    }

    saveRuntimeSettings() {
        const options = this.getRequestOptions();
        try {
            // 确保保存preferredKbIds
            const settingsToSave = {
                ...options,
                kb_ids: options.kb_ids || this.preferredKbIds.length > 0 ? this.preferredKbIds : null
            };
            localStorage.setItem(this.settingsKey, JSON.stringify(settingsToSave));
        } catch (error) {
            console.error("配置保存失败:", error);
        }
    }

    switchSession(sessionId) {
        if (this.activeSessionId === sessionId) {
            return;
        }
        if (!this.getSessionById(sessionId)) {
            return;
        }
        this.activeSessionId = sessionId;
        this.saveSessions();
        this.renderSessionList();
        this.renderCurrentSessionMessages();
    }

    deleteSession(sessionId) {
        if (!sessionId) return;
        
        // 确认删除
        if (!confirm('确定要删除这个会话吗？')) {
            return;
        }
        
        // 从会话列表中移除
        const sessionIndex = this.sessions.findIndex(session => session.id === sessionId);
        if (sessionIndex === -1) return;
        
        this.sessions.splice(sessionIndex, 1);
        
        // 如果删除的是当前活动会话，切换到另一个会话
        if (this.activeSessionId === sessionId) {
            if (this.sessions.length > 0) {
                this.activeSessionId = this.sessions[0].id;
            } else {
                this.activeSessionId = null;
                this.createSession();
            }
        }
        
        // 保存并重新渲染
        this.saveSessions();
        this.renderSessionList();
        this.renderCurrentSessionMessages();
        this.updateStatusHint('会话已删除');
    }

    renderSessionList() {
        const container = document.getElementById("agent-session-list");
        if (!container) return;

        if (!this.sessions.length) {
            container.innerHTML = '<div class="text-xs text-gray-500">暂无会话</div>';
            return;
        }

        container.innerHTML = this.sessions
            .map((session) => {
                const activeClass = session.id === this.activeSessionId ? "session-item-active" : "";
                const timeText = this.formatRelativeTime(session.updatedAt);
                return `
                    <div class="agent-session-item w-full p-2 rounded border border-gray-200 hover:border-primary transition ${activeClass}" data-session-id="${session.id}">
                        <div class="flex justify-between items-start">
                            <button class="flex-1 text-left">
                                <div class="text-sm font-medium text-gray-800 truncate">${this.escapeHtml(session.title)}</div>
                                <div class="text-xs text-gray-500 mt-1">${timeText}</div>
                            </button>
                            <button class="agent-session-delete p-1 text-gray-400 hover:text-red-500 transition" data-session-id="${session.id}">
                                <i class="fa fa-trash-o"></i>
                            </button>
                        </div>
                    </div>
                `;
            })
            .join("");

        // 切换会话事件
        container.querySelectorAll(".agent-session-item button:not(.agent-session-delete)").forEach((btn) => {
            btn.addEventListener("click", () => {
                const sessionId = btn.closest(".agent-session-item").getAttribute("data-session-id");
                if (sessionId) {
                    this.switchSession(sessionId);
                }
            });
        });

        // 删除会话事件
        container.querySelectorAll(".agent-session-delete").forEach((btn) => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation(); // 阻止事件冒泡
                const sessionId = btn.getAttribute("data-session-id");
                if (sessionId) {
                    this.deleteSession(sessionId);
                }
            });
        });
    }

    renderCurrentSessionMessages() {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox) return;

        const session = this.getActiveSession();
        chatBox.innerHTML = "";

        if (!session || !session.messages.length) {
            this.renderWelcome(chatBox);
            this.showStats(0, 0, 0);
            return;
        }

        session.messages.forEach((message) => {
            if (message.kind === "steps") {
                this.displaySteps(message.steps, false);
                return;
            }
            this.addMessage(message.role, message.content, message.success, false);
        });

        if (session.lastStats) {
            this.showStats(session.lastStats.iterations, session.lastStats.steps, session.lastStats.durationMs);
        }
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    renderWelcome(chatBox) {
        chatBox.innerHTML = `
            <div class="text-center mb-8">
              <div class="w-16 h-16 rounded-full bg-gradient-to-r from-primary to-secondary flex items-center justify-center mx-auto mb-4">
                <i class="fa fa-robot text-white text-2xl"></i>
              </div>
              <h3 class="text-xl font-bold mb-2">你好！我是 RAG Agent</h3>
              <p class="text-gray-600 text-sm max-w-md mx-auto">我可以帮你搜索知识库、执行计算和任务分解。请选择一个示例问题开始。</p>
            </div>
        `;
    }

    getRequestOptions() {
        const maxIterationsNode = document.getElementById("agent-max-iterations");
        const temperatureNode = document.getElementById("agent-temperature");
        const modelNode = document.getElementById("agent-model");
        const selectAllNode = document.getElementById("agent-kb-select-all");
        const showStepsNode = document.getElementById("agent-show-steps");

        const maxIterations = Math.max(1, Math.min(10, Number(maxIterationsNode?.value || 5)));
        const temperature = Math.max(0, Math.min(1, Number(temperatureNode?.value || 0.1)));

        const kbIds = this.getSelectedKbIds();
        
        // 保存当前选中的知识库ID
        if (selectAllNode?.checked || !kbIds.length) {
            this.preferredKbIds = [];
        } else {
            this.preferredKbIds = [...new Set(kbIds)];
        }

        return {
            max_iterations: maxIterations,
            temperature,
            llm_model: (modelNode?.value || "").trim() || null,
            kb_ids: selectAllNode?.checked || !kbIds.length ? null : [...new Set(kbIds)],
            show_steps: Boolean(showStepsNode?.checked)
        };
    }

    async loadModels() {
        const modelNode = document.getElementById("agent-model");
        if (!modelNode) return;

        const preferredModel = (this.preferredModel || modelNode.value || this.defaultModel).trim();
        const setFallback = () => {
            modelNode.innerHTML = `<option value="${this.escapeHtml(preferredModel)}">${this.escapeHtml(preferredModel)}</option>`;
            modelNode.value = preferredModel;
            this.preferredModel = preferredModel;
            this.saveRuntimeSettings();
        };

        try {
            const response = await fetch(`${this.apiUrl}/models`);
            if (!response.ok) throw new Error("获取模型列表失败");

            const models = await response.json();
            if (!Array.isArray(models) || !models.length) {
                setFallback();
                return;
            }

            const uniqueNames = [];
            models.forEach((item) => {
                const name = String(item?.name || "").trim();
                if (!name || uniqueNames.includes(name)) return;
                uniqueNames.push(name);
            });

            if (!uniqueNames.length) {
                setFallback();
                return;
            }

            if (!uniqueNames.includes(preferredModel)) {
                uniqueNames.unshift(preferredModel);
            }

            modelNode.innerHTML = uniqueNames
                .map((name) => `<option value="${this.escapeHtml(name)}">${this.escapeHtml(name)}</option>`)
                .join("");

            modelNode.value = preferredModel;
            this.preferredModel = preferredModel;
            this.saveRuntimeSettings();
        } catch (error) {
            console.error("加载模型失败:", error);
            setFallback();
        }
    }

    async loadTools() {
        const container = document.getElementById("tools-list");
        try {
            const response = await fetch(`${this.apiUrl}/tools`);
            if (!response.ok) throw new Error("获取工具列表失败");

            const tools = await response.json();
            this.displayTools(tools);
        } catch (error) {
            console.error("加载工具失败:", error);
            if (container) {
                container.innerHTML = `<div class="text-sm text-red-600">工具加载失败: ${this.escapeHtml(error.message)}</div>`;
            }
        }
    }

    displayTools(tools) {
        const container = document.getElementById("tools-list");
        if (!container) return;

        container.innerHTML = tools
            .map(
                (tool) => `
            <button type="button" class="agent-tool-item w-full text-left bg-gray-50 rounded-lg p-3 border border-gray-200 hover:border-primary hover:bg-blue-50 transition" data-tool-name="${this.escapeHtml(tool.name)}">
                <div class="flex items-center mb-1">
                    <i class="fa fa-wrench text-primary mr-2"></i>
                    <h4 class="font-bold text-sm">${this.escapeHtml(tool.name)}</h4>
                </div>
                <p class="text-xs text-gray-600">${this.escapeHtml(tool.description || "")}</p>
            </button>
        `
            )
            .join("");

        container.querySelectorAll(".agent-tool-item").forEach((btn) => {
            btn.addEventListener("click", () => {
                const toolName = (btn.getAttribute("data-tool-name") || "").trim();
                this.applyToolTemplate(toolName);
            });
        });
    }

    applyToolTemplate(toolName) {
        const input = document.getElementById("agent-query-input");
        if (!input) return;

        const templates = {
            get_current_time: "现在是什么时间？请返回精确到秒。",
            calculator: "请计算 (123 + 456) * 789",
            search_knowledge_base: "请搜索知识库中关于 RAG 的内容并做简要总结"
        };

        input.value = templates[toolName] || `请使用工具 ${toolName} 处理我的问题`;
        input.focus();
        this.updateStatusHint(`已选择工具: ${toolName}，可直接发送`);
    }

    setPending(pending) {
        this.isPending = pending;
        const sendBtn = document.getElementById("send-agent-query");
        const input = document.getElementById("agent-query-input");
        if (sendBtn) {
            sendBtn.disabled = pending;
            sendBtn.classList.toggle("opacity-60", pending);
            sendBtn.classList.toggle("cursor-not-allowed", pending);
        }
        if (input) {
            input.disabled = pending;
        }
    }

    async sendQuery() {
        if (this.isPending) {
            return;
        }

        const queryInput = document.getElementById("agent-query-input");
        const query = (queryInput?.value || "").trim();

        if (!query) {
            this.showError("请输入问题");
            return;
        }

        const session = this.getActiveSession() || this.createSession();
        this.lastQuery = query;
        this.setPending(true);
        this.updateStatusHint("请求已发送，正在等待 Agent 响应...");

        if (queryInput) {
            queryInput.value = "";
        }

        this.addMessage("user", query, true);
        this.pushMessageToSession(session, { role: "user", content: query, success: true });

        const thinkingId = this.addThinking();
        const startTime = Date.now();
        const streamedSteps = [];
        let finalResult = null;
        let liveStepsList = null;

        try {
            const options = this.getRequestOptions();
            const response = await fetch(`${this.apiUrl}/query/stream`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    query,
                    session_id: session.id,
                    kb_ids: options.kb_ids,
                    max_iterations: options.max_iterations,
                    temperature: options.temperature,
                    llm_model: options.llm_model,
                    show_steps: options.show_steps
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error("当前环境不支持流式响应");
            }

            if (options.show_steps) {
                liveStepsList = this.createLiveStepsPanel();
            }

            this.removeThinking(thinkingId);
            await this.consumeSseStream(response, (event) => {
                const eventType = String(event?.type || "");
                const eventData = event?.data;

                if (eventType === "step" && eventData) {
                    streamedSteps.push(eventData);
                    if (options.show_steps && liveStepsList) {
                        this.appendLiveStep(liveStepsList, eventData);
                    }
                    return;
                }

                if (eventType === "final" && eventData) {
                    finalResult = eventData;
                    return;
                }

                if (eventType === "error") {
                    const msg = eventData?.error || "流式请求失败";
                    throw new Error(msg);
                }
            });

            const durationMs = Date.now() - startTime;
            const result = finalResult || {
                answer: "(空响应)",
                success: false,
                iterations: 0,
                steps: streamedSteps
            };

            if (options.llm_model) {
                this.preferredModel = options.llm_model;
                this.saveRuntimeSettings();
            }

            if (options.show_steps) {
                this.pushMessageToSession(session, { kind: "steps", steps: streamedSteps });
            }

            this.addMessage("agent", result.answer || "(空响应)", Boolean(result.success));
            this.pushMessageToSession(session, {
                role: "agent",
                content: result.answer || "(空响应)",
                success: Boolean(result.success)
            });

            this.showStats(result.iterations || 0, (result.steps || []).length, durationMs);
            session.lastStats = {
                iterations: result.iterations || 0,
                steps: streamedSteps.length,
                durationMs
            };
            if (session.title === "新会话") {
                session.title = query.slice(0, 16);
            }
            session.updatedAt = new Date().toISOString();
            this.saveSessions();
            this.renderSessionList();
            const usedModelText = options.llm_model || this.defaultModel;
            this.updateStatusHint(`响应完成（模型: ${usedModelText}）`);
        } catch (error) {
            console.error("Agent 查询失败:", error);
            this.removeThinking(thinkingId);
            this.showError(`查询失败: ${error.message}`);
            this.updateStatusHint("请求失败，可直接重新发送");
        } finally {
            this.setPending(false);
        }
    }

    async consumeSseStream(response, onEvent) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split("\n\n");
            buffer = chunks.pop() || "";

            chunks.forEach((chunk) => {
                const lines = chunk
                    .split("\n")
                    .map((line) => line.trim())
                    .filter((line) => line.startsWith("data:"));

                if (!lines.length) return;

                const payloadText = lines.map((line) => line.slice(5).trim()).join("\n");
                if (!payloadText) return;

                try {
                    const payload = JSON.parse(payloadText);
                    onEvent(payload);
                } catch (error) {
                    if (error instanceof SyntaxError) {
                        console.warn("SSE 数据解析失败:", error, payloadText);
                        return;
                    }
                    throw error;
                }
            });
        }
    }

    createLiveStepsPanel() {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox) return null;

        const wrapper = document.createElement("div");
        wrapper.className = "mb-4 flex justify-start items-start";

        const card = document.createElement("div");
        card.className = "flex items-start max-w-[80%]";
        card.innerHTML = `
            <div class="w-10 h-10 rounded-full gradient-bg flex items-center justify-center mr-3 flex-shrink-0 shadow-sm">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
            </div>
            <div class="inline-block max-w-[calc(100%-40px)] bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div class="flex items-center mb-3">
                    <i class="fa fa-tasks text-gray-600 mr-2"></i>
                    <span class="font-bold text-sm text-gray-700">执行步骤（实时）</span>
                </div>
                <div class="space-y-2"></div>
            </div>
        `;

        const stepsList = card.querySelector(".space-y-2");
        wrapper.appendChild(card);
        chatBox.appendChild(wrapper);
        chatBox.scrollTop = chatBox.scrollHeight;
        return stepsList;
    }

    appendLiveStep(stepsList, step) {
        if (!stepsList) return;
        const stepNode = document.createElement("div");
        stepNode.className = "text-sm";
        stepNode.innerHTML = this.formatStep(step);
        stepsList.appendChild(stepNode);

        const chatBox = document.getElementById("agent-chat-box");
        if (chatBox) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    pushMessageToSession(session, message) {
        if (!session) return;
        const withTs = {
            ...message,
            timestamp: new Date().toISOString()
        };
        session.messages.push(withTs);
        session.updatedAt = withTs.timestamp;
        this.saveSessions();
    }

    addMessage(role, content, success = true, scroll = true) {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox) return;

        const messageDiv = document.createElement("div");
        messageDiv.className = `mb-4 flex ${role === "user" ? "justify-end" : "justify-start"} items-start`;

        // 添加头像
        if (role === "user") {
            // 用户消息：头像在右侧
            const bubbleWrapper = document.createElement("div");
            bubbleWrapper.className = "flex items-start max-w-[80%]";
            
            const bubble = document.createElement("div");
            bubble.className = "inline-block max-w-[calc(100%-40px)] p-4 rounded-lg bg-primary text-white";
            bubble.innerHTML = this.formatMessage(content);
            
            const avatar = document.createElement("div");
            avatar.className = "w-10 h-10 rounded-full bg-gray-300 flex items-center justify-center ml-3 flex-shrink-0";
            // 使用内联SVG图标作为备用
            avatar.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>`;
            
            bubbleWrapper.appendChild(bubble);
            bubbleWrapper.appendChild(avatar);
            messageDiv.appendChild(bubbleWrapper);
        } else {
            // Agent消息：头像在左侧
            const bubbleWrapper = document.createElement("div");
            bubbleWrapper.className = "flex items-start max-w-[80%]";
            
            const avatar = document.createElement("div");
            avatar.className = "w-10 h-10 rounded-full gradient-bg flex items-center justify-center mr-3 flex-shrink-0 shadow-sm";
            // 使用内联SVG图标作为备用
            avatar.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
            </svg>`;
            
            const bubble = document.createElement("div");
            bubble.className = `inline-block max-w-[calc(100%-40px)] p-4 rounded-lg ${
                success ? "bg-white border border-gray-200" : "bg-red-50 border border-red-200"
            }`;
            bubble.innerHTML = this.formatMessage(content);
            
            bubbleWrapper.appendChild(avatar);
            bubbleWrapper.appendChild(bubble);
            messageDiv.appendChild(bubbleWrapper);
        }

        chatBox.appendChild(messageDiv);

        if (scroll) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    addThinking() {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox) return null;

        const thinkingDiv = document.createElement("div");
        const thinkingId = "thinking-" + Date.now();
        thinkingDiv.id = thinkingId;
        thinkingDiv.className = "mb-4 flex justify-start items-start";

        thinkingDiv.innerHTML = `
            <div class="flex items-start max-w-[80%]">
                <div class="w-10 h-10 rounded-full gradient-bg flex items-center justify-center mr-3 flex-shrink-0 shadow-sm">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                    </svg>
                </div>
                <div class="inline-block max-w-[calc(100%-40px)] p-4 rounded-lg bg-blue-50 border border-blue-200">
                    <div class="flex items-center">
                        <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-primary mr-3"></div>
                        <span class="text-sm text-gray-600">Agent 正在思考...</span>
                    </div>
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
        if (element) {
            element.remove();
        }
    }

    displaySteps(steps, scroll = true) {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox || !Array.isArray(steps) || !steps.length) return;

        const stepsDiv = document.createElement("div");
        stepsDiv.className = "mb-4 flex justify-start items-start";

        const stepsContainer = document.createElement("div");
        stepsContainer.className = "flex items-start max-w-[80%]";

        stepsContainer.innerHTML = `
            <div class="w-10 h-10 rounded-full gradient-bg flex items-center justify-center mr-3 flex-shrink-0 shadow-sm">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                </svg>
            </div>
            <div class="inline-block max-w-[calc(100%-40px)] bg-gray-50 border border-gray-200 rounded-lg p-4">
                <div class="flex items-center mb-3">
                    <i class="fa fa-tasks text-gray-600 mr-2"></i>
                    <span class="font-bold text-sm text-gray-700">执行步骤</span>
                </div>
                <div class="space-y-2">
                    ${steps.map((step) => this.formatStep(step)).join("")}
                </div>
            </div>
        `;

        stepsDiv.appendChild(stepsContainer);
        chatBox.appendChild(stepsDiv);

        if (scroll) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    }

    formatStep(step) {
        const icons = {
            thought: "fa-lightbulb-o",
            action: "fa-play",
            observation: "fa-eye",
            final_answer: "fa-check",
            error: "fa-exclamation-triangle"
        };
        const colors = {
            thought: "text-yellow-600",
            action: "text-blue-600",
            observation: "text-green-600",
            final_answer: "text-primary",
            error: "text-red-600"
        };

        const type = step.type || "unknown";
        const icon = icons[type] || "fa-circle";
        const color = colors[type] || "text-gray-600";

        const content =
            type === "action"
                ? `<strong>工具:</strong> ${this.escapeHtml(step.tool || "")}<br><strong>参数:</strong> <code class="text-xs">${this.escapeHtml(step.input || "")}</code>`
                : this.escapeHtml(step.content || "");

        return `
            <div class="flex items-start text-sm">
                <i class="fa ${icon} ${color} mr-2 mt-1"></i>
                <div class="flex-1">
                    <span class="font-medium text-gray-700">${this.getStepLabel(type)}</span>
                    <div class="text-gray-600 text-xs mt-1">${content}</div>
                </div>
            </div>
        `;
    }

    getStepLabel(type) {
        const labels = {
            thought: "思考",
            action: "执行工具",
            observation: "观察结果",
            final_answer: "最终答案",
            error: "错误"
        };
        return labels[type] || type;
    }

    formatMessage(text) {
        return this.escapeHtml(text || "")
            .replace(/\n/g, "<br>")
            .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm">$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");
    }

    showStats(iterations, steps, durationMs) {
        const statsDiv = document.getElementById("agent-stats");
        if (!statsDiv) return;

        const durationText = durationMs > 0 ? `${(durationMs / 1000).toFixed(2)}s` : "-";
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
                <div class="flex items-center">
                    <i class="fa fa-clock-o mr-2"></i>
                    <span>耗时: ${durationText}</span>
                </div>
            </div>
        `;
    }

    showError(message) {
        const chatBox = document.getElementById("agent-chat-box");
        if (!chatBox) {
            alert(message);
            return;
        }

        const errorDiv = document.createElement("div");
        errorDiv.className = "mb-4 text-center";
        errorDiv.innerHTML = `
            <div class="inline-block px-4 py-2 rounded-lg bg-red-50 text-red-600 border border-red-200">
                <i class="fa fa-exclamation-circle mr-2"></i>
                ${this.escapeHtml(message)}
            </div>
        `;
        chatBox.appendChild(errorDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    updateStatusHint(text) {
        const statusHint = document.getElementById("agent-status-hint");
        if (!statusHint) return;
        statusHint.textContent = text;
    }

    formatRelativeTime(isoDate) {
        if (!isoDate) {
            return "未知时间";
        }
        const now = Date.now();
        const ts = new Date(isoDate).getTime();
        if (Number.isNaN(ts)) {
            return "未知时间";
        }
        const diffSec = Math.max(0, Math.floor((now - ts) / 1000));
        if (diffSec < 60) return `${diffSec}秒前`;
        if (diffSec < 3600) return `${Math.floor(diffSec / 60)}分钟前`;
        if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}小时前`;
        return `${Math.floor(diffSec / 86400)}天前`;
    }

    escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/\"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new AgentChat();
});
