GitHub：https://github.com/young1468/nju-coding-agent

本项目是个人独立实现的 Python CLI Coding Agent。它通过 OpenAI Compatible API
与模型交互；Agent Loop、消息历史、Tool Schema、Tool Dispatcher、工具执行、错误处理
和停止条件均由本项目自行实现，未使用 LangChain、OpenAI Agents SDK 等 Agent 框架。

环境：Python 3.11+。安装：
  python -m pip install -r requirements.txt
  python -m pip install -e .

将 AGENT_API_KEY、AGENT_BASE_URL、AGENT_MODEL 配置到进程环境变量后运行：
  python -m coding_agent "修复当前项目中的失败测试，不要修改测试文件" --workspace demo_workspace

核心能力：模型原生 Tool Calling 驱动本地 list_files、read_file、write_file、run_command；
Agent 将结构化 Tool Result 回传模型并循环至最终回答。命令使用 shell=False、workspace
为 cwd、30 秒超时；文件路径 resolve 后检查 workspace 边界，防御 ../ 与 symlink/junction
逃逸；子进程不继承模型配置。工具输出统一截断，日志不输出密钥。

demo_workspace 含故意失败的 pytest，演示 Agent 检查文件、运行测试、修改实现、再次验证的
全过程；运行 python scripts/reset_demo.py 可恢复演示初态。完整离线测试使用 Fake Model，
不需要真实密钥。
