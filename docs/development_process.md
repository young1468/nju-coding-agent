# Coding Agent 开发流程

本项目按四个可验证阶段逐步实现。每个阶段完成后先运行测试，再创建独立 Git
提交，避免一次性引入过多不可定位的问题。

## Phase 1：项目初始化与 CLI 骨架

- 目标：建立可安装、可测试的 Python CLI 项目，不调用模型，也不执行本地操作。
- 实现：建立 `src/` 包布局、`python -m coding_agent` 入口、环境变量配置对象、
  `.env.example`、`.gitignore` 和基础 pytest 测试。
- 文件结构：核心入口位于 `src/coding_agent/__main__.py`，配置位于 `config.py`，
  测试位于 `tests/`。
- 测试：验证 CLI 参数处理和配置读取。
- 提交：`532a5e8 feat: scaffold phase 1 CLI`。

## Phase 2：LLM Client 与 Agent Loop

- 目标：以 OpenAI Compatible API 发起请求，并自行维护对话历史与最小循环。
- 实现：`client.py` 只封装单次 chat completion；`agent.py` 创建 system/user
  messages、追加 assistant/tool messages，并在普通文本回复时结束。
- 自实现原因：题目要求核心 Agent 行为可解释且不依赖 Agent Framework。历史由
  Agent 层持有的 `list[dict]` 管理，不保存在 client 的全局状态中。
- `MAX_STEPS=12`：该值预留给外部工具交互次数，不代表模型内部 reasoning steps；
  达到上限会明确停止，避免工具循环无限持续。
- 提交：`606e733 feat: implement model client and agent loop`。

## Phase 3：Local Tool System

- 目标：实现模型提出请求、程序本地执行、结果回传模型的完整工具闭环。
- 实现：`schemas.py` 定义原生 function schema；`tools.py` 定义 Tool Dispatcher、
  `ToolResult` 与 `list_files`、`read_file`、`write_file`、`run_command`。
- Agent 将 assistant tool call 加入 history，解析 JSON 参数后调用 dispatcher，并以
  `role="tool"` 的 JSON 结果继续请求模型。未知工具、参数错误、文件错误、命令失败和
  超时都会成为结构化结果，不会使 Agent 崩溃。
- workspace：所有文件路径 resolve 后必须仍位于 workspace 内。
- 提交：`26b72b5 feat: implement local tool system`。

## Phase 4：Coding Task Demo

- 目标：准备可展示的真实修复任务，而不是只展示单个工具。
- 实现：`demo_workspace/` 包含有意写错的 calculator 实现和失败 pytest；
  `scripts/reset_demo.py` 可恢复失败初态。system prompt 要求先检查、不要擅改测试、
  修改后运行测试，并给出简短总结。
- E2E：Fake Model 按 `list_files -> read_file -> run_command -> write_file ->
  run_command -> final answer` 驱动真实本地工具，验证源代码修复、测试文件未改动和
  最终 pytest 成功。
- 提交：`72995be feat: add coding task demo and e2e validation`。
