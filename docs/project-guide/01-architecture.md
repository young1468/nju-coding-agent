# 第 1 章：项目总览与整体架构

## 一、它解决什么问题

普通聊天模型只能返回文字；Coding Agent 还必须能观察工作区、修改源码、运行测试，并把工具结果继续交给模型判断。本项目把这条闭环放进一个本地 Tkinter 应用中：用户输入任务，Agent 自主决定是否调用工具，最后返回可验证的结果。

项目入口仍保留 CLI，但主要交互入口是 `coding_agent.gui`。GUI 负责交互和展示，真正的任务执行由核心 Agent 完成，因此测试不依赖 Tkinter 或真实模型。

## 二、五个边界

| 模块 | 主要职责 | 不负责什么 |
| --- | --- | --- |
| `gui.py` | 输入、模式、设置、历史、日志和 Plan 工作流 | 不实现模型推理 |
| `agent.py` | Agent Loop、模式权限、上下文构建、工具调用 | 不直接操作文件系统 |
| `client.py` | 读取模型配置并调用 OpenAI-compatible API | 不决定下一步工具 |
| `tools.py` | 校验工具参数并执行本地操作 | 不生成自然语言答案 |
| `session.py` | 保存/恢复消息、标题、日志和压缩元数据 | 不执行工具 |

这种边界使依赖方向清晰：GUI 和 CLI 都可以复用 `CodingAgent`，Agent 可以注入 Fake Model 和临时 workspace，工具和会话也可以单独测试。

## 三、一次任务的旅程

```text
用户任务
  ↓
GUI 读取 workspace / mode / session / budgets
  ↓
CodingAgent 加载项目指令和历史消息
  ↓
build_model_messages() 生成有限上下文
  ↓
ModelClient.complete(messages, tools)
  ├─ assistant content → 最终回复
  └─ assistant tool_calls
       ↓
       ToolDispatcher 校验并执行
       ↓
  tool result 追加到会话，再请求模型
```

每一轮都是“模型决定动作，程序执行动作，结果回到模型”。程序不猜测模型意图，也不允许模型绕过工具层直接读写任意路径。

验证类命令还会经过 `feedback.py` 的确定性分类器，将返回码、超时和常见测试错误转换为结构化反馈；GUI 再从日志派生阶段和压缩统计。这样“任务是否通过”和“任务进行到哪一步”都不是依赖模型自述。

## 四、为什么没有把所有逻辑放进 GUI

GUI 线程只负责启动后台任务、接收事件和渲染文本；Agent 不依赖具体窗口。这样做有三个直接收益：

1. CLI 和 GUI 使用相同的核心行为。
2. Agent Loop 可以用 Fake Model 做确定性测试。
3. 将来替换 Tkinter、增加 Web UI 或 RPC 入口时，不必重写工具和上下文逻辑。

## 五、和 Pi 三层架构的对应

Pi 把模型抽象、Agent 引擎和产品外壳拆开。本项目虽然是一个较小的 Python 仓库，也保留了同样的思想：`client.py` 对应模型层，`agent.py` 对应循环层，`gui.py`/`__main__.py` 对应产品入口，`tools.py` 和 `session.py` 是本项目围绕编码工作流增加的基础设施。

区别在于，本项目只实现 OpenAI-compatible 客户端，不追求 Pi 的多供应商注册表；会话是线性 JSONL，不是可分叉的 Session Tree。这是范围控制，而不是隐藏能力。
