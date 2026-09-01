# 第 4 章：上下文工程与上下文压缩

## 一、为什么需要两层防护

编码任务会不断增加文件内容、测试输出和工具消息。单次 `read_file` 就可能占满窗口，而完整历史又不能简单删除，否则模型会忘记目标、决策和已修改文件。本项目先控制单次工具输出，再对旧历史做结构化压缩。

## 二、三个预算参数

| 参数 | 含义 |
| --- | --- |
| `max_context_chars` | 请求上下文的总字符预算 |
| `recent_context_chars` | 未压缩时优先保留的近期消息预算 |
| `reserve_tokens` | 为模型回复预留的 token 数 |

项目使用保守估算：JSON 序列化后的 ASCII 文本约 4 个字符一个 token，中文、emoji 等非 ASCII 字符按约 1 个字符一个 token。它不依赖额外 tokenizer，目标是提前发现风险。

## 三、构建有限请求视图

`build_model_messages()` 不修改完整历史，只生成发送给模型的副本：

1. 永远保留初始 system message 和模式指令。
2. 优先保留最新 user 消息。
3. 从后往前保留近期消息。
4. assistant tool call 和对应 tool result 作为一个完整组处理。
5. 单条 user 消息本身超预算时，按字符边界截短并加入提示。

因此 JSONL 中仍有完整记录，模型看到的只是当前请求所需的有限视图。

## 四、结构化压缩

达到“估算上下文预算减去 `reserve_tokens`”的阈值时，Agent 选择较旧且位于完整 turn 边界的消息作为摘要输入。摘要模型只能接收 `tools=None`，避免压缩请求递归触发工具循环。

摘要固定包含 `Goal`、`Constraints & Preferences`、`Progress`、`Key Decisions`、`Next Steps` 和 `Critical Context`。`compaction` 元数据保存摘要、压缩前 token 估算、保留消息起始索引以及 `read_files`/`modified_files`。多次压缩会使用上一份摘要增量更新；模型失败或返回空内容时使用本地规则摘要。

## 五、溢出重试和重复压缩控制

若 API 返回 context overflow，Agent 会强制生成一次摘要，重新构建请求并重试一次。普通网络错误不触发这条路径，第二次失败也会明确返回错误。`compacted_at_index` 是压缩水位线，避免每个 Agent step 重复生成相同摘要。

## 六、和 Pi 的关系

这里借鉴了 Pi 的“有限窗口是工程问题”“工具输出先截断”“摘要保留任务状态”三点思想；本项目没有实现 Pi 的分支摘要、Session Tree 或 Skills 渐进式加载。当前方案的优点是改动小、原始历史可恢复，限制是摘要质量依赖模型，token 估算也不是供应商精确计费结果。

### 控制单次输出，对旧历史结构化压缩