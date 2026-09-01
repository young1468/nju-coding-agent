# 第 3 章：工具系统与工具消息

## 一、工具不是模型的后门

模型只能提出结构化 tool call，不能直接访问 Python 文件系统。`schemas.py` 向模型公开工具名称、描述、参数类型和必填字段；`ToolDispatcher` 再对同一请求做运行时校验。

## 二、内置工具

| 工具 | 作用 | 关键约束 |
| --- | --- | --- |
| `list_files` | 查看目录直接子项 | 目录必须位于 workspace |
| `read_file` | 读取 UTF-8 文本 | 只接受 workspace-relative 路径 |
| `write_file` | 创建或覆盖文本文件 | 写入路径不得逃逸 workspace |
| `run_command` | 在 workspace 运行程序 | `shell=False`，参数为字符串数组 |
| `read_output` | 读取此前被截断的完整输出 | 只能使用已登记的 `output_id` |

`read_output` 不接受任意文件路径，因此按需读取完整结果不会扩大模型的本地文件权限。

## 三、消息的最小闭环

一次读取文件会在会话中形成类似下面的消息链：

```json
{"role":"assistant","content":null,"tool_calls":[{"id":"call-1","function":{"name":"read_file","arguments":"{\"path\":\"pricing.py\"}"}}]}
{"role":"tool","tool_call_id":"call-1","content":"{\"success\":true,\"tool\":\"read_file\",\"result\":{...}}"}
```

Agent 保存 assistant tool call，再追加对应 tool result。下一次模型请求会同时看到调用和结果，因而能够基于真实执行结果继续工作。

## 四、输出控制

工具输出同时受最大行数和最大 UTF-8 字节数限制。实现按字符边界截断，避免中文或 emoji 被切成无效字节；超长单行也会被单独处理。`read_file` 默认保留头部，`run_command` 默认保留尾部。

被截断的结果会写入受控临时文件，并返回截断原因、原始行数、原始字节数和 `output_id`。模型只有再次调用 `read_output` 才能读取完整内容。

## 五、GUI 为什么隐藏完整 JSON

主对话区只渲染“读取文件”“运行测试”“写入文件”等关键节点，避免完整参数和结果淹没最终回复。完整 tool call、参数、结果和异常会追加到 JSONL 的 `log` 记录，并在 View logs 弹窗中查看。

## 六、优点与限制

工具层的优点是权限集中、参数可验证、结果结构统一，便于增加新工具和做安全测试。当前限制是命令执行仍依赖本机环境，未引入沙箱；工具并行执行、交互式终端和远程 workspace 不在本轮范围内。

