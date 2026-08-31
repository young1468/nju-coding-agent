GitHub：https://github.com/young1468/nju-coding-agent

本项目是个人独立实现的 Python CLI Coding Agent。它通过 OpenAI Compatible API
与模型交互；Agent Loop、消息历史、Tool Schema、Tool Dispatcher、工具执行、错误处理
和停止条件均由本项目自行实现，未使用 LangChain、OpenAI Agents SDK 等 Agent 框架。

环境：Python 3.11+。安装：
  python -m pip install -r requirements.txt
  python -m pip install -e .

在项目根目录创建本地 `.env`，填写 AGENT_API_KEY、AGENT_BASE_URL、AGENT_MODEL 后运行。程序会自动加载 `.env`；若同名进程环境变量已存在，环境变量优先。`.env` 已被 Git 忽略，不能提交真实凭据：
  python -m coding_agent "修复当前项目中的失败测试，不要修改测试文件" --workspace demo_workspace

核心能力：模型原生 Tool Calling 驱动本地 list_files、read_file、write_file、run_command；
Agent 将结构化 Tool Result 回传模型并循环至最终回答。命令使用 shell=False、workspace
为 cwd、30 秒超时；文件路径 resolve 后检查 workspace 边界，防御 ../ 与 symlink/junction
逃逸；子进程不继承模型配置。工具输出统一截断，日志不输出密钥。

demo_workspace 含故意失败的 pytest，演示 Agent 检查文件、运行测试、修改实现、再次验证的
全过程；运行 python scripts/reset_demo.py 可恢复演示初态。完整离线测试使用 Fake Model，
不需要真实密钥。

## 会话历史与上下文

可通过 --session 将消息追加保存为本地 JSONL，会话文件包含 workspace 校验，下一次使用同一路径会自动恢复历史：

  python -m coding_agent 继续修复 --workspace demo_workspace --session .sessions/demo.jsonl

Agent 在每次模型请求前构造独立的上下文视图：保留 system message、最新任务和完整的最近工具交互；超出字符预算时加入明确的省略提示。字符数只是通用近似，不等同于特定模型的 token 计数。会话文件可能包含任务和工具输出，仅保存在本地并已加入 Git 忽略规则。

## 本地桌面界面

启动：

  python -m coding_agent.gui

GUI 可管理本地 JSONL 会话、恢复历史 workspace，并在 Auto、Review 和 Plan 模式间切换。Auto 允许所有工具；Review 和 Plan 只允许列目录和读取文件，不允许写入或运行命令。Plan 模式生成计划后会显示可编辑的计划区，可用反馈重新整理计划，确认后点击 `Execute plan` 切换到 Auto 模式执行。GUI 设置保存在本地 `.coding-agent-gui.json`，不会保存 API Key；workspace 路径限制仍是应用层保护，不是 OS 级 sandbox。
