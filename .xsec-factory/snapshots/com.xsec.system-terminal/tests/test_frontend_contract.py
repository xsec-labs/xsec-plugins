from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT
FRONTEND = PLUGIN_ROOT / "com.xsec.desktop" / "frontend" / "index.js"


class FrontendContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = FRONTEND.read_text(encoding="utf-8")

    def test_terminal_surface_contains_only_terminal_content_and_errors(self) -> None:
        surface = self.source.split("function terminalSurface(host)", 1)[1]
        self.assertIn('screen.setAttribute("aria-label", "系统终端")', self.source)
        self.assertIn("启动终端失败：", self.source)
        for text in ("打开插件设置", "重试启动终端", "重新打开终端", "点击终端区域后直接键入命令"):
            self.assertNotIn(text, surface)

    def test_settings_follow_host_theme_and_limit_windows_profiles(self) -> None:
        """Keep themed Windows profiles and the Unix login-shell label aligned."""

        self.assertIn("host.onTheme?.(apply)", self.source)
        self.assertIn(':root[data-theme="light"]', self.source)
        self.assertIn('view?.platform === "windows"', self.source)
        self.assertIn('new Set(["cmd", "windows-powershell", "powershell-7"])', self.source)
        self.assertIn("effective.label || effective.id", self.source)
        self.assertIn("新建终端使用当前帐户的登录 Shell。", self.source)

    def test_terminal_open_delegates_the_saved_profile_to_the_host(self) -> None:
        opened = self.source.split("async function openTerminal", 1)[1]
        opened = opened.split("function scheduleWrite", 1)[0]
        self.assertIn('host.request("xsec.terminal.open", terminalSize(state))', opened)
        self.assertNotIn('host.request("xsec.terminal.settings.get"', opened)
        self.assertNotIn("profileId", opened)
        self.assertNotIn("navigator.userAgent", opened)
        opened = self.source.split("state.terminalId = handle.terminal_id", 1)[1]
        opened = opened.split("function scheduleWrite", 1)[0]
        self.assertIn("resizeTerminal(host, state)", opened)

    def test_terminal_size_uses_the_visible_content_box(self) -> None:
        size = self.source.split("function terminalSize", 1)[1]
        size = size.split("async function openTerminal", 1)[0]
        self.assertIn("getComputedStyle(screen)", size)
        for edge in ("paddingLeft", "paddingRight", "paddingTop", "paddingBottom"):
            self.assertIn(edge, size)

    def test_settings_read_failure_offers_an_explicit_retry(self) -> None:
        settings = self.source.split("async function loadSettings", 1)[1]
        settings = settings.split("function terminalSettings", 1)[0]
        self.assertIn('retry = e("button", "", "重试读取设置")', settings)
        self.assertIn('state.controls.retry.hidden = false', settings)
        self.assertIn('system-terminal.settings.retry', settings)
        self.assertIn('void loadSettings(host, state)', settings)
        self.assertIn('actions.append(save); retryActions.append(retry)', settings)
        self.assertIn('form, systemDefault, retryActions, notice', settings)
        failure = settings.split("catch (error)", 1)[1]
        self.assertNotIn("renderSettingsView", failure)
        self.assertNotIn("state.ready = true", failure)

    def test_polling_stops_on_read_failure_and_throttles_idle_reads(self) -> None:
        poll = self.source.split("async function poll", 1)[1]
        poll = poll.split("function terminalSize", 1)[0]
        self.assertIn("IDLE_POLL_INTERVAL_MS = 500", self.source)
        self.assertIn("await failTerminal(host, state, `读取终端失败\uFF1A", poll)
        self.assertNotIn("schedulePoll(host, state", poll.split("catch (error)", 1)[1].split("finally", 1)[0])

    def test_terminal_failure_closes_once_and_scrollback_is_bounded(self) -> None:
        failure = self.source.split("async function failTerminal", 1)[1].split("function appendScreen", 1)[0]
        self.assertLess(failure.index('state.terminalId = ""'), failure.index('host.request("xsec.terminal.close"'))
        self.assertLess(failure.index('host.request("xsec.terminal.close"'), failure.index("report(state"))
        self.assertEqual(failure.count('host.request("xsec.terminal.close"'), 1)
        self.assertIn('state.reading = false; state.writing = false; state.inputBuffer = ""', failure)
        self.assertIn("catch (error) { closeError = error; }", failure)
        self.assertIn("generation !== state.generation", failure)
        self.assertNotIn("throw closeError", failure)
        append = self.source.split("function appendScreen", 1)[1].split("function isCurrentTerminal", 1)[0]
        self.assertIn("MAX_SCROLLBACK_CHARACTERS = 200_000", self.source)
        self.assertIn("text.appendData(clean(value))", append)
        self.assertIn("text.deleteData(0, overflow)", append)
        self.assertNotIn("textContent +=", self.source)

    def test_superseded_resize_failures_do_not_stop_the_terminal(self) -> None:
        resize = self.source.split("function resizeTerminal", 1)[1]
        resize = resize.split("function buildTerminal", 1)[0]
        self.assertIn("const resizeGeneration = ++state.resizeGeneration", resize)
        self.assertIn("resizeGeneration === state.resizeGeneration", resize)
        self.assertIn("resizeGeneration: 0", self.source)

    def test_remount_owns_theme_and_async_terminal_results(self) -> None:
        self.assertGreaterEqual(self.source.count("state.theme = followHostTheme(host)"), 2)
        self.assertIn("generation !== state.generation", self.source)
        self.assertIn("isCurrentTerminal(state, generation, terminalId)", self.source)
        self.assertIn('state.terminalId = ""', self.source)
        dispose = self.source.split("async function disposeTerminal", 1)[1]
        dispose = dispose.split("function terminalSurface", 1)[0]
        self.assertLess(dispose.index("cancelAnimationFrame(state.inputFrame)"), dispose.index("state.inputFrame = 0"))

    def test_manifest_declares_every_method_the_frontend_and_native_panel_call(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "2.1.0")
        desktop = manifest["extensions"]["com.xsec.desktop"]
        self.assertEqual(desktop["schemaVersion"], 3)
        self.assertEqual(desktop["entrypoints"]["native"], "builtin:com.xsec.system-terminal")
        agent_tools = manifest["extensions"]["com.xsec.desktop"]["contributes"]["agentTools"]
        self.assertEqual(
            sorted(tool["mcpTool"] for tool in agent_tools.values()),
            sorted(
                [
                    "terminal_close",
                    "terminal_list",
                    "terminal_open",
                    "terminal_profiles",
                    "terminal_read",
                    "terminal_resize",
                    "terminal_reveal",
                    "terminal_write",
                ]
            ),
        )
        self.assertEqual({tool["mcpServer"] for tool in agent_tools.values()}, {"system-terminal"})
        self.assertEqual(manifest["version"], codex["version"])
        methods = manifest["extensions"]["com.xsec.desktop"]["frontendApi"]["methods"]
        requested = set(re.findall(r'host\.request\("([^"]+)"', self.source))
        self.assertLessEqual(requested, set(methods))
        # The native panel and the Agent tools call these Host methods too; the Broker refuses any not declared here.
        panel_and_agent = {
            "xsec.terminal.profiles",
            "xsec.terminal.open",
            "xsec.terminal.list",
            "xsec.terminal.read",
            "xsec.terminal.write",
            "xsec.terminal.resize",
            "xsec.terminal.attach",
            "xsec.terminal.detach",
            "xsec.terminal.reveal",
            "xsec.terminal.close",
        }
        self.assertLessEqual(panel_and_agent, set(methods))

    def test_plugin_api_lower_bound_excludes_lease_era_hosts(self) -> None:
        """The control-less calls need a 1.9.0 host.

        Hosts at Plugin API 1.8.0 (Desktop 0.3.8 among them) still require a control lease on
        write, resize and close, so the lower bound must exclude them. The host rule that
        needs at least 1.7.0 for terminal mutations is a weaker check and still holds.
        """

        desktop = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))["extensions"]["com.xsec.desktop"]
        mutations = {
            method
            for method in desktop["frontendApi"]["methods"]
            if method in {"xsec.terminal.write", "xsec.terminal.resize", "xsec.terminal.close"}
        }
        self.assertTrue(mutations, "the frontend must declare at least one terminal mutation")
        plugin_api = desktop["engines"]["pluginApi"]
        self.assertRegex(plugin_api, r"^\^\d+\.\d+\.\d+$")
        lower = tuple(int(part) for part in plugin_api[1:].split("."))
        self.assertGreaterEqual(lower, (1, 9, 0))

    def test_manifest_declares_no_control_methods(self) -> None:
        """The control lease is gone: no frontend method and no Agent tool may name it."""

        desktop = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))["extensions"]["com.xsec.desktop"]
        self.assertEqual([m for m in desktop["frontendApi"]["methods"] if m.startswith("xsec.terminal.control.")], [])
        self.assertEqual([n for n, b in desktop["contributes"]["agentTools"].items() if "control" in b["mcpTool"]], [])

    def test_activation_returns_explicit_lifecycle_helpers(self) -> None:
        activation = self.source.split("export function activate(host)", 1)[1]
        self.assertIn('return terminalSettings(host)', activation)
        self.assertIn('return terminalSurface(host)', activation)

    def test_terminal_calls_send_no_lease_and_read_from_the_cursor(self) -> None:
        """Terminal calls carry no control lease; read must advance from the cursor."""

        self.assertIsNone(re.search(r"\bcontrol\b", self.source))
        self.assertIn('host.request("xsec.terminal.write", { terminalId, data })', self.source)
        self.assertIn("terminalId,\n    ...terminalSize(state),", self.source)
        self.assertEqual(self.source.count('"xsec.terminal.close", { terminalId })'), 2)
        self.assertIn('"xsec.terminal.close", { terminalId: handle.terminal_id }', self.source)
        self.assertIn("{ terminalId, cursor: state.cursor }", self.source)
        self.assertIn("state.cursor = data.next_cursor", self.source)

    def test_source_respects_workspace_complexity_limits(self) -> None:
        lines = self.source.splitlines()
        self.assertLessEqual(len(lines), 300)
        starts = [index for index, line in enumerate(lines) if re.match(r"^(?:async )?function ", line)]
        ends = starts[1:] + [len(lines)]
        for start, end in zip(starts, ends, strict=True):
            self.assertLessEqual(end - start, 50, lines[start])


if __name__ == "__main__":
    unittest.main()
