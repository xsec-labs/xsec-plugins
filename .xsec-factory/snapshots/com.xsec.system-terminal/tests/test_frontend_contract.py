from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
# The frontend is the readable ESM file the plugin runs. No build step sits between review and runtime.
FRONTEND = ROOT / "com.xsec.desktop" / "frontend" / "index.js"
EXPECTED_TOOLS = {
    "terminal-profiles": "terminal_profiles",
    "terminal-open": "terminal_open",
    "terminal-list": "terminal_list",
    "terminal-read": "terminal_read",
    "terminal-write": "terminal_write",
    "terminal-resize": "terminal_resize",
    "terminal-reveal": "terminal_reveal",
    "terminal-close": "terminal_close",
}
# Terminals have no control lease: these mutations carry the terminal id (and data or size), never a control.
MUTATIONS = {
    "xsec.terminal.write",
    "xsec.terminal.resize",
    "xsec.terminal.close",
}
REMOVED_CONTROL_METHODS = {
    "xsec.terminal.control.status",
    "xsec.terminal.control.acquire",
    "xsec.terminal.control.release",
}
# A control lease is any spelling of "control" except the UI object `controls` (state.controls in the settings view).
CONTROL_LEASE = r"(?i)control(?!s\b)"


class SystemTerminalMcpContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.mcp = json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))
        self.source = FRONTEND.read_text(encoding="utf-8")

    def test_plugin_declares_one_mcp_one_skill_and_eight_parent_sub_tools(self) -> None:
        extension = self.manifest["extensions"]["com.xsec.desktop"]
        metadata = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["name"], "com.xsec.system-terminal")
        self.assertEqual(self.manifest["version"], "4.2.0")
        self.assertEqual(metadata["name"], self.manifest["name"])
        self.assertEqual(metadata["version"], self.manifest["version"])
        self.assertEqual(extension["displayName"], "系统终端 MCP")
        self.assertEqual(extension["engines"]["pluginApi"], "^1.9.0")
        self.assertTrue((ROOT / "skills/system-terminal/SKILL.md").is_file())
        bindings = extension["contributes"]["agentTools"]
        self.assertEqual(
            {binding: value["mcpTool"] for binding, value in bindings.items()},
            EXPECTED_TOOLS,
        )
        for binding in bindings.values():
            self.assertEqual(binding["roles"], ["parent", "sub"])
            self.assertEqual(binding["mcpServer"], "system-terminal")
            self.assertEqual(binding["workspaceToolId"], "system-terminal")
            self.assertEqual(binding["permission"], "terminal.shell:session.agent")
            self.assertIn(binding["permission"], extension["permissions"])

    def test_mcp_entrypoint_is_the_platform_native_sidecar(self) -> None:
        server = self.mcp["mcpServers"]["system-terminal"]
        self.assertEqual(server["type"], "stdio")
        self.assertEqual(server["command"], "./bin/system-terminal-mcp")
        self.assertEqual(server["cwd"], "${PLUGIN_DATA}")

    def test_frontend_exports_the_activator_inline(self) -> None:
        # The Marketplace validator matches the literal export. A bundler's trailing export list fails it.
        self.assertRegex(self.source, r"(?m)^export function activate\(host\) \{")
        self.assertEqual(len(re.findall(r"^export\b", self.source, re.MULTILINE)), 1)

    def test_both_views_return_the_full_lifecycle(self) -> None:
        terminal = self.source.split("function terminalView(", 1)[1].split("\nasync function loadSettings(", 1)[0]
        settings = self.source.split("function terminalSettings(", 1)[1].split("\nexport function activate(", 1)[0]
        for body in (terminal, settings):
            for method in ("mount", "update", "dispose"):
                self.assertRegex(body, rf"(?m)^    {method}\(")

    def test_frontend_uses_cursor_reads_and_detaches_without_terminating(self) -> None:
        self.assertIn('host.request("xsec.terminal.attach", { terminalId: existing })', self.source)
        self.assertIn('host.request("xsec.terminal.read", {', self.source)
        self.assertIn("state.cursor = result.next_cursor", self.source)
        self.assertIn("result.truncated", self.source)
        dispose = self.source.split("async function disposeTerminal(", 1)[1].split("\n}\n", 1)[0]
        self.assertIn('host.request("xsec.terminal.detach", { terminalId })', dispose)
        self.assertNotIn('host.request("xsec.terminal.close"', dispose)

    def test_frontend_uses_host_validated_terminal_operations(self) -> None:
        methods = set(re.findall(r'host\.request\("(xsec\.terminal\.[^"]+)"', self.source))
        declared = self.manifest["extensions"]["com.xsec.desktop"]["frontendApi"]["methods"]
        self.assertTrue(methods <= set(declared))
        checked = set()
        # This is a source contract gate; Host/PTY/browser tests prove execution.
        for method_expression, payload in re.findall(r'host\.request\(([^,\n]+),\s*\{([^{}]*)\}\)', self.source):
            targets = set(re.findall(r'"(xsec\.terminal\.[^"]+)"', method_expression))
            mutations = targets & MUTATIONS
            if mutations:
                self.assertRegex(payload, r"\bterminalId\b")
                self.assertNotRegex(payload, CONTROL_LEASE)
                checked.update(mutations)
        self.assertEqual(checked, MUTATIONS)
        for method in MUTATIONS:
            self.assertEqual(declared[method], {"capability": "terminal.shell", "binding": "session"})
        self.assertFalse(REMOVED_CONTROL_METHODS & set(declared))
        self.assertNotRegex(self.source, CONTROL_LEASE)
        self.assertIn('host.request("xsec.terminal.reveal", { terminalId })', self.source)

    def test_settings_save_waits_for_a_successful_read(self) -> None:
        # Saving before the settings are read would write the system default over the configured shell.
        save = self.source.split("async function saveDefaultShell(", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("if (!state.ready) return;", save)
        self.assertIn("state.controls.save.disabled = true;", self.source)
        load = self.source.split("async function loadSettings(", 1)[1].split("\n}\n", 1)[0]
        before_read, found, after_read = load.partition('host.request("xsec.terminal.settings.get"')
        self.assertTrue(found)
        # ready becomes true only after the read succeeds, never before the request is sent.
        self.assertNotIn("state.ready = true;", before_read)
        self.assertIn("state.ready = true;", after_read)
        self.assertIn("state.ready = false;", load.split("catch", 1)[1])

    def test_control_lease_pattern_catches_lease_names_but_not_the_ui_object(self) -> None:
        for lease in ("controlLease", "terminal_control_status", "requestControl", "control"):
            self.assertRegex(lease, CONTROL_LEASE)
        for ui in ("const controls = state.controls;", "state.controls.save.disabled"):
            self.assertNotRegex(ui, CONTROL_LEASE)

    def test_frontend_and_skill_follow_the_declared_contract(self) -> None:
        self.assertTrue(FRONTEND.is_file())
        self.assertGreater(FRONTEND.stat().st_size, 10_000)
        skill = (ROOT / "skills/system-terminal/SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: system-terminal\n"))
        self.assertIn("tools/list", skill)
        self.assertIn("terminal_reveal", skill)
        self.assertNotIn("terminal_control", skill)


if __name__ == "__main__":
    unittest.main()
