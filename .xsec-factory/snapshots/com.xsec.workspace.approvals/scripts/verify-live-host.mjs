// Run inside a real Desktop Debug WebView with the disposable SQLite fixture.
function assert(value, message) { if (!value) throw new Error(message); }
const PAGE_SIZE = 40;
const TEST_TIMEOUT_MS = 10_000;

class LiveHostCheck {
  constructor(options) { this.options = options; this.bound = { sessionId: options.sessionId }; this.requests = []; }
  context() { return { kind: "workspace-tool", workspace: { binding: { sessionId: this.bound.sessionId } } }; }
  async setup() {
    const invoke = window.__TAURI__.core.invoke;
    this.plugin = (await invoke("plugin_installed_manifests")).find((entry) => entry.plugin_id === "com.xsec.workspace.approvals");
    assert(this.plugin?.trust === "official-development", "Attach the Approvals development workspace first");
    this.bound.sha = this.plugin.sha256;
    const loaded = await invoke("plugin_frontend_load", { pluginId: this.plugin.plugin_id, expectedSha256: this.bound.sha });
    const url = URL.createObjectURL(new Blob([loaded.source], { type: "text/javascript" }));
    try { this.module = await import(url); } finally { URL.revokeObjectURL(url); }
    this.root = document.createElement("div"); this.root.id = "approval-host-regression"; document.body.append(this.root);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    this.host = { context: this.context(), request: (method, params) => this.request(method, params), onTheme(listener) {
      const receive = () => listener({ "color-mode": media.matches ? "dark" : "light" });
      media.addEventListener("change", receive); return { dispose() { media.removeEventListener("change", receive); } };
    } };
    this.page = this.module.activate(this.host); await this.page.mount(this.root, this.context());
    assert(this.page.state.stats?.approval_request_count === this.options.expectedCount, "Host is not using the fixture database");
  }
  request(method, params) {
    this.requests.push({ method, params });
    return window.__TAURI__.core.invoke("plugin_frontend_rpc", { pluginId: this.plugin.plugin_id, expectedSha256: this.bound.sha, sessionId: method.startsWith("xsec.approvals.settings.") ? undefined : this.bound.sessionId, method, params });
  }
  settled(predicate) {
    return new Promise((resolve, reject) => {
      const observer = new MutationObserver(() => { if (predicate()) { observer.disconnect(); clearTimeout(timer); resolve(); } });
      const timer = setTimeout(() => { observer.disconnect(); reject(new Error("UI state did not settle")); }, TEST_TIMEOUT_MS);
      observer.observe(this.root, { childList: true, subtree: true, attributes: true, characterData: true });
      if (predicate()) { observer.disconnect(); clearTimeout(timer); resolve(); }
    });
  }
  async pagination() {
    const { page, options } = this; const ids = []; const counts = [];
    while (true) {
      counts.push(page.state.rows.length); ids.push(...page.state.rows.map((row) => row.id));
      if (!page.state.nextCursor) break;
      page.controls.next.click(); await this.settled(() => !page.state.refreshInFlight);
    }
    assert(JSON.stringify(counts) === JSON.stringify([PAGE_SIZE, PAGE_SIZE, options.expectedCount - PAGE_SIZE * 2]), "Unexpected page sizes");
    assert(ids.length === options.expectedCount && new Set(ids).size === ids.length, "Pagination duplicated or lost equal-timestamp records");
    assert(page.controls.next.disabled, "Last-page navigation must be disabled");
    page.controls.previous.click(); await this.settled(() => !page.state.refreshInFlight);
    assert(page.state.pageIndex === 1 && page.state.rows[0].id === ids[PAGE_SIZE], "Previous page lost its cursor");
    page.controls.refresh.click(); await this.settled(() => !page.state.refreshInFlight);
    assert(page.state.pageIndex === 0 && page.controls.previous.disabled, "Manual refresh must reset pagination");
    return counts;
  }
  async details() {
    const { page, options } = this; const row = page.state.rows.find((value) => value.request_id === options.longRequestId);
    assert(row, "Long-detail fixture must sort into page one");
    await page.openDetail(row);
    assert(page.controls.drawer.textContent.includes(options.expectedArgumentSuffix), "UTF-8 detail was truncated");
    const detailRequests = this.requests.filter((entry) => entry.method === "xsec.approvals.detail");
    assert(detailRequests.length > 1 && detailRequests[1].params.revision, "Detail must use revision-pinned chunks");
    page.closeDetail();
    const refresh = page.refresh({ silent: true }); const detail = page.openDetail(row); await Promise.all([refresh, detail]);
    assert(!page.controls.drawer.hidden, "An in-flight automatic refresh closed the detail");
    page.closeDetail(); const pending = page.openDetail(row); page.closeDetail(); await pending;
    assert(page.controls.drawer.hidden, "Closed detail reappeared after its response");
    return detailRequests.length;
  }
  async filters() {
    const { page } = this; const select = this.root.querySelector("select"); select.value = "denied"; select.dispatchEvent(new Event("change"));
    await this.settled(() => !page.state.refreshInFlight);
    assert(page.state.pageIndex === 0 && page.state.rows.every((row) => row.decision === "denied"), "Decision filter failed");
    const input = this.root.querySelector("input[type=search]"); input.value = this.options.toolName; input.dispatchEvent(new Event("input"));
    await this.settled(() => Boolean(page.state.rows) && !page.state.refreshInFlight);
    assert(page.state.rows.length === 1 && page.state.rows[0].tool_name === this.options.toolName, "Tool filter failed");
    select.value = ""; select.dispatchEvent(new Event("change")); input.value = ""; input.dispatchEvent(new Event("input"));
    await this.settled(() => page.state.rows?.length === PAGE_SIZE && !page.state.refreshInFlight);
    this.root.querySelector('[data-value="24h"]').click(); await this.settled(() => !page.state.refreshInFlight);
    const since = page.state.sinceMs; page.controls.next.click(); await this.settled(() => !page.state.refreshInFlight);
    assert(page.state.sinceMs === since, "Time window moved during pagination");
    this.root.querySelector('[data-value="all"]').click(); await this.settled(() => !page.state.refreshInFlight);
  }
  async sessions() {
    const { page } = this; const pending = page.refresh(); const detail = page.openDetail(page.state.rows[0]);
    this.bound.sessionId = this.options.otherSessionId;
    await Promise.all([pending, detail, page.update(this.context())]);
    assert(page.state.rows.length === 1 && page.state.rows[0].session_id === this.bound.sessionId, "Old session response leaked into new session");
    assert(page.controls.drawer.hidden, "Session change left the old detail open");
    this.bound.sessionId = undefined; await page.update(this.context());
    assert(!page.state.rows && !page.controls.refresh.disabled && page.controls.status.textContent.includes("进入会话"), "Unbound session remained busy");
    this.bound.sessionId = this.options.sessionId; await page.update(this.context());
    const foreign = this.request("xsec.approvals.detail", { requestId: this.options.foreignRequestId, offset: 0 });
    await foreign.then(() => { throw new Error("Cross-session detail was accepted"); }, (error) => assert(String(error).length > 0, "Missing host error"));
  }
  async failures() {
    const { page } = this; this.bound.sha = "0".repeat(this.plugin.sha256.length); await page.refresh();
    assert(!page.state.rows && !page.state.stats && !page.state.autoRefresh && page.controls.status.dataset.tone === "error", "Host failure must clear data and pause refresh");
    this.bound.sha = this.plugin.sha256; page.controls.refresh.click(); await this.settled(() => !page.state.refreshInFlight);
    assert(page.state.rows.length === PAGE_SIZE && page.controls.status.textContent === "", "Explicit refresh did not recover");
    const pending = page.openDetail(page.state.rows[0]); page.dispose(); await pending;
    assert(page.controls.drawer.hidden, "Disposed detail reappeared");
    await page.mount(this.root, this.context()); assert(page.state.rows.length === PAGE_SIZE, "Remount failed");
  }
  async settings() {
    this.page.dispose(); const host = { ...this.host, context: { kind: "settings-page" } }; this.page = this.module.activate(host);
    this.page.mount(this.root, host.context); await this.settled(() => this.page.settingsReady);
    assert(!this.page.controls.save.disabled, "Settings read failed after lifecycle extraction");
    await this.page.save(); assert(this.page.controls.notice.textContent.startsWith("已保存"), "Settings save failed");
  }
  dispose() { this.page?.dispose(); this.root?.remove(); }
}

export async function verifyLiveHost(options) {
  const check = new LiveHostCheck(options);
  try {
    await check.setup(); const pages = await check.pagination(); const detailChunks = await check.details();
    await check.filters(); await check.sessions(); await check.failures(); await check.settings();
    return { passed: true, version: check.plugin.version, sha256: check.plugin.sha256, pages, detailChunks, checks: ["filters", "sessions", "cross-session rejection", "error recovery", "remount", "settings read/save"] };
  } finally { check.dispose(); }
}
