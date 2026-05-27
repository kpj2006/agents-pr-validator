#!/usr/bin/env python3
"""
detect_agent.py
Detects which top-level agent folder was added/modified in this PR,
classifies the agent type, and finds the main entry file.
Writes outputs to GITHUB_OUTPUT.
"""

import os
import subprocess
import json
from pathlib import Path

# ── Agent type classification ─────────────────────────────────────────────────
# Maps folder prefix → agent type used for runtime strategy
FOLDER_TYPE_MAP = {
    "web3": "web3",
    "frontend-integration": "frontend",
    "a2a-cart-store": "a2a",
    "a2a-uAgents-Integration": "a2a",
    "launch-your-a2a": "a2a",
    "mcp-agents": "mcp",
    "crewai-agents": "crewai",
    "ag2-agents": "ag2",
    "google-adk": "google-adk",
    "google-genai": "genai",
    "stripe-": "stripe",
    "llama-index": "llama",
    "Rag-agent": "rag",
    "Crewai": "crewai",
    "Composio": "composio",
    "Claude Agent SDK": "claude-sdk",
    "openai-agent-sdk": "openai-sdk",
}

# Folders to skip validation entirely
SKIP_FOLDERS = {
    ".github", "docs", "contributors", "cursor-rules",
    "Browser-based-agents",  # requires live browser
}

# Priority order for finding the main entry file
ENTRY_CANDIDATES = [
    "agent.py", "main.py", "run.py", "app.py",
    "agents/alice/agent.py", "src/agent.py",
]


def get_changed_folders(base_sha: str, head_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        capture_output=True, text=True, check=True
    )
    folders = set()
    for line in result.stdout.splitlines():
        parts = line.split("/")
        if len(parts) > 1:
            folders.add(parts[0])
    return list(folders)


def classify_agent(folder: str) -> str:
    for prefix, atype in FOLDER_TYPE_MAP.items():
        if folder.startswith(prefix):
            return atype
    return "uagent"  # default: standard uAgents agent


def find_entry_file(folder: Path) -> str | None:
    for candidate in ENTRY_CANDIDATES:
        if (folder / candidate).exists():
            return candidate
    # Fallback: find any *.py at root level that isn't a util
    for f in sorted(folder.glob("*.py")):
        if f.name not in {"setup.py", "conftest.py"}:
            return f.name
    return None


def write_output(key: str, value: str):
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{key}={value}\n")
    print(f"OUTPUT {key}={value}")


def main():
    base_sha = os.environ.get("BASE_SHA", "HEAD~1")
    head_sha = os.environ.get("HEAD_SHA", "HEAD")

    changed = get_changed_folders(base_sha, head_sha)
    print(f"Changed top-level folders: {changed}")

    # Filter to real agent folders that exist as directories
    agent_folders = [
        f for f in changed
        if (Path(f).is_dir() and f not in SKIP_FOLDERS and not f.startswith("."))
    ]

    if not agent_folders:
        print("No agent folders changed — skipping validation")
        write_output("skip", "true")
        write_output("agent_dir", "")
        write_output("agent_type", "")
        write_output("has_env", "false")
        write_output("entry_file", "")
        return

    # Take the first (or only) changed agent folder
    agent_dir = agent_folders[0]
    agent_path = Path(agent_dir)
    agent_type = classify_agent(agent_dir)

    has_env = (agent_path / ".env.example").exists()
    entry_file = find_entry_file(agent_path) or "agent.py"

    print(f"Agent dir:  {agent_dir}")
    print(f"Agent type: {agent_type}")
    print(f"Has .env:   {has_env}")
    print(f"Entry file: {entry_file}")

    write_output("agent_dir", agent_dir)
    write_output("agent_type", agent_type)
    write_output("has_env", str(has_env).lower())
    write_output("entry_file", entry_file)
    write_output("skip", "false")


if __name__ == "__main__":
    main()