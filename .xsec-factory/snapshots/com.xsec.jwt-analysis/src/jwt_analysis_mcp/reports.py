from __future__ import annotations

import json
from typing import Any


def report(job: dict[str, Any], format_name: str) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for test in job["tests"]:
        counts[test["status"]] = counts.get(test["status"], 0) + 1
    if format_name == "json":
        return {"format": "json", "report": {**job, "summary": counts}}
    if format_name != "markdown":
        raise ValueError("format must be markdown or json")
    lines = [f"# JWT 分析报告 {job['job_id']}", "", f"状态：{job['status']}", "",
             f"JWT 数量：{len(job['tokens'])}", f"结果统计：{json.dumps(counts, ensure_ascii=False)}", "",
             "| 测试 | CVE | 状态 | 严重性 |", "|---|---|---|---|"]
    lines.extend(f"| {item['test_id']} | {item.get('cve') or '—'} | {item['status']} | {item['severity']} |"
                 for item in job["tests"])
    return {"format": "markdown", "report": "\n".join(lines)}
