# 第 2 章：模型调用与 Agent Loop

## 一、模型调用的边界

`client.py` 将模型服务收敛到一个小接口：

```python
response = client.complete(messages, tools=tool_schemas)
```

`Settings.from_env()` 从 `.env` 或环境变量读取 API Key、Base URL 和模型名；`OpenAICompatibleClient` 再把统一的 Python 消息列表发送到兼容接口。Agent 不需要知道具体 HTTP 细节，也不把密钥写入会话。

本项目的“兼容”指请求协议兼容 OpenAI Chat Completions 风格，不等于已经实现 Pi 那样的多厂商适配和流式事件抽象。

## 二、Agent Loop 如何转动

`CodingAgent.run()` 的核心是一个有上限的循环：

```text
while True:
  压缩或构建有限上下文
  请求模型
  追加 assistant message
  if 有 tool_calls:
      执行每个工具
      追加 tool message
      继续下一轮
  if 有文本:
      返回 completed
  否则返回 error
```

一批工具调用属于同一轮工具交互。工具结果必须带有对应的 `tool_call_id`，模型才能把结果和请求配对。

## 三、停止条件和失败路径

默认 `MAX_STEPS` 为 24，GUI 可以在 Settings 中配置。它限制工具交互轮数，不限制最终回复长度。达到上限时返回 `status="max_steps"`，防止模型在重复读取文件或重复运行命令时无限循环。

其他停止情况包括：模型返回空内容、工具调用缺少 ID、会话不匹配、模型配置错误，以及普通网络/API 错误。上下文溢出是特殊情况：Agent 会识别错误文本，执行一次压缩并重试原请求；第二次失败后停止，不会无限重试。

## 四、模式如何改变工具集合

`MODE_TOOL_NAMES` 是权限的单一来源：

| 模式 | 可用工具 | 目的 |
| --- | --- | --- |
| Auto | 列目录、读写文件、运行命令 | 完整编码任务 |
| Review | 列目录、读取文件 | 只读审查 |
| Plan | 列目录、读取文件 | 生成实施计划 |

Plan 模式生成计划后，GUI 允许用户编辑或请求修改；只有点击 Execute Plan 后，才以 Auto 模式执行批准的计划。

## 五、项目指令如何进入模型

Agent 从 workspace 向上查找 `AGENTS.md` 和 `CLAUDE.md`，按祖先目录到当前 workspace 的顺序读取，并使用带 `path` 属性的 XML 标签拼接到 system message。组织级规则先出现，项目级规则后出现。

## 六、优点与限制

优点是循环逻辑短、工具权限显式、每一步都可记录和测试；限制是当前客户端没有流式 token 展示，且 `max_steps` 是轮数上限而不是基于成本或时间的动态预算。

