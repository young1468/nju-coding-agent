# 安全设计

## Workspace 限制

`ToolDispatcher` 在创建时接收一个已存在的 workspace。`list_files`、`read_file` 和
`write_file` 只接受相对路径：绝对路径、盘符路径会被拒绝。程序以 workspace 拼接输入后
调用 `resolve(strict=False)`，再使用 `relative_to(workspace)` 检查解析后的真实路径是否仍
位于 workspace 内。因此 `../`、多层 `../../` 等路径逃逸不会通过字符串判断，而是通过真实
路径位置判断拒绝。

## Symlink/Junction 防护

仅检查原始路径不足以防御 workspace 内的链接指向外部目录。解析后的路径会跟随已有的
symbolic link 或 Windows junction；若最终目标不在 workspace 内，读取、写入和目录列举都
返回结构化错误。测试覆盖 symlink，并在无 symlink 权限的 Windows 环境中以 junction 验证
相同防线。

## Command Execution

`run_command` 接受分离的 `program` 与字符串数组 `args`，调用
`subprocess.run([program, *args], shell=False, cwd=workspace, ...)`。它不拼接 shell
命令，cwd 固定为 workspace，默认超时为 30 秒。stdout、stderr、return code 与 timeout
状态写入 Tool Result；非零退出码和超时不会使 Agent 进程崩溃。

## 凭据保护

模型设置只从 `AGENT_API_KEY`、`AGENT_BASE_URL`、`AGENT_MODEL` 环境变量读取；`.env`
被 Git 忽略，示例文件没有值。CLI 与日志不输出 API Key 或完整环境。启动子进程前，
dispatcher 从子进程环境移除三项模型变量，避免将模型凭据传递给被执行程序。

## 安全边界说明

workspace 限制是应用层路径约束，不是 OS 级 sandbox。它没有提供容器、Windows Sandbox、
seccomp、namespace 或操作系统权限隔离。演示时应仅将可信的、独立的项目目录作为
workspace，并将 `run_command` 视为具有该用户权限的本地执行能力。
