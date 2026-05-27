#!/usr/bin/env python3
"""
generate_report.py
──────────────────
Reads sandbox_result.json and posts a focused PR comment:
Did the agent actually do what it claims? That's it.
"""

import argparse
import json
import os
from pathlib import Path


VERDICT_ICON = {"pass": "✅", "partial": "⚠️", "fail": "❌"}
CONFIDENCE_ICON = {"high": "🔵", "medium": "🟡", "low": "🔴"}
PROVIDER_BADGE = {"Claude": "🟣 Claude", "Gemini": "🔵 Gemini", "Copilot": "⚫ Copilot"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-file", default="sandbox_result.json")
    parser.add_argument("--output-file", default="final_report.md")
    args = parser.parse_args()

    if not Path(args.result_file).exists():
        Path(args.output_file).write_text(
            "<!-- fetch-agent-validator -->\n"
            "## ⚠️ Agent Validation — No Result\n\n"
            "Sandbox runner did not produce output. Check the Actions log."
        )
        return

    r = json.loads(Path(args.result_file).read_text())

    verdict = r.get("verdict", "fail")
    icon = VERDICT_ICON.get(verdict, "❓")
    confidence = r.get("confidence", "low")
    provider = PROVIDER_BADGE.get(r.get("provider", ""), r.get("provider", "LLM"))
    crashed = r.get("startup_crashed", False)

    lines = [
        "<!-- fetch-agent-validator -->",
        f"## {icon} Agent Sandbox Test — `{r.get('agent_dir', '')}`",
        "",
        f"> **Verdict:** `{verdict.upper()}` &nbsp;·&nbsp; "
        f"**Confidence:** {CONFIDENCE_ICON.get(confidence, '')} {confidence} &nbsp;·&nbsp; "
        f"**Reviewed by:** {provider}",
        "",
        "---",
        "",
    ]

    # ── What the agent claims to do ──────────────────────────────────────────
    if r.get("agent_purpose"):
        lines += [
            f"**Agent purpose:** {r['agent_purpose']}",
            "",
        ]

    # ── Crash shortcircuit ───────────────────────────────────────────────────
    if crashed:
        crash_line = next(
            (l for l in r.get("startup_logs", "").splitlines()
             if any(p in l.lower() for p in ["traceback", "error", "importerror"])),
            "See startup logs below"
        )
        lines += [
            "### ❌ Agent crashed on startup",
            "",
            f"```\n{crash_line}\n```",
            "",
        ]
    else:
        # ── Test performed ───────────────────────────────────────────────────
        lines += [
            "### 🧪 Test Performed",
            "",
            f"**Query sent:** `{r.get('test_query', 'N/A')}`",
            "",
        ]

        # ── Judgment ─────────────────────────────────────────────────────────
        lines += ["### 📊 Result", ""]

        if r.get("what_worked"):
            lines += [f"**What worked:** {r['what_worked']}", ""]
        if r.get("what_failed"):
            lines += [f"**What failed:** {r['what_failed']}", ""]
        if r.get("evidence"):
            lines += [
                "**Evidence from response:**",
                f"> {r['evidence']}",
                "",
            ]

    # ── Collapsible: raw response + startup logs ──────────────────────────────
    raw = r.get("raw_response", "")
    if raw:
        truncated = raw[:1500] + ("\n...(truncated)" if len(raw) > 1500 else "")
        lines += [
            "<details><summary>Agent response (raw)</summary>",
            "",
            f"```\n{truncated}\n```",
            "</details>",
            "",
        ]

    startup = r.get("startup_logs", "")
    if startup:
        trunc = startup[:1000] + ("\n...(truncated)" if len(startup) > 1000 else "")
        lines += [
            "<details><summary>Startup logs</summary>",
            "",
            f"```\n{trunc}\n```",
            "</details>",
            "",
        ]

    lines += [
        "---",
        "<sub>🤖 [fetch-agent-validator](https://github.com/fetchai/innovation-lab-examples)</sub>",
    ]

    report = "\n".join(lines)
    Path(args.output_file).write_text(report)
    print(report)


if __name__ == "__main__":
    main()