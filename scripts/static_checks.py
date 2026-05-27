#!/usr/bin/env python3
"""
static_checks.py
Runs static validation on a PR's agent folder:
  1. Required files present (README.md, requirements.txt, .env.example)
  2. Python syntax valid (py_compile)
  3. Ruff lint check
  4. .env.example keys documented in README
  5. README has required sections
Outputs a JSON result file.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = ["README.md", "requirements.txt"]
OPTIONAL_BUT_CHECKED = [".env.example"]

README_REQUIRED_SECTIONS = [
    "## Overview",       # or "## Description" or "# "
    "## Prerequisites",  # or "## Requirements" or "## Setup"
    "## Usage",          # or "## Running" or "## How to"
]

# Loose matching — any of these words count for a section
SECTION_KEYWORDS = {
    "overview":     ["overview", "description", "about", "what"],
    "prerequisites": ["prerequisite", "requirement", "setup", "install", "before"],
    "usage":        ["usage", "running", "run", "how to", "getting started", "quickstart"],
}


def check_required_files(agent_path: Path) -> dict:
    results = {}
    for f in REQUIRED_FILES:
        exists = (agent_path / f).exists()
        results[f] = {"pass": exists, "msg": "✅ Found" if exists else "❌ Missing"}

    for f in OPTIONAL_BUT_CHECKED:
        exists = (agent_path / f).exists()
        results[f] = {
            "pass": exists,
            "msg": "✅ Found" if exists else "⚠️ Missing (required if agent uses env vars)",
        }

    has_screenshot = any(
        (agent_path / f).exists()
        for f in ["screenshot.png", "demo.png", "demo.gif", "screenshot.gif"]
    ) or any(agent_path.glob("*.png")) or any(agent_path.glob("*.gif"))
    results["screenshot"] = {
        "pass": has_screenshot,
        "msg": "✅ Found" if has_screenshot else "⚠️ Missing (screenshot/demo image recommended)",
    }
    return results


def check_python_syntax(agent_path: Path) -> dict:
    py_files = list(agent_path.rglob("*.py"))
    if not py_files:
        return {"pass": True, "msg": "No Python files found", "errors": []}

    errors = []
    for f in py_files:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(f)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            errors.append(f"{f.name}: {result.stderr.strip()}")

    return {
        "pass": len(errors) == 0,
        "msg": f"✅ {len(py_files)} files OK" if not errors else f"❌ {len(errors)} syntax error(s)",
        "errors": errors,
    }


def check_ruff(agent_path: Path) -> dict:
    result = subprocess.run(
        ["ruff", "check", str(agent_path), "--output-format=concise"],
        capture_output=True, text=True
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    # Ruff exits 1 even for warnings — distinguish errors vs warnings
    critical = [l for l in lines if " E " in l or " F " in l]

    return {
        "pass": len(critical) == 0,
        "msg": (
            "✅ No critical lint issues"
            if not critical
            else f"⚠️ {len(critical)} lint issue(s) found"
        ),
        "issues": lines[:10],  # cap at 10 for readability
    }


def check_readme_sections(agent_path: Path) -> dict:
    readme = agent_path / "README.md"
    if not readme.exists():
        return {"pass": False, "msg": "README.md not found", "missing": list(SECTION_KEYWORDS)}

    content = readme.read_text(encoding="utf-8", errors="ignore").lower()
    missing = []
    for section, keywords in SECTION_KEYWORDS.items():
        if not any(kw in content for kw in keywords):
            missing.append(section)

    return {
        "pass": len(missing) == 0,
        "msg": (
            "✅ README has all required sections"
            if not missing
            else f"⚠️ README missing sections: {', '.join(missing)}"
        ),
        "missing": missing,
    }


def check_env_documented(agent_path: Path) -> dict:
    env_example = agent_path / ".env.example"
    readme = agent_path / "README.md"

    if not env_example.exists():
        return {"pass": True, "msg": "No .env.example — skipped", "undocumented": []}

    env_keys = []
    for line in env_example.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            env_keys.append(line.split("=")[0].strip())

    if not readme.exists() or not env_keys:
        return {"pass": True, "msg": "Skipped", "undocumented": []}

    readme_content = readme.read_text(encoding="utf-8", errors="ignore")
    undocumented = [k for k in env_keys if k not in readme_content]

    return {
        "pass": len(undocumented) == 0,
        "msg": (
            f"✅ All {len(env_keys)} env vars referenced in README"
            if not undocumented
            else f"⚠️ {len(undocumented)} env var(s) not mentioned in README: {', '.join(undocumented)}"
        ),
        "undocumented": undocumented,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-dir", required=True)
    parser.add_argument("--result-file", default="static_result.json")
    args = parser.parse_args()

    agent_path = Path(args.agent_dir)
    if not agent_path.is_dir():
        print(f"ERROR: {agent_path} is not a directory")
        sys.exit(1)

    print(f"\n{'='*50}")
    print(f"Static checks for: {agent_path}")
    print(f"{'='*50}\n")

    results = {
        "agent_dir": str(agent_path),
        "files": check_required_files(agent_path),
        "syntax": check_python_syntax(agent_path),
        "lint": check_ruff(agent_path),
        "readme_sections": check_readme_sections(agent_path),
        "env_documented": check_env_documented(agent_path),
    }

    # Overall pass: only hard-fail on missing README/syntax errors
    hard_fails = [
        not results["files"].get("README.md", {}).get("pass"),
        not results["syntax"]["pass"],
    ]
    results["overall_pass"] = not any(hard_fails)

    with open(args.result_file, "w") as f:
        json.dump(results, f, indent=2)

    print(json.dumps(results, indent=2))
    print(f"\nOverall: {'PASS' if results['overall_pass'] else 'FAIL'}")

    # Exit 0 always (report job handles failure, not this job)
    sys.exit(0)


if __name__ == "__main__":
    main()