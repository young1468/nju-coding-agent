# 测试说明

执行完整测试：

```powershell
python -m pytest
```

当前测试套件共 27 项，全部离线运行，不需要 API Key，也不访问真实模型或网络。临时项目均
由 pytest `tmp_path` 创建，不会修改 Coding Agent 工程本身。

## Unit Test

- 配置与 CLI：缺失模型配置时的清晰错误、环境变量读取、CLI 参数行为。
- Client：model/messages/tool schemas 是否正确传递，API 异常和畸形响应是否规范化。
- Agent：system/user/assistant/tool history、普通最终回答、空响应、模型异常、MAX_STEPS。
- 文件工具：正常读取、写入、父目录创建、缺失文件、目录读取、路径穿越、绝对/盘符路径、
  symlink 或 junction 逃逸、输出截断。
- 命令工具：成功、非零退出、stdout/stderr、return code、timeout、输出截断、`shell=False`、
  workspace cwd 和模型环境变量移除。
- Dispatcher：未知工具、非法参数和内部异常均返回统一 Tool Result。

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
