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
- `Settings` 配置 Workspace、会话目录、上下文字符预算和回复预留 token，不保存 API Key。

会话保存在本地 JSONL 并校验 Workspace；工具路径限制在 Workspace 内，命令使用 `shell=False`。

## 上下文工程

- 工具输出同时受行数和 UTF-8 字节数限制：文件读取保留头部，命令输出保留尾部。
- 超长工具结果会保存到受控临时文件，Agent 只能通过返回的 `output_id` 调用 `read_output` 读取。
- 长会话会在请求前压缩为包含 Goal、Progress、Key Decisions 等 section 的摘要；原始消息仍保存在 JSONL 中。
- 检测到模型上下文溢出时会自动压缩并重试一次；摘要生成失败时使用本地回退摘要。
- Agent 会自动加载 workspace 及其祖先目录中的 `AGENTS.md`、`CLAUDE.md` 项目规则。

## 演示与测试

将 Workspace 设为 `demo_workspace` 可演示修复计算器并运行测试：

```powershell
python scripts/reset_demo.py
python -m pytest
```

测试使用 Fake Model，不需要密钥或网络。CLI 仍可用：`python -m coding_agent "任务" --workspace demo_workspace`。
