# 测试说明

执行完整测试：

```powershell
python -m pytest
```

当前测试套件共 56 项，全部离线运行，不需要 API Key，也不访问真实模型或网络。临时项目均
由 pytest `tmp_path` 创建，不会修改 Coding Agent 工程本身。

## Unit Test

- 配置与 CLI：缺失模型配置时的清晰错误、环境变量读取、CLI 参数行为。
- Client：model/messages/tool schemas 是否正确传递，API 异常和畸形响应是否规范化。
- Agent：system/user/assistant/tool history、普通最终回答、空响应、模型异常、MAX_STEPS。
- 文件工具：正常读取、写入、父目录创建、缺失文件、目录读取、路径穿越、绝对/盘符路径、
  symlink 或 junction 逃逸、行/字节双重输出截断、受控 output ID 回读。
- 命令工具：成功、非零退出、stdout/stderr、return code、timeout、输出截断、`shell=False`、
  workspace cwd 和模型环境变量移除。
- Dispatcher：未知工具、非法参数和内部异常均返回统一 Tool Result。
- Feedback：验证类命令的成功、断言失败、语法错误、导入错误、超时和命令缺失均由纯函数确定性分类；普通命令保持原有结果结构。
- GUI 控制层：进度阶段、Agent Step、压缩次数、完成/失败状态，以及历史日志恢复均可在不创建真实窗口的情况下测试。
- Demo reset：`scripts/reset_order_demo.py` 只覆盖 `order_demo/pricing.py` 和 `catalog.py`，并拒绝缺少 `tests/` 或指定模块的目录。

## Integration / E2E Test

`tests/test_e2e.py` 使用 Fake Model 编排以下真实本地工具流程：

```text
list_files
  ↓
read_file
  ↓
run_command (pytest fails)
  ↓
write_file
  ↓
run_command (pytest passes)
  ↓
final answer
```

测试断言 source 被修复、测试文件保持原样、每个 Tool Result 进入 message history，且修复前
命令失败、修复后命令成功。

## Session History

`tests/test_session.py` 覆盖 JSONL 往返、损坏文件、workspace 不匹配、上下文超限、工具消息完整性和 compaction 元数据恢复；`test_session_agent.py` 覆盖跨运行恢复。会话日志可能包含源代码与命令输出，因此只用于本地调试，不能提交到仓库。

上下文增强的行为还可通过 GUI 验证：在 Settings 中设置较小的上下文预算，连续提交多轮任务，观察状态条中的 `Compactions` 计数和 `Context summarized` 阶段，并在 `.sessions/*.jsonl` 中检查 `type: "compaction"` 记录；大文件读取应显示截断标记和 output ID。

录制跨文件修复演示时，先执行 `python scripts/reset_order_demo.py`，确认故障基线为 `5 failed, 1 passed`，再让 Agent 修复并运行完整 pytest，最终应恢复为 6 个测试全部通过。
