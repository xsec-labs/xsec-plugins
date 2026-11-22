# Official plugin bridge

This package owns the signed plugin manifest, permissions and release lifecycle. XSEC Desktop currently binds its compatible built-in renderer only after this package is installed and enabled. The bridge is intentionally explicit so package state, rather than the application installer, is the source of truth.

## 设置审查

默认终端配置位于“设置 → 插件 → 系统终端”，仅影响后续新建的 PTY。Windows
提供 CMD、Windows PowerShell 和 PowerShell 7 中已安装的选项；macOS 与 Linux
使用当前帐户的登录 Shell。终端主界面显示 PTY 内容和真实错误。界面与设置区均跟随
XSEC Desktop 的深色或浅色外观。详见
[插件设置规范](https://github.com/xsec-labs/xsec-plugins/blob/main/docs/plugin-settings.md)。

The root manifest uses Agent Plugins v1 with a `com.xsec.desktop` schema v3
extension. System Terminal declares eight `agentTools` for the `parent` and
`sub` roles, a stdio `mcp.json` entry and the portable `system-terminal` Skill.
Shell selection, PTY lifecycle, working directory, process execution, and audit
stay behind the Desktop capability and session boundary.

## Agent 工具边界

Agent 工具是 Host 能力的转发入口，不是新的执行面。`system-terminal-mcp` 不打开 PTY、
不启动 Shell，也不保存终端状态：

- 启动时必须带有 `XSEC_PLUGIN_HOST_RPC_ENDPOINT`，缺少它时进程直接退出。
- 每次工具调用先经 `xsec.terminal.context` 取得会话身份（会话 ID、角色、制品哈希、
  能力哈希和允许的工具列表），校验通过后才转发。
- 不在 `allowedTools` 中的工具在 sidecar 内即被拒绝，不会发往 Host。
- 参数原样转发，由 Host 校验；全部终端进程的生命周期由 Host 持有。
