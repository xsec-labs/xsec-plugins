# 系统终端 MCP Host 边界

插件拥有 manifest、MCP 描述、Skill、可读的单文件 ESM 前端和原生 stdio sidecar。Runtime Host
统一拥有会话身份、PTY、Shell profile、启动目录、进程组和审计（终端没有控制租约）。
插件在标准 sandbox 中加载前端，并通过受限的 `xsec.terminal.*` 契约访问会话资源。

每次 MCP `tools/call` 先经 `xsec.terminal.context` 核验短期 Host RPC 令牌、冻结制品摘要、
调用角色、任务 lease 与工具允许列表。缺失或失效的上下文显式失败；write、resize、close
只带 `terminal_id`（和数据、尺寸），没有 `control` 参数。initialize 与 tools/list 只提供协议和工具信息。

`terminal.shell:session.agent`、`mcp.servers.register` 和 `native.execute` 进入安装及升级
确认流程。observer 的独立 cursor read 保留输出；界面卸载 detach，close 终止 PTY。
会话结束、插件撤销、卸载和 Runtime 退出由 Host 回收资源。

默认 Shell 配置位于“设置 → 插件 → 系统终端”，影响后续新建 PTY。Windows 使用当前可用的
CMD、Windows PowerShell 或 PowerShell 7；macOS/Linux 使用当前账户的登录 Shell。
界面与设置区跟随 Host 外观，显示实际操作错误。详见
[插件设置规范](https://github.com/xsec-labs/xsec-plugins/blob/main/docs/plugin-settings.md)。

开发日志使用 Host/frontend 的现有结构化通道；通用日志只记录有界、脱敏的操作元数据。
命令原文、终端输出、令牌和凭据按日志安全契约处理。
