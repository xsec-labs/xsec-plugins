const STATUS = {
  vulnerable: "确认风险",
  candidate: "候选",
  not_vulnerable: "未发现",
  not_applicable: "不适用",
  not_run: "未运行",
  blocked: "已阻断",
  error: "错误",
};
const DOWNLOAD_URL_REVOKE_DELAY_MS = 1000;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function panel(title) {
  const section = element("section", undefined, "jwt-section");
  section.append(element("h2", title));
  return section;
}
function jsonBlock(value) {
  const pre = element("pre", JSON.stringify(value, null, 2), "jwt-json");
  return pre;
}
function statusCounts(tests) {
  return tests.reduce((counts, item) => {
    counts[item.status] = (counts[item.status] || 0) + 1;
    return counts;
  }, {});
}
function ensureStyles() {
  if (document.getElementById("jwt-analysis-style")) return;
  const style = document.createElement("style");
  style.id = "jwt-analysis-style";
  style.textContent = `
    .jwt-root{padding:20px;color:var(--foreground,#e8edf7);font:13px/1.5 system-ui,sans-serif}.jwt-root h1{font-size:22px;margin:0 0 4px}.jwt-root h2{font-size:15px;margin:0 0 12px}.jwt-root p{color:var(--muted-foreground,#9aa6bb)}
    .jwt-section{margin:16px 0;padding:16px;border:1px solid #ffffff1c;border-radius:12px;background:#ffffff05}.jwt-toolbar,.jwt-cards{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.jwt-toolbar select{min-width:220px;flex:1}
    .jwt-root button,.jwt-root select,.jwt-field input,.jwt-field textarea{padding:8px 10px;border:1px solid #ffffff2d;border-radius:8px;background:#111827;color:inherit}.jwt-cards{margin-top:10px}.jwt-card{padding:8px 10px;border-radius:8px;background:#ffffff0c}
    .jwt-token-columns{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.jwt-json{white-space:pre-wrap;overflow-wrap:anywhere;max-height:240px;overflow:auto;padding:10px;background:#080d17;border-radius:8px}.jwt-tests{width:100%;border-collapse:collapse}.jwt-tests td,.jwt-tests th{text-align:left;padding:8px;border-bottom:1px solid #ffffff16}
    .jwt-events{max-height:150px;overflow:auto}.jwt-settings{display:grid;gap:12px;max-width:720px;padding:20px}.jwt-field{display:grid;gap:5px}.jwt-field textarea{resize:vertical}.jwt-check{display:flex;align-items:center;gap:9px}.jwt-note{max-width:620px;color:var(--muted-foreground,#9aa6bb)}@media(max-width:800px){.jwt-token-columns{grid-template-columns:1fr}}
  `;
  document.head.append(style);
}

function renderTests(host, container, tests, tokens, signal) {
  const algorithms = [...new Set(tokens.map((token) => token.algorithm).filter(Boolean))].map((value) => [value, value]);
  const filters = [selectField("状态", "all", [["all", "全部状态"], ...Object.entries(STATUS)]),
    selectField("严重性", "all", [["all", "全部级别"], ...["critical", "high", "medium", "low", "informational"].map((value) => [value, value])]),
    selectField("算法", "all", [["all", "全部算法"], ...algorithms]), input("CVE", "search", "")];
  const section = panel("安全测试矩阵"), filterBar = element("div", undefined, "jwt-toolbar");
  filters.forEach((filter) => filterBar.append(filter.label));
  const table = element("table", undefined, "jwt-tests"), header = element("tr"), rows = element("tbody");
  ["测试", "CVE", "状态", "级别", "说明", "证据"].forEach((label) => header.append(element("th", label)));
  table.append(header, rows);
  const byToken = new Map(tokens.map((token) => [token.token_fingerprint, token.algorithm]));
  const render = () => {
    rows.replaceChildren();
    tests.filter((test) => matchesTest(test, filters, byToken)).forEach((test) => appendTestRow(host, container, rows, test, signal));
  };
  filters.forEach((filter, index) => filter.input.addEventListener(index === 3 ? "input" : "change", render, { signal }));
  render();
  section.append(filterBar, table); container.append(section);
}
function matchesTest(test, filters, byToken) {
  const [status, severity, algorithm, cve] = filters.map((filter) => filter.input.value);
  return (status === "all" || status === test.status) && (severity === "all" || severity === test.severity) &&
    (algorithm === "all" || algorithm === byToken.get(test.token_fingerprint)) &&
    (!cve || (test.cve || "").toLowerCase().includes(cve.toLowerCase()));
}
function appendTestRow(host, container, table, test, signal) {
  const row = element("tr");
  [test.test_id, test.cve || "—", STATUS[test.status] || test.status, test.severity, test.details?.reason || "—"]
    .forEach((value) => row.append(element("td", value)));
  const cell = element("td");
  if (test.evidence_id) {
    const button = element("button", "查看");
    button.addEventListener("click", async () => {
      const evidence = await host.request("xsec.jwt-analysis.evidence.get", { evidence_id: test.evidence_id });
      if (signal.aborted) return;
      container.replaceChildren(panel("脱敏证据"), jsonBlock(evidence));
    }, { signal });
    cell.append(button);
  } else cell.textContent = "—";
  row.append(cell);
  table.append(row);
}
async function showReport(host, root, jobId, signal) {
  if (!jobId) return;
  const value = await host.request("xsec.jwt-analysis.report", { job_id: jobId, format: "markdown" });
  if (signal.aborted) return;
  const section = panel("JWT 分析报告"), link = element("a", "下载 Markdown");
  const url = URL.createObjectURL(new Blob([value.report], { type: "text/markdown;charset=utf-8" }));
  signal.addEventListener("abort", () => URL.revokeObjectURL(url), { once: true });
  Object.assign(link, { href: url, download: `jwt-analysis-${jobId}.md` });
  link.addEventListener("click", () => setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_REVOKE_DELAY_MS), { once: true });
  section.append(link, element("pre", value.report, "jwt-json")); root.replaceChildren(section);
}

async function renderWorkspace(host, root, context, signal) {
  let selected = new URLSearchParams(location.search).get("job") || "";
  let refreshRevision = 0;
  let timer;
  signal.addEventListener("abort", () => window.clearTimeout(timer), { once: true });
  const body = element("div", undefined, "jwt-root");
  const title = element("h1", "JWT 分析");
  const subtitle = element("p", `项目任务 · ${context?.project?.projectId || "当前项目"}`);
  const diagnostics = await host.request("xsec.jwt-analysis.diagnostics", {});
  if (signal.aborted) return;
  const runtime = element("p", `Sidecar ${diagnostics.sidecar} · jwt_tool ${diagnostics.jwt_tool_version} · RockYou ${diagnostics.rockyou_available ? "已就绪" : "缺失"}`);
  const jobSelect = element("select");
  const content = element("div", undefined, "jwt-content"), reportView = element("div");
  const refreshButton = element("button", "刷新"), reportButton = element("button", "报告预览 / 下载");
  const toolbar = element("div", undefined, "jwt-toolbar");
  toolbar.append(jobSelect, reportButton, refreshButton);
  body.append(title, subtitle, runtime, toolbar, content, reportView); root.replaceChildren(body);
  const refresh = async (revision) => {
    if (signal.aborted) return;
    const current = () => !signal.aborted && revision === refreshRevision;
    const result = await host.request("xsec.jwt-analysis.jobs.list", { limit: 100 });
    if (!current()) return;
    const jobs = result.items || [];
    const previous = selected;
    jobSelect.replaceChildren();
    for (const job of jobs) {
      const option = element("option", `${job.job_id} · ${job.status}`);
      option.value = job.job_id;
      jobSelect.append(option);
    }
    if (!selected && jobs.length) selected = jobs[0].job_id;
    jobSelect.value = selected || previous;
    content.replaceChildren();
    if (!selected) {
      content.append(element("p", "当前项目还没有 JWT 分析任务。将 JWT、抓包引用或项目文件交给 Agent 创建任务。"));
      return;
    }
    const job = await host.request("xsec.jwt-analysis.jobs.get", { job_id: selected });
    if (!current()) return;
    renderSummary(content, job);
    renderTokens(content, job.tokens || []);
    renderWeakSecrets(content, job);
    renderCandidates(content, job.tests || []);
    renderTests(host, content, job.tests || [], job.tokens || [], signal);
    await renderEvents(host, content, selected, signal, current);
  };
  // Poll only after a successful refresh; an error reaches the Host boundary
  // and leaves the next refresh to an explicit user action.
  const refreshAndSchedule = async () => {
    window.clearTimeout(timer);
    const revision = ++refreshRevision;
    await refresh(revision);
    if (!signal.aborted && revision === refreshRevision) {
      timer = window.setTimeout(() => void refreshAndSchedule(), 2500);
    }
  };
  jobSelect.addEventListener("change", () => { selected = jobSelect.value; reportView.replaceChildren(); void refreshAndSchedule(); }, { signal });
  refreshButton.addEventListener("click", () => void refreshAndSchedule(), { signal });
  reportButton.addEventListener("click", () => void showReport(host, reportView, selected, signal), { signal });
  await refreshAndSchedule();
}

function renderSummary(root, job) {
  const summary = panel(`任务状态：${job.status}`);
  summary.append(element("p", `创建时间：${job.created_at} · 模式：${job.profile}`));
  const counts = statusCounts(job.tests || []);
  const cards = element("div", undefined, "jwt-cards");
  for (const key of ["vulnerable", "candidate", "not_vulnerable", "not_run", "blocked", "error"]) {
    cards.append(element("div", `${STATUS[key]} ${counts[key] || 0}`, `jwt-card ${key}`));
  }
  summary.append(cards);
  const severity = element("div", undefined, "jwt-cards");
  for (const level of ["critical", "high", "medium", "low", "informational"]) {
    const count = (job.tests || []).filter((test) => test.status === "vulnerable" && test.severity === level).length;
    severity.append(element("div", `${level} ${count}`, "jwt-card"));
  }
  summary.append(severity);
  root.append(summary);
}
function renderCandidates(root, tests) {
  const section = panel("候选发现");
  const candidates = tests.filter((item) => ["candidate", "vulnerable"].includes(item.status));
  section.append(element("p", "候选结果需复核请求差异和 canary 证据；确认后再由 Agent 调用核心 xsec_finding_upsert。"));
  section.append(jsonBlock(candidates.map((item) => ({
    test_id: item.test_id, cve: item.cve, status: item.status,
    severity: item.severity, confidence: item.confidence, evidence_id: item.evidence_id,
  }))));
  root.append(section);
}
function renderWeakSecrets(root, job) {
  const section = panel("弱密钥 / 空密钥");
  const findings = (job.tests || []).filter((item) => item.test_id === "weak-secret");
  section.append(jsonBlock({ findings, wordlist_runs: job.wordlist_runs || [] })); root.append(section);
}
function renderTokens(root, tokens) {
  const section = panel("JWT 解析");
  for (const token of tokens) {
    const columns = element("div", undefined, "jwt-token-columns");
    columns.append(jsonBlock({ fingerprint: token.token_fingerprint, header: token.header }));
    columns.append(jsonBlock(token.payload));
    columns.append(jsonBlock({ signature: token.signature, algorithm: token.algorithm, key_id: token.key_id }));
    section.append(columns);
  }
  root.append(section);
}
function renderEvents(host, root, jobId, signal, current) {
  const section = panel("任务阶段");
  return host.request("xsec.jwt-analysis.jobs.events", { job_id: jobId, cursor: 0 }).then((result) => {
    if (signal.aborted || !current()) return;
    const list = element("ol", undefined, "jwt-events");
    for (const item of result.items || []) list.append(element("li", `${item.created_at} · ${item.stage} · ${item.status}`));
    section.append(list);
    root.append(section);
  });
}

async function renderSettings(host, root, signal) {
  const current = await host.request("xsec.plugin.config.get", { key: "analysis" });
  if (signal.aborted) return;
  const settings = current?.value || {};
  const form = element("form", undefined, "jwt-settings");
  const title = element("h1", "JWT 分析设置");
  const note = element("p", "设置保存在当前账号。自定义字典需为本机可读的 UTF-8 文本文件。全量 RockYou 保持压缩并逐行读取；运行状态在项目 JWT 分析面板显示。", "jwt-note");
  const common = checkbox("启用 jwt-common 字典", settings.wordlists?.includes("jwt-common") ?? true);
  const rockyou = checkbox("启用 RockYou 字典", settings.rockyou_enabled ?? true);
  const customPaths = input("自定义字典路径，每行一个", "textarea", (settings.custom_wordlists || []).join("\n"));
  const rate = input("主动请求速率（每分钟）", "number", settings.rate_limit ?? 10);
  const timeout = input("请求超时（秒）", "number", settings.request_timeout_seconds ?? 10);
  const concurrency = input("最大并发任务", "number", settings.max_concurrent_jobs ?? 2);
  const requestCount = input("每任务主动请求上限", "number", settings.max_requests_per_job ?? 100);
  const redirect = selectField("重定向策略", settings.redirect_policy || "disabled", [
    ["disabled", "不跟随（默认）"], ["same-origin", "仅跟随同源，最多 3 次"],
  ]);
  const tls = checkbox("验证 TLS 证书", settings.tls_verify ?? true);
  const redaction = selectField("证据脱敏", settings.evidence_redaction || "standard", [["strict", "严格"], ["standard", "标准"], ["none", "关闭"]]);
  const publicKey = input("RS/HS 混淆测试公钥（PEM，可选）", "textarea", settings.public_key || "");
  const save = element("button", "保存设置");
  save.type = "submit";
  form.append(title, note, common.label, rockyou.label, customPaths.label, rate.label,
              timeout.label, concurrency.label, requestCount.label, redirect.label, tls.label, redaction.label, publicKey.label, save);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const wordlists = [common.input.checked ? "jwt-common" : null,
                       rockyou.input.checked ? "rockyou" : null,
                       customPaths.input.value.trim() ? "custom" : null].filter(Boolean);
    const value = {
      ...settings, wordlists, rockyou_enabled: rockyou.input.checked,
      custom_wordlists: customPaths.input.value.split("\n").map((path) => path.trim()).filter(Boolean),
      rate_limit: boundedInput(rate.input, 1, 60),
      request_timeout_seconds: boundedInput(timeout.input, 1, 60),
      max_concurrent_jobs: boundedInput(concurrency.input, 1, 8),
      max_requests_per_job: boundedInput(requestCount.input, 1, 100),
      tls_verify: tls.input.checked, redirect_policy: redirect.input.value, evidence_redaction: redaction.input.value,
      public_key: publicKey.input.value,
      retention: "permanent",
      listener_enabled: false,
    };
    await host.request("xsec.plugin.config.set", { key: "analysis", value });
    if (signal.aborted) return;
    console.info("settings.saved", { wordlistCount: value.wordlists.length, rateLimit: value.rate_limit });
    save.textContent = "已保存";
  }, { signal });
  root.replaceChildren(form);
}
function checkbox(labelText, checked) {
  const label = element("label", undefined, "jwt-field jwt-check");
  const inputNode = document.createElement("input");
  inputNode.type = "checkbox";
  inputNode.checked = checked;
  label.append(inputNode, element("span", labelText));
  return { label, input: inputNode };
}
function input(labelText, type, value) {
  const label = element("label", labelText, "jwt-field");
  const inputNode = document.createElement(type);
  if (type === "textarea") inputNode.rows = 4;
  else inputNode.type = type;
  inputNode.value = value;
  label.append(inputNode);
  return { label, input: inputNode };
}
function selectField(labelText, value, options) {
  const label = element("label", labelText, "jwt-field");
  const select = document.createElement("select");
  for (const [key, title] of options) {
    const option = element("option", title);
    option.value = key;
    select.append(option);
  }
  select.value = value;
  label.append(select);
  return { label, input: select };
}
function boundedInput(node, min, max) {
  const value = Number(node.value);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`Value must be from ${min} to ${max}`);
  }
  return value;
}

export async function activate(host) {
  ensureStyles();
  console.debug("frontend.activate", { apiVersion: host.apiVersion });
  let mountedRoot;
  let view;
  let disposed = false;
  const render = async (context) => {
    if (disposed) throw new Error("JWT frontend has been disposed");
    if (!mountedRoot) throw new Error("JWT frontend must be mounted before updating context");
    view?.abort();
    const current = new AbortController();
    view = current;
    const content = element("div");
    mountedRoot.replaceChildren(content);
    if (context?.kind === "settings-page" || context?.settings?.page === "settings") {
      await renderSettings(host, content, current.signal);
    } else {
      await renderWorkspace(host, content, context, current.signal);
    }
  };
  return {
    async mount(root, context) {
      if (disposed) throw new Error("JWT frontend has been disposed");
      if (mountedRoot) throw new Error("JWT frontend is already mounted");
      mountedRoot = root;
      console.info("workspace.mount", { projectId: context?.project?.projectId });
      await render(context);
    },
    async update(context) {
      console.debug("workspace.update", { projectId: context?.project?.projectId });
      await render(context);
    },
    dispose() {
      disposed = true;
      view?.abort();
      mountedRoot?.replaceChildren();
      mountedRoot = undefined;
      console.debug("frontend.dispose");
    },
  };
}
