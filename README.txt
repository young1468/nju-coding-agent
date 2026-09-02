# Coding Agent

GitHub：https://github.com/young1468/nju-coding-agent

个人独立实现的 Python 编程智能体桌面应用，使用 Tkinter 和 OpenAI Compatible API，可读取、修改文件并运行命令；未使用 Agent 框架。

## 运行

Python 3.11+，PowerShell：

```powershell
cd D:\Desktop\NJU\nju-coding-agent
python -m pip install -r requirements.txt
python -m pip install -e .
python -m coding_agent.gui
```

项目根目录需创建 `.env`：

```dotenv
AGENT_API_KEY=your-api-key
AGENT_BASE_URL=https://your-compatible-endpoint/v1
AGENT_MODEL=your-model-name
```

## GUI 功能

- 历史会话：创建、恢复、刷新和确认删除 JSONL 会话。
- 对话区：显示任务、关键流程和回复；`View logs` 查看完整工具日志。
- `auto` 可读写和运行命令；`review` 只读审查；`plan` 只读规划。
- Plan 生成后可编辑或用 `Refine plan` 修改，确认后点 `Execute plan` 执行。
- `Settings` 配置 Workspace、会话目录、上下文字符预算、回复预留 token 和最大工具交互步数，不保存 API Key。
- `Settings` 可启用长期记忆并设置记忆上下文预算；`View memory` 查看全局与项目记忆文件。

## 原理文档

项目架构、模型调用、Agent Loop、工具消息、上下文压缩、会话与 GUI 工作流的分章说明见：[docs/project-guide/README.md](docs/project-guide/README.md)。

会话保存在本地 JSONL 并校验 Workspace；工具路径限制在 Workspace 内，命令使用 `shell=False`。

## 上下文工程

- 工具输出同时受行数和 UTF-8 字节数限制：文件读取保留头部，命令输出保留尾部。
- 超长工具结果会保存到受控临时文件，Agent 只能通过返回的 `output_id` 调用 `read_output` 读取。
- 长会话会在请求前压缩为包含 Goal、Progress、Key Decisions 等 section 的摘要；原始消息仍保存在 JSONL 中。
- 检测到模型上下文溢出时会自动压缩并重试一次；摘要生成失败时使用本地回退摘要。
- 最大工具交互步数默认 24，可在 GUI 设置中调整；达到上限时任务会停止，避免模型陷入无限工具循环。
- Agent 会自动加载 workspace 及其祖先目录中的 `AGENTS.md`、`CLAUDE.md` 项目规则。

## 长期记忆

- 全局记忆保存在用户目录 `.coding-agent/memory.md`，项目记忆保存在 workspace 的 `.coding-agent/memory.md`。
- 每个记忆文件旁有 `memory-index.json`，用于去重、分类和任务相关检索；Markdown 仍是人工可读来源。
- 成功任务完成后，模型可提取稳定的用户偏好、项目约定和设计决策；规则会过滤 token、密码、密钥和临时日志。
- 每轮只注入与当前任务相关的有限记忆，不会把全部历史或全部 memory.md 无限制塞进上下文。
- 长期记忆是本地应用层能力，不是 Pi 原生的用户画像系统；当前不使用向量数据库或跨会话 embedding 检索。
