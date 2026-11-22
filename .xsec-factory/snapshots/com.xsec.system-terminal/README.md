# com.xsec.system-terminal

This is the public source repository for `com.xsec.system-terminal`. It was materialized from
the immutable signed XSEC Marketplace release during the first-party source
migration. Develop on `beta`; merge reviewed, tested changes to `main` for the
Stable source line.

Marketplace artifacts, release indexes, signatures, and Factory adoption proof
remain in [xsec-labs/xsec-plugins](https://github.com/xsec-labs/xsec-plugins).
This source repository never stores Factory credentials or KMS material.

Source repository: <https://github.com/xsec-labs/xsec-plugin-system-terminal>

## 系统终端行为

- 终端工作区跟随 XSEC Desktop 的深色或浅色外观，并在启动、读取、写入或调整
  尺寸失败时显示实际错误。
- Windows 设置页提供 CMD、Windows PowerShell 和 PowerShell 7 中当前可用的
  Shell；macOS 与 Linux 使用当前帐户的登录 Shell。
- 设置读取失败时保留实际错误，并提供页内重试；读取恢复后继续使用同一设置与保存流程。

## Agent 工具与 Go sidecar

- 插件声明 8 个 Agent 工具（`terminal_profiles` 至 `terminal_close`），绑定 `parent` 与 `sub`
  角色。没有控制租约工具：Desktop B1 起终端没有控制租约。
- `mcp.json` 启动随包分发的 stdio 服务 `./bin/system-terminal-mcp`。它由 XSEC Desktop 仓库的
  `go/cmd/system-terminal-mcp` 以 Go 编译，本仓库不含 Rust 或 Cargo 源码。
- 构建制品：在 XSEC Desktop 仓库中运行
  `node scripts/plugins/build-system-terminal-artifact.mjs --source <本仓库路径> --out <输出文件>`，
  可加 `--target linux-amd64`、`windows-amd64` 或 `darwin-arm64` 指定平台。
