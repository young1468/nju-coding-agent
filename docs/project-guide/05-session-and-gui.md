# 第 5 章：会话持久化与 GUI 工作流

## 一、JSONL 会话

每个会话是本地 `.jsonl` 文件，一行一个 JSON entry，不需要数据库，便于备份、调试和恢复。文件包含 `session`（版本、workspace、创建时间）、`message`、`title`、`log` 和 `compaction` 记录。`SessionStore.load_messages()` 忽略元数据，因此旧 JSONL 仍可恢复。

## 二、workspace 绑定

session header 保存创建时的绝对 workspace。加载时路径不一致就拒绝恢复并提示 `Session workspace does not match the requested workspace.`，避免把项目 A 的历史误用于项目 B。

## 三、历史、日志和删除

会话完成后，GUI 根据首条任务和最终回复生成标题，失败时使用本地规则回退。历史列表显示标题、workspace、更新时间和消息数量。运行日志经事件队列实时进入日志窗口，并追加保存到会话；删除按钮只允许永久删除当前会话目录的直接 `.jsonl` 子文件，并经过二次确认。

## 四、Plan 工作流

```text
任务 → Plan mode（只读）→ 用户查看/编辑/Refine
     → Execute plan → Auto mode 修改文件并验证
```

Plan 阶段没有 `write_file` 和 `run_command` 权限；执行阶段把原始任务和批准计划一起交给 Agent。

## 五、GUI 线程和信息层级

Agent 在后台线程运行，主线程通过 `queue.Queue` 消费 `log`、`done`、`error` 事件。主对话区只显示任务、关键节点和最终回复；完整 JSON 位于独立日志窗口。Settings 持久化 workspace、会话目录、模式、上下文预算、回复预留 token 和 `max_steps`，API Key 只从环境读取。

Conversation 标题下方的状态条从已有日志派生 `Phase`、`Step/max_steps`、`Compactions` 和 `Status`。读取文件、写入文件、运行验证、压缩、overflow 重试和最终完成分别映射为简短阶段；选择历史会话时也会重新计算这些统计，不新增会话记录类型。

长期记忆独立于 JSONL：GUI Settings 可以启用记忆并设置注入预算，`View memory` 以只读方式查看全局和当前项目的 Markdown。运行日志会显示加载和提取数量，memory 文件不会写入会话 message。

## 六、与 Pi 的差异

本项目是线性 append-only 会话，可以恢复和删除，但不能创建分支或回退；Pi 的 Session Tree 不在当前范围内。线性结构更简单、行为更可预测，适合当前 GUI。
