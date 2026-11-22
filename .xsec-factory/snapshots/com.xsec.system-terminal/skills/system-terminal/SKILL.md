---
name: system-terminal
description: Operate the session-shared System Terminal MCP safely, including interactive programs and user-visible terminals.
---

# 系统终端 MCP

先调用 `terminal_profiles` 了解平台与可用 Shell；然后调用 `terminal_list`。复用终端前先用
`terminal_read` 查看它是否在执行任务或等待输入。需要新的 Shell 时调用 `terminal_open`；它会自动显示在
用户的底栏中。

写入时将命令、回车和控制字符原样作为 `data` 传给 `terminal_write`。命令不会自动执行：显式写入 `\r`。
对输出保存自己的 cursor，并用 `terminal_read` 分页读取；每个调用方的 cursor 独立，读取不消费其他调用方的
输出。`truncated: true` 表示较早输出已被运行时缓存淘汰。
若 `terminal_read` 返回 `read_error`，不要假定后续输出完整；调用 `terminal_reveal` 显示终端，用户可在界面
中显式选择“重新连接”恢复 PTY 输出读取。

用户、主 Agent 与子 Agent 共享相同 PTY，任何一方都可以键入，没有控制权之争：写入前先用
`terminal_read` 确认终端空闲，以免和用户的输入交错。终端没有控制租约，`terminal_write`、
`terminal_resize`、`terminal_close` 只需要 `terminal_id`（以及数据或尺寸），不需要任何凭据，也不会返回
`CONTROL_STALE` 或 `CONTROL_BUSY`。需要中断前台任务时写入 Ctrl+C (`\u0003`)。区分 Shell 进程结束码与某一命令的
退出码；需要后一种时让 Shell 显式打印该状态。

`terminal_open` 创建的终端会加入用户底栏终端面板的列表（面板里最多并排 4 个）；用户在面板里删除终端会
直接终止它，关闭面板标签只是隐藏，进程继续运行。用 `terminal_reveal` 重新显示面板；只有在确实不再需要该
进程时调用 `terminal_close`。

终端结束（Shell 退出或被 `terminal_close` 终止）后，面板列表里不再显示它，但 `terminal_list` 仍会列出它
（`state` 为 `exited` 或 `terminated`），`terminal_read` 仍能读到缓存的输出，包括最后输出；`terminal_write`
会失败。需要看结束前的输出就在新开终端之前读取：每个会话最多保留 8 个终端条目，`terminal_open` 遇到已满时会淘汰
最早打开的已结束条目，淘汰后无法再读。需要新的 Shell 时调用 `terminal_open`。任务结束时说明保留的后台进程或已终止的终端。

工具的完整参数 schema 以 MCP `tools/list` 为准。交互细节与平台注意事项见
[references/interactive.md](references/interactive.md)。
