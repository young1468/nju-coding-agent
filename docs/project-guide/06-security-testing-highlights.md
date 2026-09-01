# 第 6 章：安全边界、测试与项目亮点

## 一、安全边界

文件工具只接受相对路径，并检查解析后路径仍位于 workspace 内；绝对路径、盘符路径和 `..` 逃逸都会被拒绝。`run_command` 使用参数数组和 `shell=False`。日志会对 API key、authorization、token、secret、password 等参数脱敏；完整工具结果使用受控输出 ID 读取，会话和日志默认只在本地保存。

## 二、测试覆盖

- 工具测试：路径安全、参数错误、输出截断、UTF-8 边界、`read_output` ID。
- Agent 测试：工具循环、模式权限、最大步数、上下文溢出重试、项目指令加载。
- Session 测试：旧 JSONL、标题/日志/压缩元数据、workspace 校验和恢复。
- GUI 测试：标题回退、Plan 提示、设置兼容和非法配置。
- 回归检查：完整 `pytest` 和 Tkinter 无交互启动。

测试注入 Fake Model，不依赖真实密钥或网络，因此每条行为都可重复验证。

## 三、跨文件 coding 演示

`demo_workspace/order_demo` 将金额计算、库存预留、checkout 编排和 CLI 输出拆成多个模块，并预置 Decimal、优惠顺序和库存原子性故障。任务要求 Agent 修复实现、保持 CLI 兼容并运行测试，可以展示阅读多文件、理解约束、修改源码和验证结果的完整能力。

## 四、项目亮点

| 亮点 | 当前实现 | 价值 |
| --- | --- | --- |
| 工具调用闭环 | assistant call → dispatcher → result | 基于真实结果迭代 |
| 权限分级 | Auto / Review / Plan | 规划与修改隔离 |
| 可恢复会话 | append-only JSONL | 可暂停、恢复、审计 |
| 日志分层 | 关键节点 + 独立完整日志 | 可读且可追溯 |
| 输出控制 | 行数/字节截断 + `read_output` | 防止撑爆上下文 |
| 结构化压缩 | 六段摘要 + 文件状态 | 长会话保留进度 |
| 步骤配置 | GUI 可调 `max_steps` | 复杂任务有余量且不死循环 |
| Plan 确认执行 | 用户确认后切换 Auto | 保留人类控制 |

## 五、边界与未来

已实现的是一条完整、可测试的本地 coding workflow，借鉴 Pi 的是上下文工程、输出控制和简洁分层。Skills 懒加载、Session Tree 分支、流式响应、命令沙箱和多 Agent 编排仍属于未来扩展，不应误称为当前能力。

