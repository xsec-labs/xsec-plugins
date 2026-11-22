# 系统终端 MCP

`com.xsec.system-terminal` 4.2.0 交付共享 PTY 的文本界面、原生 stdio MCP Server
和 `system-terminal` Skill。Desktop/Web 用户与 Agent 访问同一 Runtime 会话；Host
持有 Shell、工作目录、进程组、权限和审计。

源码位于 [xsec-labs/xsec-plugin-system-terminal](https://github.com/xsec-labs/xsec-plugin-system-terminal)。
市场制品与 Factory 发布记录位于 [xsec-labs/xsec-plugins](https://github.com/xsec-labs/xsec-plugins)。
源码仓库保持 `beta` 开发、审查验证后合并 `main` 的发布流程。

## 包与契约

版本组合为 Terminal Host Service 2.0.0、Plugin API 1.9.0、插件 4.2.0。
`plugin.json` 声明 `^1.9.0`、一个 MCP Server、一个 Skill、8 个 parent/sub Agent Tool
绑定，以及安装和升级所需权限。`.codex-plugin/plugin.json` 与 Cargo package 使用相同插件版本。

工具为 `terminal_profiles`、`terminal_open`、`terminal_list`、`terminal_read`、
`terminal_write`、`terminal_resize`、`terminal_reveal`、`terminal_close`。
参数 schema 以 MCP `tools/list` 为准。

终端没有控制租约：用户、主 Agent 与子 Agent 都可以键入，write、resize、close 只带 `terminal_id`，
`terminal_open` 的结果里也没有 `control`。4.1.0 里留作过渡的 `terminal_control_status`、`terminal_control_acquire`、
`terminal_control_release` 三个工具和 `xsec.terminal.control.*` 三个前端方法已经删除，需要 Desktop 的对应版本
（主机不再提供这些方法）。
observer 通过 attach 与独立 cursor read 读取；界面卸载 detach，PTY 继续运行。
close 终止 PTY；会话结束、插件撤销或 Runtime 退出按 Host 生命周期回收资源。
结束的终端从面板列表消失，但仍可由 `terminal_list` 列出、由 `terminal_read` 读到输出，直到 `terminal_open` 在每会话 8 条已满时把它淘汰（先淘汰最早打开的已结束条目）。

## 构建与验证

前端位于 `com.xsec.desktop/frontend/index.js`。它就是可读的 ESM 源码，没有打包、压缩或转译步骤，
评审与 Marketplace 校验读到的正是运行时执行的代码。`mcp.json` 引用平台匹配的
`bin/system-terminal-mcp`（Windows 为 `.exe`），执行上下文由 Host 提供。

在工作区先运行资源控制器的 status 与 changed plan，再通过统一构建槽执行所选命令。
复用共享 Cargo target。sidecar 的构建入口为：

```sh
rtk pnpm build:mcp
```

开发 sidecar 与发布制品分别由对应构建流程生成。Desktop 的
`plugin:system-terminal:pack` 和 `test:system-terminal-artifact` 负责平台包与完整性检查。
Host/API 与插件成套升级。Windows、Linux、macOS arm64/x86_64 按受影响边界选择实际验收目标。
当前导入候选的验证状态见迁移预检记录；发布前须完成接收仓库的门禁与实际 Host/Agent 验收。
