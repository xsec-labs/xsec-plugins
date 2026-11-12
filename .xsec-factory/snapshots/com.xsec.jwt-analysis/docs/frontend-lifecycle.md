# JWT 前端控制器生命周期

本轮以 `f159dcda672e03a19516f7741c1dfa139a466c9b` 为基线，修复 JWT 前端控制器的视图更新、销毁和轮询生命周期，并保持 Host RPC 契约一致。

## 原因与行为

Desktop sandbox bootstrap 等待 `controller.mount()` 完成，清理由 `controller.dispose()` 承担。基线 JWT 前端把清理函数作为 `mount()` 的返回值；Host 不使用该返回值，而原有 `dispose()` 仅记录日志，因此轮询继续运行。控制器也缺少上下文更新入口。

控制器现在通过一个 `AbortController` 拥有当前视图、事件监听器、轮询和报告 URL。`update(context)` 先取消旧视图，再渲染新的项目或设置页面；`dispose()` 取消视图并清空挂载节点。异步结果写入 DOM 前检查取消状态，任务刷新同时检查 revision，防止旧请求覆盖当前视图。成功刷新后安排下一次轮询；请求错误继续传播，并停止轮询，等待用户显式刷新或切换任务。

六个 JWT Host RPC 方法继续使用现有名称和参数：`xsec.jwt-analysis.jobs.list`、`xsec.jwt-analysis.jobs.get`、`xsec.jwt-analysis.jobs.events`、`xsec.jwt-analysis.evidence.get`、`xsec.jwt-analysis.report`、`xsec.jwt-analysis.diagnostics`。调用使用直接字符串字面量，供官方前端源码门禁校验。manifest 权限、协议及依赖锁保持原状。本轮增加手动真实浏览器回归工具；运行依赖保持原状。

## 已执行验证

真实浏览器运行前端模块、DOM 和计时器，通过 loopback HTTP 访问隔离的真实 SQLite Store。五个场景分别为项目更新、挂载完成后销毁、挂载等待期间销毁、挂载等待期间更新和刷新失败。失败场景通过对隔离数据库执行真实 `ALTER TABLE` 触发查询错误。五项在基线全部失败，在修复版本全部通过；观察窗口验证销毁及刷新失败后停止轮询。

实际验证命令经工作区构建资源控制器执行：

```sh
rtk python3 /Volumes/xsec-build/evidence/2026-10-20-jwt-frontend-lifecycle/check_inputs.py
rtk python3 scripts/verify_package.py
```

两条命令均通过。检查包括浏览器输入哈希、五项基线失败与五项当前通过、JavaScript/Python 语法、完整 JWT 官方前端源码门禁、diff 检查，以及 manifest、RockYou、SBOM 许可证和包大小。手动浏览器运行说明见 `tests/browser_lifecycle/README.md`。

本轮真实边界为浏览器、HTTP 和隔离 SQLite。Desktop 原生 Host、授权及 MCP 传输仍需独立验收；设置保存和报告下载也尚未单独验收。原生平台矩阵和发布验收待后续执行。

## 证据与资源

证据目录为 `/Volumes/xsec-build/evidence/2026-10-20-jwt-frontend-lifecycle`：

- `browser-results.json`、`browser-tested-inputs.json` 和 `browser-final-explicit-methods-result.jpg` 记录浏览器结果、输入和最终画面；测试数据库位于该目录。
- `validation-report.json`、`final-validation-output.log` 与 `full-frontend-gate-report.json` 记录通过的验证；`initial-full-frontend-gate-failure.json` 保留RPC 调用改动前的失败证据。
- `browser-resource-report.json`：run `6dd49326-a279-41ea-81d3-0c9a1dfc04e6`，耗时 35.269 秒，峰值 RSS 82,788,352 字节，磁盘增长 53,248 字节。
- `validation-report.json`：run `f0878aab-813b-4448-8ac8-7249698af4a1`，耗时 2.832 秒，磁盘增长 24,576 字节；命令 RSS 采样未捕获有效峰值，报告中的 0 不代表实际内存为零。

两次资源报告均为 `sourceChanged=false`，swap 前后均为 2,339,897,344 字节。共享缓存目标为 `/Volumes/xsec-build/.worktree-cache/build-resources/targets/bf11de21084a99184d859955044049e418c6b82da29c329a7c2ec84f0c4bba59`。`resources-final.json` 回读为 `lease=null`、`foreignBuilds=[]`。本地 clone 总占用 106,488 KiB，属于目录总量，磁盘增量以对应资源报告为准。

## 本地集成、发布与回滚

交付范围为控制器、说明文档和浏览器回归工具。Factory 候选仍固定基线 JWT 源码；本地集成后，需在发布授权覆盖下更新 Factory pin、重新装配并验收候选包，才能确认此修复进入发布链路。

本轮未改变持久化数据格式。回滚本任务提交可使用 `rtk git revert <本任务提交>`；浏览器数据库为证据目录中的隔离测试数据。上线前仍需完成上述 Host 与功能验收。
