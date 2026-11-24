import assert from "node:assert/strict";
import { test } from "node:test";
import { loadRules } from "../src/api/settings";
import type { PluginHost } from "../src/types";

const hostWith = (items: unknown[]) => ({ request: async () => items }) as unknown as PluginHost;
const rule = (severity: string) => ({ rule_id: `r-${severity}`, severity, pattern: "x", enabled: true });

test("loadRules accepts every severity the host stores, including info", async () => {
  const severities = ["info", "low", "medium", "high", "critical"];
  const rules = await loadRules(hostWith(severities.map(rule)));
  assert.deepEqual(rules.map((item) => item.severity), severities);
});

test("loadRules still rejects an unknown severity", async () => {
  await assert.rejects(loadRules(hostWith([rule("urgent")])), /规则级别格式无效/);
});
