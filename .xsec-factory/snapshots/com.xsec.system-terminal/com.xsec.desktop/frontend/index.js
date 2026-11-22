// 系统终端 MCP 的网页前端。这个文件就是插件运行的代码：不打包、不压缩、不转译，
// Marketplace 校验与评审读到的内容与运行时完全一致。界面是纯文本输出加键入，不使用终端模拟器。

/**
 * @typedef {{
 *   context: { kind?: string, tool?: { entityId?: string } } | null,
 *   request(method: string, params: object): Promise<any>,
 *   onTheme?(listener: (theme: Record<string, string>) => void): { dispose(): void } | undefined,
 * }} Host
 */

const MIN_COLS = 20;
const MIN_ROWS = 2;
const CELL_WIDTH = 8;
const CELL_HEIGHT = 16;
const RESIZE_DELAY_MS = 100;
const READ_WAIT_MS = 1000;
const MAX_READ_BYTES = 65536;
const MAX_OUTPUT_CHARACTERS = 200000;
const KEY_SEQUENCES = {
  Enter: "\r",
  Backspace: "\x7f",
  Tab: "\t",
  Escape: "\x1b",
  ArrowUp: "\x1b[A",
  ArrowDown: "\x1b[B",
  ArrowRight: "\x1b[C",
  ArrowLeft: "\x1b[D",
};

const css = `
:root{color-scheme:dark;--bg:#111;--surface:#17191d;--hover:#202329;--text:#fcfcfc;--muted:#919191;--border:#303030;--accent:#76a5ff;--danger:#ff8b88}
:root[data-theme="light"]{color-scheme:light;--bg:#fff;--surface:#f6f7f9;--hover:#eceff3;--text:#17191c;--muted:#606773;--border:#d7dbe1;--accent:#3977e8;--danger:#b42318}
*{box-sizing:border-box}
html,body,[data-xsec-plugin-root]{width:100%;height:100%;margin:0}
body{background:var(--bg);color:var(--text);font:13px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
[hidden]{display:none!important}
button,select{font:inherit;color:inherit;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 9px;cursor:pointer}
button:hover{background:var(--hover)}
button:disabled,select:disabled{cursor:default;opacity:.55}
button:focus-visible,select:focus-visible,.screen:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.app{display:flex;flex-direction:column;height:100%}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:6px 10px;border-bottom:1px solid var(--border)}
.state{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.list{display:flex;flex-wrap:wrap;gap:6px;padding:6px 10px;border-bottom:1px solid var(--border)}
.list:empty,.notice:empty{display:none}
.screen{flex:1;min-height:0;margin:0;padding:8px 10px;overflow:auto;outline:none;font:12px/1.3 ui-monospace,"SFMono-Regular",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.notice{padding:8px 10px;color:var(--danger);font:12px/1.4 ui-monospace,"SFMono-Regular",Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.settings{display:grid;gap:12px;max-width:520px;padding:20px}
.settings label{display:grid;gap:6px;font-weight:600}
.settings select{padding:6px 8px}
`;

function el(tag, className = "", text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function errorText(error) {
  return error instanceof Error ? error.message : String(error);
}

// 纯文本视图不渲染终端转义序列：去掉 OSC 与 CSI 序列，并统一换行。
function plainText(value) {
  return value
    .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\r\n?/g, "\n");
}

function followHostTheme(host) {
  const apply = (theme) => {
    const bridged = getComputedStyle(document.documentElement).getPropertyValue("--xsec-color-mode").trim();
    const mode = theme?.["color-mode"] || bridged;
    document.documentElement.dataset.theme = mode === "light" ? "light" : "dark";
  };
  apply();
  return host.onTheme?.(apply);
}

function showError(state, value) {
  if (state.ui) state.ui.notice.textContent = errorText(value);
}

function setState(state, value) {
  if (state.ui) state.ui.state.textContent = value;
}

function renderState(state) {
  if (state.ui) state.ui.close.disabled = !state.terminalId || state.closing || state.ended;
}

function appendOutput(state, value) {
  const ui = state.ui;
  if (!ui) return;
  ui.output.appendData(plainText(value));
  const overflow = ui.output.length - MAX_OUTPUT_CHARACTERS;
  if (overflow > 0) ui.output.deleteData(0, overflow);
  ui.screen.scrollTop = ui.screen.scrollHeight;
}

function currentSize(state) {
  if (!state.ui) return { cols: MIN_COLS, rows: MIN_ROWS };
  const { screen } = state.ui;
  const style = getComputedStyle(screen);
  const width = screen.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const height = screen.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  return {
    cols: Math.max(MIN_COLS, Math.floor(width / CELL_WIDTH)),
    rows: Math.max(MIN_ROWS, Math.floor(height / CELL_HEIGHT)),
  };
}

function keyData(event) {
  // Shift+Tab 不发送给 Shell，留给浏览器移动焦点，避免键盘用户被困在终端里。
  if (event.key === "Tab" && event.shiftKey) return "";
  const key = event.key.toLowerCase();
  // Ctrl 加字母发送控制字符（Ctrl+C 为 \x03）；Ctrl+V 交给粘贴事件处理。
  if (event.ctrlKey && !event.metaKey && event.key.length === 1 && key !== "v") {
    const code = key.charCodeAt(0) - 96;
    return code >= 1 && code <= 26 ? String.fromCharCode(code) : "";
  }
  if (KEY_SEQUENCES[event.key]) return KEY_SEQUENCES[event.key];
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey ? event.key : "";
}

// 读取输出：每次带上次的 cursor 继续读，宿主返回 next_cursor 后才前移。
async function readOutput(host, state) {
  const terminalId = state.terminalId;
  if (state.stopped || state.reading || !terminalId) return;
  state.reading = true;
  try {
    const result = await host.request("xsec.terminal.read", {
      terminalId,
      cursor: state.cursor,
      maxBytes: MAX_READ_BYTES,
      waitMs: READ_WAIT_MS,
    });
    if (state.stopped) return;
    if (result.read_error) {
      console.warn("system-terminal.read.failed", { terminalId });
      showError(state, `终端输出读取失败：${result.read_error}`);
      if (state.ui) state.ui.reconnect.disabled = false;
      return;
    }
    if (result.truncated) appendOutput(state, "\n[较早的终端历史已被缓存淘汰]\n");
    if (result.data) appendOutput(state, result.data);
    state.cursor = result.next_cursor;
    if (result.state && result.state !== "running") {
      state.ended = true;
      setState(state, `${state.title}（${result.state}）`);
      renderState(state);
      return;
    }
    setState(state, state.title);
    queueMicrotask(() => void readOutput(host, state));
  } catch (reason) {
    console.warn("system-terminal.read.failed", { terminalId });
    showError(state, `读取终端失败：${errorText(reason)}`);
    if (state.ui) state.ui.reconnect.disabled = false;
  } finally {
    state.reading = false;
  }
}

// 面板有宿主给出的终端时 attach 它，否则新建一个；界面卸载只 detach，PTY 继续运行。
async function bindTerminal(host, state) {
  const existing = host.context?.tool?.entityId;
  const handle = existing
    ? await host.request("xsec.terminal.attach", { terminalId: existing })
    : await host.request("xsec.terminal.open", currentSize(state));
  if (state.stopped) {
    await host.request("xsec.terminal.detach", { terminalId: handle.terminal_id });
    return;
  }
  state.terminalId = handle.terminal_id;
  state.title = handle.title ?? handle.terminal_id;
  state.ended = Boolean(handle.state && handle.state !== "running");
  setState(state, state.title);
  renderState(state);
  resizeTerminal(host, state);
  state.ui?.screen.focus();
  await readOutput(host, state);
}

function resizeTerminal(host, state) {
  const terminalId = state.terminalId;
  if (!terminalId || state.ended || state.stopped) return;
  const size = currentSize(state);
  if (state.lastSize?.cols === size.cols && state.lastSize.rows === size.rows) return;
  state.lastSize = size;
  state.resizeQueue = state.resizeQueue
    .then(() => sendResize(host, state, terminalId, size))
    .catch((reason) => showError(state, reason));
}

async function sendResize(host, state, terminalId, size) {
  if (state.stopped || state.ended) return;
  try {
    await host.request("xsec.terminal.resize", { terminalId, ...size });
  } catch (reason) {
    // 失败的尺寸没有生效，下一次同样的尺寸仍会重试。
    if (state.lastSize === size) state.lastSize = undefined;
    throw reason;
  }
}

function scheduleResize(host, state) {
  clearTimeout(state.resizeTimer);
  state.resizeTimer = setTimeout(() => resizeTerminal(host, state), RESIZE_DELAY_MS);
}

function sendInput(host, state, data) {
  const terminalId = state.terminalId;
  if (!terminalId || state.stopped || state.ended) return;
  state.inputQueue = state.inputQueue
    .then(() => writeInput(host, state, terminalId, data))
    .catch((reason) => showError(state, reason));
}

async function writeInput(host, state, terminalId, data) {
  if (state.stopped || state.ended) return;
  await host.request("xsec.terminal.write", { terminalId, data });
}

async function closeTerminal(host, state) {
  const terminalId = state.terminalId;
  if (!terminalId || state.closing || state.ended || state.stopped) return;
  state.closing = true;
  renderState(state);
  try {
    await host.request("xsec.terminal.close", { terminalId });
    state.ended = true;
    console.info("system-terminal.closed", { terminalId });
    showError(state, "");
  } catch (reason) {
    showError(state, reason);
  } finally {
    state.closing = false;
    renderState(state);
  }
}

async function showTerminalList(host, state) {
  const ui = state.ui;
  if (!ui) return;
  ui.list.replaceChildren();
  try {
    const result = await host.request("xsec.terminal.list", {});
    for (const handle of result.items ?? []) {
      const button = el("button", "", `${handle.title ?? handle.terminal_id} · ${handle.state}`);
      button.onclick = () => void revealTerminal(host, state, handle.terminal_id);
      ui.list.append(button);
    }
    if (!ui.list.childElementCount) ui.list.textContent = "当前会话没有可显示的终端";
  } catch (reason) {
    showError(state, `读取终端列表失败：${errorText(reason)}`);
  }
}

async function revealTerminal(host, state, terminalId) {
  try {
    await host.request("xsec.terminal.reveal", { terminalId });
  } catch (reason) {
    showError(state, reason);
  }
}

function reconnectTerminal(host, state) {
  const terminalId = state.terminalId;
  if (!terminalId || !state.ui) return;
  console.info("system-terminal.reconnect", { terminalId });
  state.ui.reconnect.disabled = true;
  void attachAndRead(host, state, terminalId);
}

async function attachAndRead(host, state, terminalId) {
  try {
    await host.request("xsec.terminal.attach", { terminalId });
    showError(state, "");
    await readOutput(host, state);
  } catch (reason) {
    console.warn("system-terminal.reconnect.failed", { terminalId });
    showError(state, `重新连接终端失败：${errorText(reason)}`);
    if (state.ui) state.ui.reconnect.disabled = false;
  }
}

function mountTerminal(host, state, root) {
  root.replaceChildren(el("style", "", css));
  const app = el("main", "app");
  const bar = el("div", "bar");
  const stateText = el("span", "state", "正在连接…");
  const list = el("div", "list");
  const listButton = el("button", "", "终端列表");
  const revealButton = el("button", "", "显示");
  const reconnectButton = el("button", "", "重新连接");
  const closeButton = el("button", "", "终止终端");
  reconnectButton.disabled = true;
  closeButton.disabled = true;
  const screen = el("pre", "screen");
  screen.tabIndex = 0;
  screen.setAttribute("role", "application");
  screen.setAttribute("aria-label", "系统终端");
  const output = document.createTextNode("");
  screen.append(output);
  const notice = el("div", "notice");
  state.ui = { state: stateText, notice, list, screen, output, reconnect: reconnectButton, close: closeButton };
  listButton.onclick = () => void showTerminalList(host, state);
  revealButton.onclick = () => {
    console.info("system-terminal.reveal", { terminalId: state.terminalId });
    if (state.terminalId) void revealTerminal(host, state, state.terminalId);
  };
  reconnectButton.onclick = () => reconnectTerminal(host, state);
  closeButton.onclick = () => void closeTerminal(host, state);
  screen.onkeydown = (event) => {
    const data = keyData(event);
    if (!data) return;
    event.preventDefault();
    sendInput(host, state, data);
  };
  screen.onpaste = (event) => {
    const pasted = event.clipboardData?.getData("text") ?? "";
    if (!pasted) return;
    event.preventDefault();
    sendInput(host, state, pasted);
  };
  bar.append(stateText, listButton, revealButton, reconnectButton, closeButton);
  app.append(bar, list, screen, notice);
  root.append(app);
  state.observer = new ResizeObserver(() => scheduleResize(host, state));
  state.observer.observe(screen);
  state.theme = followHostTheme(host);
  console.info("system-terminal.mount", { existing: Boolean(host.context?.tool?.entityId) });
  return bindTerminal(host, state).catch((reason) => showError(state, `打开终端失败：${errorText(reason)}`));
}

async function disposeTerminal(host, state) {
  state.stopped = true;
  state.observer?.disconnect();
  clearTimeout(state.resizeTimer);
  state.theme?.dispose();
  state.theme = undefined;
  const terminalId = state.terminalId;
  state.ui = undefined;
  console.debug("system-terminal.dispose", { terminalId });
  if (!terminalId) return;
  try {
    await host.request("xsec.terminal.detach", { terminalId });
  } catch (reason) {
    console.warn("system-terminal.detach.failed", { terminalId, reason: errorText(reason) });
  }
}

function terminalView(host) {
  const state = {
    ui: undefined,
    theme: undefined,
    observer: undefined,
    resizeTimer: 0,
    terminalId: "",
    title: "",
    cursor: undefined,
    lastSize: undefined,
    ended: false,
    closing: false,
    stopped: false,
    reading: false,
    inputQueue: Promise.resolve(),
    resizeQueue: Promise.resolve(),
  };
  return {
    mount(root) {
      return mountTerminal(host, state, root);
    },
    update() {
      scheduleResize(host, state);
    },
    dispose() {
      return disposeTerminal(host, state);
    },
  };
}

async function loadSettings(host, state) {
  const ui = state.ui;
  if (!ui) return;
  try {
    const settings = await host.request("xsec.terminal.settings.get", {});
    ui.select.replaceChildren(new Option("系统默认", ""));
    for (const profile of settings.profiles ?? []) {
      ui.select.append(new Option(profile.label ?? profile.id, profile.id));
    }
    ui.select.value = settings.configuredProfileId ?? "";
    const fixed = settings.platform !== "windows";
    ui.select.disabled = fixed;
    ui.save.disabled = fixed;
    ui.info.textContent = fixed
      ? "macOS 和 Linux 使用当前帐户的系统登录 Shell。"
      : `当前默认 Shell：${settings.effectiveProfileId ?? "系统默认"}`;
  } catch (reason) {
    ui.info.textContent = `读取设置失败：${errorText(reason)}`;
  }
}

async function saveDefaultShell(host, ui) {
  try {
    await host.request("xsec.terminal.settings.set", { profileId: ui.select.value || null });
    ui.info.textContent = "默认 Shell 已保存，仅影响之后新建的终端。";
  } catch (reason) {
    ui.info.textContent = `保存设置失败：${errorText(reason)}`;
  }
}

function settingsView(host) {
  const state = { ui: undefined, theme: undefined };
  return {
    mount(root) {
      root.replaceChildren(el("style", "", css));
      const page = el("main", "app");
      const title = el("div", "bar", "系统终端 MCP 设置");
      const body = el("div", "settings");
      const label = el("label", "", "默认 Shell");
      const select = el("select");
      const save = el("button", "", "保存默认 Shell");
      const info = el("div", "notice");
      label.append(select);
      body.append(label, save, info);
      page.append(title, body);
      root.append(page);
      state.ui = { select, save, info };
      save.onclick = () => void saveDefaultShell(host, state.ui);
      state.theme = followHostTheme(host);
      return loadSettings(host, state);
    },
    update() {
      return loadSettings(host, state);
    },
    dispose() {
      state.theme?.dispose();
      state.theme = undefined;
    },
  };
}

export function activate(host) {
  console.debug("system-terminal.activate", { kind: host.context?.kind });
  if (host.context?.kind === "settings-page") return settingsView(host);
  return terminalView(host);
}
