# Agent 模块实现说明（毕设版）

## 1. 模块目标
- 将 Agent 页面从静态展示升级为可交互工作台。
- 支持参数配置、会话持久化、执行步骤展示、统计信息展示。
- 与后端 `/api/agent/*` 接口形成稳定闭环。

## 2. 前端结构
- 页面入口：`Frontend/agent-demo.html`
- 核心脚本：`Frontend/js/agent.js`
- 配置入口：`Frontend/js/config.js`
- 样式补充：`Frontend/css/agent.css`

### 2.1 页面区块
- 运行配置区：模型、最大迭代、温度、步骤显示开关。
- 会话区：新建会话、清空会话、会话列表切换。
- 对话区：用户消息、Agent 回复、步骤卡片、错误提示。
- 统计区：迭代次数、步骤数量、耗时。

### 2.2 前端关键能力
- localStorage 持久化会话。
- 请求状态管理（pending/成功/失败）。
- `show_steps` 开关控制步骤渲染。
- 对话渲染时使用 HTML 转义，避免直接注入。

## 3. 后端增强点
- 请求模型新增可选字段：`llm_model`、`temperature`、`show_steps`。
- Agent 服务接入 `session_id` 历史上下文，控制最近轮数。
- 统一返回结构，失败分支保留 `iterations` 字段。
- 结构化指标日志：`session_id`、`iterations`、`tools_called`、`duration_ms`、`success`。

## 4. 测试策略
- 单元脚本：`test/test_agent.py`
- 接口脚本：`test/test_agent_endpoints.py`
- 前端手工回归：`test/agent_frontend_regression_checklist.md`

## 5. 已知限制
- 当前 Agent 仍是串行 ReAct，未实现流式步骤推送。
- 模型推理稳定性受 Ollama/GPU 运行状态影响。
- 会话上下文目前为进程内存级，重启后清空。

## 6. 演示建议
1. 先跑健康检查和工具列表。
2. 用“现在几点了”验证低风险路径。
3. 用“计算 10+20*3”展示工具调用。
4. 关闭 `show_steps` 演示参数开关效果。
5. 刷新页面验证会话恢复。
