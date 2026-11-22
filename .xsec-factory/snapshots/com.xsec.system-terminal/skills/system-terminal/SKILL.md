---
name: system-terminal
description: Operate the session-shared System Terminal MCP for interactive programs and for work the user should watch or operate together. For one-off commands, use the bash tool instead.
---

# 系统终端 MCP

分工：一次性命令（执行完就结束、不需要交互）用 bash 工具；交互式程序，或需要用户一起看、一起操作的任务，用系统终端。

先调用 `terminal_profiles` 了解平台与可用 Shell；然后调用 `terminal_list`。复用终端前先用
`terminal_read` 查看它是否在执行任务或等待输入。需要新的 Shell 时调用 `terminal_open`；它会自动显示在
用户的底栏中。

写入时将命令、回车和控制字符原样作为 `data` 传给 `terminal_write`。命令不会自动执行：显式写入 `\r`。
对输出保存自己的 cursor，并用 `terminal_read` 分页读取；每个调用方的 cursor 独立，读取不消费其他调用方的
输出。`truncated: true` 表示较早输出已被运行时缓存淘汰。
若 `terminal_read` 返回 `read_error`，不要假定后续输出完整；调用 `terminal_reveal` 显示终端，用户可在界面
中显式选择“重新连接”恢复 PTY 输出读取。

用户、主 Agent 与子 Agent 共享相同 PTY，没有控制租约，任何人都可以输入。写入前先用 `terminal_read` 看终端是否在执行任务或等待输入，避免打断别人正在运行的前台程序。Agent 的写入需要用户审批，审批里会显示终端未提交的输入和最近输出；未获批准的写入不会执行。读取输出不需要任何许可。需要中断前台任务时写入
Ctrl+C (`\u0003`)。区分 Shell 进程结束码与某一命令的退出码；需要后一种时让 Shell 显式打印该状态。

关闭底栏标签只会隐藏终端。用 `terminal_reveal` 重新显示隐藏终端；只有在确实不再需要该进程时调用
`terminal_close`。任务结束时说明保留的后台进程或已终止的终端。

工具的完整参数 schema 以 MCP `tools/list` 为准。交互细节与平台注意事项见
[references/interactive.md](references/interactive.md)。
