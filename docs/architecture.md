# 系统架构

```text
User
 |
CLI
 |
Agent Loop -----------------> LLM Client
 |                                |
 |                            Tool Calling
 v                                |
Tool Dispatcher <-----------------
 |
 +----------------+
 | Local Tools    |
 | list_files     |
 | read_file      |
 | write_file     |
 | run_command    |
 +----------------+
 |
Tool Result
 |
Agent Loop -> LLM Client -> ... -> Final Answer
```

## 职责划分

- CLI 读取任务、模型配置和 workspace，显示步骤日志与最终结果。
- Agent Loop 持有单次任务的 messages，调用模型，追加 assistant message，并将每个
  工具结果作为 tool message 回传。普通 assistant 文本即是最终回答。
- LLM Client 仅使用 `openai` 包发出 OpenAI Compatible chat completion 请求；不保存
  history、不执行工具、不实现循环。
- Tool Dispatcher 根据工具名验证 JSON 参数、调用对应的本地 Python 函数，并返回统一的
  `ToolResult(success, tool, result, error)`。
- Local Tools 是唯一执行文件操作和 `subprocess` 的位置。

## 不使用 Agent Framework 的原因

项目没有使用 LangChain、LlamaIndex、OpenAI Agents SDK、AutoGen、CrewAI 或类似框架。
对话历史、function schema、tool-call 解析、dispatcher、循环停止和错误结果均由本项目
代码实现。这样每个状态变化与安全决策都有明确位置，便于测试、演示和答辩说明。
