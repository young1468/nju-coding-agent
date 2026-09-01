# Coding Agent 原理详解

这是一套面向本项目的实现说明，写作方式参考 `pi-agent/` 的原理文章，但内容以当前 Python 源码为准。阅读顺序从整体架构开始，再进入模型调用、工具消息、上下文、会话与 GUI，最后看安全、测试和项目亮点。

## 目录

1. [项目总览与整体架构](01-architecture.md)
2. [模型调用与 Agent Loop](02-model-and-agent-loop.md)
3. [工具系统与工具消息](03-tools-and-messages.md)
4. [上下文工程与上下文压缩](04-context-engineering.md)
5. [会话持久化与 GUI 工作流](05-session-and-gui.md)
6. [安全边界、测试与项目亮点](06-security-testing-highlights.md)

## 一张图看懂项目

```text
┌─────────────────────────────────────────────┐
│ Tkinter GUI / CLI                           │
│ 输入任务 · 选择模式 · 展示关键节点和回复      │
└──────────────────┬──────────────────────────┘
                   │ task + settings
┌──────────────────▼──────────────────────────┐
│ CodingAgent                                 │
│ 构建上下文 · 请求模型 · 处理 tool call        │
│ 控制 Agent Loop · 限制 max_steps              │
└──────────────┬─────────────────┬────────────┘
               │                  │
┌──────────────▼──────────┐ ┌─────▼────────────────┐
│ OpenAICompatibleClient   │ │ ToolDispatcher       │
│ messages + tools 请求    │ │ 文件、命令、输出读取  │
└──────────────┬──────────┘ └─────┬────────────────┘
               │                  │
        Compatible API       workspace boundary
                                  │
                         ┌────────▼────────┐
                         │ SessionStore    │
                         │ append-only JSONL│
                         └─────────────────┘
```

## 与 Pi 的关系

- **已实现的借鉴点**：小而清晰的 Agent Loop、工具输出截断、项目指令注入、上下文预算、结构化压缩、原始会话保留。
- **本项目自己的产品选择**：Tkinter GUI、Plan/Review 模式、独立日志弹窗、会话删除、可配置 `max_steps`。
- **当前未实现**：Pi 的多供应商适配体系、Skills 懒加载、Session Tree 分支、流式事件树和多 Agent 编排。

更细的设计背景仍可参考现有的[架构说明](../architecture.md)、[安全设计](../security_design.md)和[测试说明](../testing.md)。

