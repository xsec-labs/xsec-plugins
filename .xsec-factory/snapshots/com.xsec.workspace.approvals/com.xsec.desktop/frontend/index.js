// XSEC Frontend API v2 — single-file ESM.  All data comes through the
// manifest-declared broker methods; the iframe has no direct Tauri access.
const DECISIONS = { allowed: ["允许", "success"], denied: ["拒绝", "danger"], manual_review: ["人工审批", "warning"], bypass: ["绕过", "volcano"], error: ["错误", "magenta"] };
const FILTER_DECISIONS = ["allowed", "denied", "manual_review", "bypass", "error"];
const RISKS = { low: "低", medium: "中", high: "高", critical: "严重" };
const MODES = { manual: "人工", auto_llm: "LLM", full_access: "完全访问" };
const WINDOWS = [["all", "全部"], ["24h", "24 小时"], ["7d", "7 天"], ["30d", "30 天"]];
const WINDOW_MS = { "24h": 86_400_000, "7d": 604_800_000, "30d": 2_592_000_000 };
const MIN_CONFIDENCE = 0;
const MAX_CONFIDENCE = 1;
const MIN_TIMEOUT_MS = 1_000;
const AUTO_REFRESH_INTERVAL_MS = 15_000;
const PAGE_SIZE = 40;
const FILTER_DEBOUNCE_MS = 250;
const FULL_ACCESS_CONFIRMATION = "我确认启用完全访问权限";
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function isRecord(value) { return Boolean(value) && typeof value === "object" && !Array.isArray(value); }
function text(value) { return value === undefined || value === null || value === "" ? "—" : String(value); }
function errorText(error) { return error instanceof Error ? error.message : String(error); }
function logFailure(event, error) { console.error(event, { message: errorText(error) }); }
function sessionIdFrom(context) {
  const id = context?.workspace?.session?.session_id || context?.workspace?.binding?.sessionId;
  return typeof id === "string" && id.trim() ? id : undefined;
}
function formatTime(value) {
  const stamp = typeof value === "number" ? value : Date.parse(String(value));
  return Number.isFinite(stamp) ? new Date(stamp).toLocaleString("zh-CN") : "—";
}
function decisionInfo(row) {
  const value = row.final_decision || row.decision || "未知";
  return DECISIONS[value] || [value, "neutral"];
}
function applyTheme(theme) {
  const mode = theme?.["color-mode"] || getComputedStyle(document.documentElement).getPropertyValue("--xsec-color-mode").trim();
  document.documentElement.dataset.xsecTheme = mode === "light" ? "light" : "dark";
}
function isNumericSetting(value) { return typeof value === "number" && Number.isFinite(value); }
function validLlm(llm) { return isRecord(llm) && typeof llm.use_default_model === "boolean" && (llm.use_default_model || typeof llm.model === "string") && isNumericSetting(llm.timeout_ms) && Number.isSafeInteger(llm.timeout_ms) && llm.timeout_ms >= MIN_TIMEOUT_MS; }
function validSettings(settings) {
  const threshold = Number(settings?.low_confidence_threshold);
  return isRecord(settings) && validLlm(settings.llm)
    && typeof settings.auto_enabled === "boolean" && typeof settings.full_access === "boolean" && typeof settings.allow_local_readonly === "boolean"
    && isNumericSetting(settings.low_confidence_threshold) && threshold >= MIN_CONFIDENCE && threshold <= MAX_CONFIDENCE;
}
function applySettings(controls, settings) {
  if (!validSettings(settings)) throw new Error("审批设置响应无效");
  controls.auto.checked = settings.auto_enabled; controls.full.checked = settings.full_access; controls.risk.hidden = !settings.full_access;
  controls.acknowledge.checked = false; controls.confirm.value = ""; controls.readonly.checked = settings.allow_local_readonly;
  controls.threshold.value = String(settings.low_confidence_threshold); controls.model.value = settings.llm.use_default_model ? "" : settings.llm.model;
  controls.timeout.value = String(settings.llm.timeout_ms);
}
function showResolvedModel(controls, settings) {
  const value = settings?.resolved_model;
  controls.modelStatus.textContent = value?.error ? `模型状态：${value.error}` : value?.model
    ? `模型状态：${value.provider || "默认服务商"} / ${value.model}（${value.api_key_available ? "凭据可用" : "凭据不可用"}）`
    : `模型状态：${settings?.api_key_configured ? "使用当前会话模型" : "尚未配置固定审批模型"}`;
}
function showSettingsOverview(controls, settings) {
  const model = settings?.llm?.use_default_model ? "跟随当前会话模型" : (settings?.llm?.model || "未配置");
  const values = [["新会话默认模式", settings?.auto_enabled ? "LLM 自动审批" : "人工审批"], ["完全访问授权", settings?.full_access ? "已授权，可显式选择" : "未授权"], ["审批模型策略", model]];
  controls.summary.replaceChildren(); for (const [label, value] of values) controls.summary.append(detailValue(label, value));
}
function settingsContextKey(context) {
  const settings = isRecord(context?.settings) ? context.settings : {};
  return JSON.stringify([context?.kind, settings.id, settings.page]);
}
function addStyles(root) {
  const style = element("style");
  style.textContent = `:root{font:13px/1.45 var(--xsec-font-family,system-ui,sans-serif)}.xsec-approvals,.approval-settings{--bg:#0f141b;--surface:#111924;--control:#18212d;--line:#303b4c;--strong:#d7dee8;--muted:#9aa7b7;--hover:#202d3c;--error:#ff8e8e;min-height:100%;color:var(--strong);background:var(--bg)}:root[data-xsec-theme=light] .xsec-approvals,:root[data-xsec-theme=light] .approval-settings{--bg:#f7f9fc;--surface:#fff;--control:#fff;--line:#d7dee8;--strong:#18212d;--muted:#66758a;--hover:#edf3fb;--error:#bd3030}.xsec-approvals *,.approval-settings *{box-sizing:border-box}.xsec-approvals{padding:12px}.approval-card{border:1px solid var(--line);border-radius:8px;background:var(--surface);padding:10px;margin-bottom:12px}.approval-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.approval-stat{min-width:0;padding:8px;border:1px solid var(--line);border-radius:7px}.approval-label,.approval-meta,.approval-status{color:var(--muted);font-size:12px}.approval-value{overflow:hidden;margin-top:2px;font-size:18px;font-weight:650;text-overflow:ellipsis;white-space:nowrap}.approval-card-head,.approval-row-title,.approval-toolbar{display:flex;align-items:center;gap:8px}.approval-card-head{justify-content:space-between;margin-bottom:10px}.approval-card-title{margin:0;font-size:14px}.approval-toolbar{flex-wrap:wrap;margin-bottom:9px}.approval-button,.approval-select,.approval-input{border:1px solid var(--line);border-radius:6px;padding:5px 8px;color:var(--strong);background:var(--control);font:inherit}.approval-button{cursor:pointer}.approval-button:disabled{cursor:wait;opacity:.65}.approval-window[aria-pressed=true]{border-color:#4f7cff;color:#fff;background:#25457a}.approval-status{min-height:20px;margin:0 0 8px}.approval-status[data-tone=error]{color:var(--error)}.approval-list{display:grid;gap:7px}.approval-row{width:100%;padding:9px;border:1px solid var(--line);border-radius:7px;color:var(--strong);background:var(--surface);font:inherit;text-align:left;cursor:pointer}.approval-row:hover{background:var(--hover)}.approval-row-title{justify-content:space-between}.approval-preview{display:block;overflow:hidden;margin:4px 0;color:var(--muted);text-overflow:ellipsis;white-space:nowrap}.approval-badge{flex:none;border-radius:999px;padding:1px 6px;font-size:11px}.success{color:#82e6a8;background:#163a29}.warning{color:#ffd17a;background:#453318}.danger{color:#ff9999;background:#4a2027}.volcano{color:#ffb17a;background:#4a2d20}.magenta{color:#ff9cd5;background:#48213d}.neutral{color:var(--muted);background:var(--hover)}.approval-empty{padding:22px 10px;border:1px dashed var(--line);border-radius:7px;color:var(--muted);text-align:center}.approval-drawer{position:fixed;z-index:10;inset:0;display:grid;justify-items:end;background:#0007}.approval-drawer[hidden]{display:none}.approval-drawer-panel{width:min(560px,100%);height:100%;overflow:auto;padding:14px;background:var(--bg);box-shadow:-8px 0 26px #0004}.approval-drawer-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.approval-details{display:grid;gap:0;margin:12px 0}.approval-details div{padding:8px;border:1px solid var(--line);border-bottom:0}.approval-details div:last-child{border-bottom:1px solid var(--line)}.approval-details dt{margin-bottom:4px;color:var(--muted)}.approval-details dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.approval-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.approval-settings{max-width:760px;min-height:100vh;padding:18px}.approval-settings h1{margin:0;font-size:20px}.approval-settings p{color:var(--muted)}.approval-settings label{display:grid;gap:6px;margin:14px 0}.approval-settings .check{display:flex;align-items:center;gap:8px}.approval-model-status{padding:8px;border-left:3px solid #4f7cff;background:var(--surface)}@media(max-width:300px){.approval-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}`;
  root.append(style);
}
function detailValue(label, value, code = false) {
  const item = element("div"); const title = element("dt", "", label); const body = element("dd", code ? "approval-code" : "", text(value));
  item.append(title, body); return item;
}
function policyValue(value) {
  try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed.join("、") : value; } catch { return value; }
}
function confidence(value) { return value == null ? undefined : `${(Number(value) * 100).toFixed(1)}%`; }
function latency(value) { return value == null ? undefined : `${value} ms`; }
function detailContent(row) {
  const [label, tone] = decisionInfo(row);
  const items = [["请求 ID", row.request_id, true], ["工具", row.tool_name], ["最终决策", label], ["自动审批决定", row.gateway_decision ? (DECISIONS[row.gateway_decision]?.[0] || row.gateway_decision) : undefined], ["决定来源", row.resolution_source], ["风险等级", row.risk_level ? (RISKS[row.risk_level] || row.risk_level) : undefined], ["审批模式", MODES[row.mode] || row.mode], ["命令", row.command_preview, true], ["工作目录", row.cwd, true], ["参数", row.arguments_preview, true], ["自动审批原因", row.gateway_reason || row.reason], ["自动审批指引", row.gateway_guidance || row.agent_guidance], ["人工最终原因", row.final_reason], ["模型失败码", row.llm_failure_code], ["命中策略", row.policy_codes_json ? policyValue(row.policy_codes_json) : undefined], ["审批模型", row.model_name], ["置信度", confidence(row.model_confidence)], ["耗时", latency(row.model_latency_ms)], ["执行状态", row.execution_status], ["执行错误", row.execution_error], ["审批时间", row.approval_started_at == null ? undefined : formatTime(row.approval_started_at)]];
  return { label, tone, items: items.filter(([, value]) => value !== undefined && value !== null && value !== "") };
}
function renderDetail(row) {
  const { label, tone, items } = detailContent(row); const details = element("dl", "approval-details");
  for (const [title, value, code] of items) if (value !== undefined && value !== null && value !== "") details.append(detailValue(title, value, code));
  const decision = element("span", `approval-badge ${tone}`, label); return { decision, details };
}
function validSummary(row, session) {
  return isRecord(row) && row.session_id === session && typeof row.request_id === "string" && Boolean(row.request_id) && typeof row.id === "string" && Boolean(row.id) && Number.isSafeInteger(row.created_at);
}
export function validatePage(page, session) {
  if (!isRecord(page) || !Array.isArray(page.rows) || page.rows.some((row) => !validSummary(row, session))) throw new Error("审批列表分页数据无效");
  const cursor = page.nextCursor; const last = page.rows.at(-1);
  if (cursor !== null) validateCursor(cursor, last);
  return page;
}
function validateCursor(cursor, last) {
  if (!isRecord(cursor) || !Number.isSafeInteger(cursor.createdAt) || cursor.createdAt < 0 || !last || cursor.id !== last.id || cursor.createdAt !== last.created_at) throw new Error("审批列表分页游标无效");
}
function validateRevision(value, revision) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value) || (revision && value !== revision)) throw new Error("审批详情分片版本无效");
}
export function validateChunk(chunk, offset, revision) {
  if (!isRecord(chunk) || typeof chunk.data !== "string" || !chunk.data) throw new Error("审批详情分片数据无效");
  validateRevision(chunk.revision, revision); const end = offset + new TextEncoder().encode(chunk.data).length;
  if (chunk.nextOffset !== null && (!Number.isSafeInteger(chunk.nextOffset) || chunk.nextOffset !== end)) throw new Error("审批详情分片位置无效");
  return chunk;
}
function validThreshold(value) { return Boolean(value) && Number.isFinite(Number(value)) && Number(value) >= MIN_CONFIDENCE && Number(value) <= MAX_CONFIDENCE; }
function validTimeout(value) { return Boolean(value) && Number.isSafeInteger(Number(value)) && Number(value) >= MIN_TIMEOUT_MS; }
class SettingsPage {
  constructor(api) { this.api = api; this.settingsReady = false; this.loadRevision = 0; this.contextKey = settingsContextKey(api.context); this.disposed = false; this.lifecycleRevision = 0; }
  notice(message, failed = false) { this.controls.notice.textContent = message; this.controls.notice.dataset.tone = failed ? "error" : ""; }
  async readSettings() {
    try { return await this.api.readSettings(); }
    catch (error) { logFailure("approvals.settings.load.failed", error); throw error; }
  }
  async writeSettings(input) {
    try { return await this.api.writeSettings(input); }
    catch (error) { logFailure("approvals.settings.save.failed", error); throw error; }
  }
  async load() {
    if (this.activeSave) { this.activeSave.reloadQueued = true; this.controls.retry.disabled = true; return; }
    const revision = ++this.loadRevision;
    this.settingsReady = false; this.controls.save.disabled = true; this.controls.retry.disabled = true; this.notice("正在读取审批设置…");
    console.info("approvals.settings.load.started");
    try {
      const settings = await this.readSettings();
      if (revision !== this.loadRevision) return;
      applySettings(this.controls, settings);
      showResolvedModel(this.controls, settings); showSettingsOverview(this.controls, settings); this.settingsReady = true; this.controls.save.disabled = false; this.notice("");
      console.info("approvals.settings.load.completed", { fullAccessEnabled: settings.full_access, usesDefaultModel: settings.llm.use_default_model });
    } catch (error) { if (revision === this.loadRevision) this.notice(`读取审批设置失败：${errorText(error)}`, true); } finally { if (revision === this.loadRevision) this.controls.retry.disabled = false; }
  }
  saveInput() {
    const controls = this.controls; const fullAccess = controls.full.checked; const acknowledged = fullAccess && controls.confirm.value === FULL_ACCESS_CONFIRMATION;
    const threshold = controls.threshold.value.trim(); const timeout = controls.timeout.value.trim();
    if (!validThreshold(threshold)) throw new Error("低置信度阈值必须是 0 到 1 之间的数字。");
    if (!validTimeout(timeout)) throw new Error("模型超时必须是不小于 1000 毫秒的安全整数。");
    if (fullAccess && (!acknowledged || !controls.acknowledge.checked)) throw new Error("启用完全访问前，请确认风险声明并输入确认语句。");
    return { autoEnabled: controls.auto.checked, fullAccess, allowLocalReadonly: controls.readonly.checked, lowConfidenceThreshold: Number(threshold), llm: { model: controls.model.value.trim(), timeoutMs: Number(timeout), temperature: 0 }, fullAccessAcknowledged: acknowledged };
  }
  isActiveSave(save) { return this.activeSave === save && save.revision === this.loadRevision && !this.disposed && save.lifecycle === this.lifecycleRevision; }
  finishSave(save) {
    if (this.activeSave !== save) return;
    this.activeSave = undefined;
    if (save.reloadQueued && !this.disposed) void this.load();
    else if (!this.disposed && save.lifecycle === this.lifecycleRevision && save.revision === this.loadRevision) { this.controls.save.disabled = !this.settingsReady; this.controls.retry.disabled = false; }
  }
  async save() {
    if (!this.settingsReady) return this.notice("请先成功读取当前审批设置后再保存。", true);
    let input; try { input = this.saveInput(); } catch (error) { this.notice(errorText(error), true); return; }
    this.controls.save.disabled = true; this.controls.retry.disabled = true;
    const saveState = { lifecycle: this.lifecycleRevision, reloadQueued: false, revision: ++this.loadRevision }; this.activeSave = saveState; console.info("approvals.settings.save.started", { fullAccessEnabled: input.fullAccess });
    try {
      const settings = await this.writeSettings(input); if (!this.isActiveSave(saveState)) return;
      applySettings(this.controls, settings); showResolvedModel(this.controls, settings); showSettingsOverview(this.controls, settings); this.settingsReady = true;
      this.notice("已保存。审批授权和只读放行立即生效；新会话默认策略仅影响之后创建的会话。"); console.info("approvals.settings.save.completed", { fullAccessEnabled: settings.full_access, usesDefaultModel: settings.llm.use_default_model });
    } catch (error) { if (this.isActiveSave(saveState)) this.notice(`保存审批设置失败：${errorText(error)}`, true); } finally { this.finishSave(saveState); }
  }
  field(title, input) { const label = element("label", "", title); label.append(input); return label; }
  build() {
    this.root.replaceChildren(); addStyles(this.root); const page = element("main", "approval-settings");
    const auto = element("input"); auto.type = "checkbox"; const full = element("input"); full.type = "checkbox"; const readonly = element("input"); readonly.type = "checkbox"; const acknowledge = element("input"); acknowledge.type = "checkbox";
    const threshold = element("input", "approval-input"); threshold.type = "number"; threshold.min = "0"; threshold.max = "1"; threshold.step = "0.05";
    const model = element("input", "approval-input"); model.placeholder = "留空使用当前会话模型"; const timeout = element("input", "approval-input"); timeout.type = "number"; timeout.min = "1000"; timeout.step = "1000";
    const confirm = element("input", "approval-input"); confirm.placeholder = `启用完全访问时输入：${FULL_ACCESS_CONFIRMATION}`;
    const summaryCard = element("section", "approval-card"); const summary = element("dl", "approval-details"); summaryCard.append(element("h2", "approval-card-title", "审批策略"), summary);
    const saveButton = element("button", "approval-button", "保存设置"); const retryButton = element("button", "approval-button", "重新读取设置"); const status = element("p", "approval-model-status"); const note = element("p", "approval-status"); saveButton.disabled = true;
    const check = (input, label) => { const node = element("label", "check"); node.append(input, document.createTextNode(label)); return node; };
    const risk = element("section", "approval-card"); const riskTitle = element("strong", "", "完全访问确认"); const riskDetail = element("p", "", "启用后，普通会话、批量任务和资产发现可以显式选择完全访问。系统危险规则、工作区写入沙箱和审计仍然生效。请仅在目标与操作均已获得授权时继续。");
    risk.append(riskTitle, riskDetail, check(acknowledge, "我已了解上述风险，并确认当前操作仅用于合法且已获得授权的目标。"), this.field("请输入确认语句", confirm)); risk.hidden = true;
    const updateRisk = () => { risk.hidden = !full.checked; if (!full.checked) { acknowledge.checked = false; confirm.value = ""; } };
    saveButton.onclick = () => void this.save(); retryButton.onclick = () => void this.load();
    full.onchange = updateRisk;
    page.append(element("h1", "", "审批记录"), element("p", "", "新会话默认策略影响后续创建的普通会话；完全访问是全局可选上限，当前会话的模式仍在任务界面管理。"), summaryCard, check(auto, "新会话默认使用 LLM 自动审批"), check(full, "允许选择完全访问（高风险）"), risk, check(readonly, "本地只读调用直接放行"), this.field("低置信度阈值", threshold), this.field("审批模型（留空跟随当前会话模型）", model), status, this.field("模型超时（毫秒）", timeout), saveButton, retryButton, note);
    this.root.append(page); this.controls = { auto, full, readonly, threshold, model, timeout, confirm, acknowledge, risk, summary, save: saveButton, retry: retryButton, modelStatus: status, notice: note }; updateRisk(); retryButton.disabled = Boolean(this.activeSave); console.info("approvals.settings.mount"); if (this.activeSave) this.activeSave.reloadQueued = true; else void this.load();
  }
  mount(root, context) { this.themeSubscription?.dispose(); this.disposed = false; this.lifecycleRevision += 1; this.root = root; this.contextKey = settingsContextKey(context); this.build(); applyTheme({}); this.themeSubscription = this.api.onTheme((theme) => applyTheme(theme)); }
  update(context) { const key = settingsContextKey(context); if (key === this.contextKey) return; this.contextKey = key; if (this.activeSave?.lifecycle === this.lifecycleRevision) { this.activeSave.reloadQueued = true; return; } return this.load(); }
  dispose() { console.debug("approvals.settings.dispose"); this.disposed = true; this.lifecycleRevision += 1; if (this.activeSave) this.activeSave.reloadQueued = false; this.themeSubscription?.dispose(); }
}
class WorkspacePage {
  constructor(api) {
    this.api = api; this.context = api.context;
    this.state = { session: undefined, revision: 0, rows: undefined, stats: undefined, autoRefresh: false, detailRequestId: undefined, detailRevision: 0, cursors: [null], pageIndex: 0, nextCursor: null, sinceMs: undefined, refreshInFlight: false, disposed: false, tool: "", decision: "", window: "all" };
  }
  status(message, failed = false) { this.controls.status.textContent = message; this.controls.status.dataset.tone = failed ? "error" : ""; }
  showStats() {
    const { controls, state } = this; controls.summary.replaceChildren(); const stats = state.stats; const rate = stats ? `${(Number(stats.allow_rate) * 100).toFixed(1)}%` : "—";
    for (const [label, value] of [["总数", stats ? stats.approval_request_count : "—"], ["允许", stats ? stats.allowed_count : "—"], ["拒绝", stats ? stats.denied_count : "—"], ["人工", stats ? stats.manual_review_count : "—"], ["绕过", stats ? stats.bypass_count : "—"], ["放行率", rate]]) { const card = element("div", "approval-stat"); card.append(element("div", "approval-label", label), element("div", "approval-value", text(value))); controls.summary.append(card); }
  }
  closeDetail() { this.state.detailRequestId = undefined; this.state.detailRevision += 1; this.controls.drawer.hidden = true; this.controls.drawer.replaceChildren(); }
  showDetail(row) {
    const panel = element("section", "approval-drawer-panel"); const head = element("header", "approval-drawer-head"); const close = element("button", "approval-button", "关闭"); const view = renderDetail(row);
    close.onclick = () => this.closeDetail(); head.append(element("h2", "approval-card-title", "本会话审批详情"), close); panel.append(head, view.decision, view.details); this.controls.drawer.replaceChildren(panel); this.controls.drawer.hidden = false;
  }
  currentDetail(revision) { return revision === this.state.detailRevision && !this.state.disposed; }
  async openDetail(row) {
    const { state, controls, api } = this; this.closeDetail(); const revision = state.detailRevision; const session = state.session; state.detailRequestId = row.request_id;
    const panel = element("section", "approval-drawer-panel"); const close = element("button", "approval-button", "关闭"); close.onclick = () => this.closeDetail();
    const note = element("p", "approval-status", "正在加载审批详情…"); panel.append(close, note); controls.drawer.replaceChildren(panel); controls.drawer.hidden = false;
    console.info("approvals.workspace.detail.started");
    try {
      let offset = 0; let version; let serialized = "";
      do {
        const chunk = validateChunk(await api.detail({ requestId: row.request_id, offset, revision: version }), offset, version);
        if (!this.currentDetail(revision)) return;
        serialized += chunk.data; version = chunk.revision; offset = chunk.nextOffset;
      } while (offset !== null);
      const detail = JSON.parse(serialized);
      if (!isRecord(detail) || detail.session_id !== session || detail.request_id !== row.request_id || detail.id !== row.id) throw new Error("审批详情会话归属无效");
      this.showDetail(detail); console.info("approvals.workspace.detail.completed");
    } catch (error) {
      if (!this.currentDetail(revision)) return;
      logFailure("approvals.workspace.detail.failed", error); note.textContent = `加载审批详情失败：${errorText(error)}`; note.dataset.tone = "error";
    }
  }
  showRows() {
    const { controls, state } = this; controls.list.replaceChildren(); const rows = state.rows;
    if (!rows?.length) return controls.list.append(element("div", "approval-empty", rows ? "本会话暂无审批记录" : "尚未加载审批记录"));
    for (const row of rows) { const [label, tone] = decisionInfo(row); const card = element("button", "approval-row"); card.type = "button"; card.setAttribute("aria-label", `查看 ${text(row.tool_name)} 的审批详情`); const head = element("span", "approval-row-title"); const meta = [MODES[row.mode] || row.mode, row.risk_level ? `风险：${RISKS[row.risk_level] || row.risk_level}` : ""].filter(Boolean).join(" · "); head.append(element("strong", "", text(row.tool_name)), element("span", `approval-badge ${tone}`, label)); card.append(head, element("span", "approval-meta", meta), element("span", "approval-preview", text(row.command_preview || row.reason || "无补充说明")), element("span", "approval-meta", formatTime(row.created_at))); card.onclick = () => void this.openDetail(row); controls.list.append(card); }
  }
  showPagination() { const { controls, state } = this; controls.previous.disabled = state.refreshInFlight || state.pageIndex === 0; controls.next.disabled = state.refreshInFlight || !state.nextCursor; controls.page.textContent = `第 ${state.pageIndex + 1} 页`; }
  render() { this.showStats(); this.showRows(); this.showPagination(); }
  resetPages() {
    const { state } = this; state.revision += 1; state.autoRefresh = false; state.refreshInFlight = false; this.controls.refresh.disabled = false;
    state.cursors = [null]; state.pageIndex = 0; state.nextCursor = null; state.sinceMs = state.window === "all" ? undefined : Date.now() - WINDOW_MS[state.window]; state.rows = undefined; state.stats = undefined; this.closeDetail(); this.render();
  }
  resetSession(session) { window.clearTimeout(this.debounce); this.state.session = session; this.resetPages(); }
  current(revision) { return revision === this.state.revision && !this.state.disposed; }
  targetPage(options) { const pageIndex = options.pageIndex ?? this.state.pageIndex; const cursors = options.cursors ?? this.state.cursors; return { pageIndex, cursors, cursor: cursors[pageIndex] }; }
  readPage(cursor) { const { state, api } = this; return Promise.all([api.list({ decision: state.decision || undefined, toolName: state.tool || undefined, sinceMs: state.sinceMs, limit: PAGE_SIZE, ...(cursor ? { beforeCreatedAt: cursor.createdAt, beforeId: cursor.id } : {}) }), api.statistics(state.window === "all" ? {} : { window: state.window })]); }
  async refresh(options = {}) {
    const { state, controls } = this; const silent = options.silent === true; const session = sessionIdFrom(this.context);
    if (!session) { this.resetSession(undefined); this.status("进入会话后查看该会话的审批记录。"); return; }
    if (session !== state.session) this.resetSession(session);
    const { pageIndex, cursors, cursor } = this.targetPage(options);
    const revision = ++state.revision; state.refreshInFlight = true; controls.refresh.disabled = true; this.showPagination();
    if (!silent) { this.closeDetail(); this.status("正在加载本会话审批记录…"); }
    try {
      const [list, stats] = await this.readPage(cursor);
      if (!this.current(revision)) return;
      const result = validatePage(list, session); validateStatistics(stats); state.rows = result.rows; state.stats = stats; state.nextCursor = result.nextCursor;
      state.pageIndex = pageIndex; state.cursors = cursors; state.autoRefresh = true; this.render(); this.status("");
      if (!silent) console.info("approvals.workspace.page.loaded", { page: pageIndex + 1, count: result.rows.length, hasNext: Boolean(result.nextCursor) });
    } catch (error) {
      if (!this.current(revision)) return;
      state.rows = undefined; state.stats = undefined; state.nextCursor = null; state.autoRefresh = false; this.closeDetail(); this.render();
      logFailure("approvals.workspace.refresh.failed", error); this.status(`加载本会话审批记录失败：${errorText(error)}`, true);
    } finally { if (this.current(revision)) { state.refreshInFlight = false; controls.refresh.disabled = false; this.showPagination(); } }
  }
  pagination() {
    const bar = element("nav", "approval-toolbar"); bar.setAttribute("aria-label", "审批记录分页");
    const previous = element("button", "approval-button", "上一页"); const next = element("button", "approval-button", "下一页"); const page = element("span", "approval-meta");
    previous.onclick = () => void this.refresh({ pageIndex: this.state.pageIndex - 1 });
    next.onclick = () => void this.refresh({ pageIndex: this.state.pageIndex + 1, cursors: [...this.state.cursors.slice(0, this.state.pageIndex + 1), this.state.nextCursor] });
    bar.append(previous, page, next); return { bar, previous, page, next };
  }
  later() { window.clearTimeout(this.debounce); this.debounce = window.setTimeout(() => { console.info("approvals.workspace.tool-filter.applied", { hasValue: Boolean(this.state.tool) }); void this.refresh(); }, FILTER_DEBOUNCE_MS); }
  build() {
    const { root, state } = this; root.replaceChildren(); addStyles(root); const page = element("section", "xsec-approvals"); const summary = element("div", "approval-card approval-summary"); const card = element("section", "approval-card"); const head = element("header", "approval-card-head"); const refreshButton = element("button", "approval-button", "刷新"); refreshButton.type = "button"; refreshButton.onclick = () => { console.info("approvals.workspace.refresh.requested"); this.resetPages(); void this.refresh(); }; head.append(element("h1", "approval-card-title", "本会话审批记录"), refreshButton);
    const toolbar = element("div", "approval-toolbar"); const windowGroup = element("span", "approval-toolbar"); const select = element("select", "approval-select"); const input = element("input", "approval-input"); input.placeholder = "工具名"; input.type = "search"; [["", "决策"], ...FILTER_DECISIONS.map((key) => [key, DECISIONS[key][0]])].forEach(([value, label]) => { const option = element("option", "", label); option.value = value; select.append(option); });
    for (const [value, label] of WINDOWS) { const button = element("button", "approval-button approval-window", label); button.type = "button"; button.dataset.value = value; button.onclick = () => { if (state.window !== value) { console.info("approvals.workspace.window.changed", { window: value }); state.window = value; this.resetPages(); this.updateWindows(); void this.refresh(); } }; windowGroup.append(button); }
    select.value = state.decision; input.value = state.tool; select.onchange = () => { console.info("approvals.workspace.decision.changed", { decision: select.value || "all" }); state.decision = select.value; this.resetPages(); void this.refresh(); }; input.oninput = () => { state.tool = input.value.trim(); this.resetPages(); this.later(); }; toolbar.append(windowGroup, select, input); const stateText = element("p", "approval-status"); const list = element("div", "approval-list"); const drawer = element("aside", "approval-drawer"); drawer.hidden = true; drawer.onclick = (event) => { if (event.target === drawer) this.closeDetail(); }; const pager = this.pagination(); card.append(head, toolbar, stateText, pager.bar, list); page.append(summary, card, drawer); root.append(page); this.controls = { ...pager, summary, list, status: stateText, refresh: refreshButton, drawer, windows: windowGroup.querySelectorAll("button") }; this.updateWindows(); this.render(); console.info("approvals.workspace.mount");
  }
  updateWindows() { this.controls.windows.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.value === this.state.window))); }
  mount(root, context) {
    window.clearInterval(this.timer); window.clearTimeout(this.debounce); this.themeSubscription?.dispose(); this.state.disposed = false; this.state.revision += 1; this.state.detailRevision += 1; this.state.detailRequestId = undefined;
    this.root = root; this.context = context; this.build(); applyTheme({}); this.themeSubscription = this.api.onTheme((theme) => applyTheme(theme));
    this.timer = window.setInterval(() => { const state = this.state; if (state.autoRefresh && state.pageIndex === 0 && !state.detailRequestId && !state.refreshInFlight && document.visibilityState === "visible") void this.refresh({ silent: true }); }, AUTO_REFRESH_INTERVAL_MS); return this.refresh();
  }
  update(context) { this.context = context; if (sessionIdFrom(context) !== this.state.session) { console.debug("approvals.workspace.context.changed"); return this.refresh(); } }
  dispose() { console.debug("approvals.workspace.dispose"); this.state.disposed = true; this.state.revision += 1; this.closeDetail(); window.clearInterval(this.timer); window.clearTimeout(this.debounce); this.themeSubscription?.dispose(); }
}
export function validateStatistics(stats) {
  const counts = ["approval_request_count", "allowed_count", "denied_count", "manual_review_count", "bypass_count"];
  if (!isRecord(stats) || counts.some((key) => !Number.isSafeInteger(stats[key]) || stats[key] < 0) || !Number.isFinite(stats.allow_rate) || stats.allow_rate < MIN_CONFIDENCE || stats.allow_rate > MAX_CONFIDENCE) throw new Error("审批统计数据无效");
}
export function activate(host) {
  const api = { context: host.context, onTheme: (listener) => host.onTheme(listener),
    readSettings: () => host.request("xsec.approvals.settings.get", {}), writeSettings: (input) => host.request("xsec.approvals.settings.set", input),
    list: (params) => host.request("xsec.approvals.list", params), statistics: (params) => host.request("xsec.approvals.statistics", params), detail: (params) => host.request("xsec.approvals.detail", params) };
  console.debug("approvals.activate", { surface: api.context?.kind === "settings-page" ? "settings" : "workspace" });
  return api.context?.kind === "settings-page" ? new SettingsPage(api) : new WorkspacePage(api);
}
