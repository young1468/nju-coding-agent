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
 | list/read/write|
 | run_command    |
 | read_output    |
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
  `ToolResult(success, tool, result, error)`；超长输出通过受控 output ID 提供只读回取。
- 对 pytest、lint、类型检查等验证类命令，Tool Dispatcher 额外附加纯函数生成的
  `verification` 结果（passed/category/summary）；普通命令仍保持兼容的结果结构。
- Local Tools 是唯一执行文件操作和 `subprocess` 的位置。

## 不使用 Agent Framework 的原因

项目没有使用 LangChain、LlamaIndex、OpenAI Agents SDK、AutoGen、CrewAI 或类似框架。
对话历史、function schema、tool-call 解析、dispatcher、循环停止和错误结果均由本项目
代码实现。这样每个状态变化与安全决策都有明确位置，便于测试、演示和答辩说明。

## 会话与上下文工程

会话历史由 SessionStore 以 append-only JSONL 保存：首行记录版本与 workspace，后续每行记录消息、标题、日志或 compaction 元数据。Agent 内部保留完整 history，发送给模型前由 build_model_messages 生成有界请求视图；压缩摘要只替代模型请求视图中的旧消息，不删除原始历史。

GUI 从同一批运行日志派生轻量进度状态，显示当前阶段、`step/max_steps`、压缩次数和完成/失败状态；完整日志仍在独立弹窗中查看。

上下文预算保留现有字符配置，同时用保守启发式估算 token，并通过 reserve_tokens 为回复预留空间。超限时先按完整消息组选择压缩前缀，assistant tool call 与 tool result 不会被拆开；模型使用结构化摘要、最近消息和最新任务。摘要包含目标、约束、进度、决策、后续步骤和关键上下文，并累计读取/修改文件。

工具输出在进入消息历史前经过行数与 UTF-8 字节双重限制；read_file 保留头部，run_command 保留尾部。若发生截断，完整结果写入受控临时存储，只能使用本次运行生成的 output ID 通过 read_output 获取。项目启动时还会从祖先目录到 workspace 自动加载 AGENTS.md/CLAUDE.md，并以带路径的 XML 标签加入 system prompt。
