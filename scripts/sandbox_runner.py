#!/usr/bin/env python3
"""
sandbox_runner.py
─────────────────
The CORE of the validator. Does exactly one thing:

  1. Read README → extract what the agent claims to do + how to talk to it
  2. Start the agent in background
  3. Wait for it to be ready (HTTP or stdout signal)
  4. Send a REAL test query (like a human would)
  5. Capture the response
  6. Ask LLM: did it genuinely do what it claimed?

Output: sandbox_result.json
"""

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# ── LLM imports (best-effort, Claude > Gemini > Copilot) ─────────────────────
try:
    import anthropic
except ImportError:
    anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import httpx
except ImportError:
    import urllib.request
    import urllib.error
    httpx = None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Parse README to understand the agent's purpose + interface
# ─────────────────────────────────────────────────────────────────────────────

PARSE_README_PROMPT = """You are analyzing an AI agent's README to understand how to test it.

README:
---
{readme}
---

Extract ONLY the following as JSON (no preamble, no markdown fences):
{{
  "agent_purpose": "one sentence: what does this agent do?",
  "interface": "http | uagent | cli | unknown",
  "port": 8000,
  "test_query": "the exact natural language query to send to test its main functionality",
  "test_input": {{}},
  "expected_behavior": "what a successful response looks like (NOT checking code, just the output)"
}}

Rules:
- interface "http": agent exposes a REST/Flask/FastAPI endpoint
- interface "uagent": uAgents framework, runs on port 8000 by default
- interface "cli": agent reads from stdin or accepts CLI args
- test_query: make it REAL. For flight booking → "Book a flight from London to Paris on 2025-06-15 for 1 adult"
  For weather → "What is the weather in Mumbai?" For research → "Research recent AI breakthroughs"
- test_input: JSON body to POST if http/uagent, else {{}}
- port: default 8000 for uAgents, 5000 for Flask, 8080 otherwise
"""

JUDGE_PROMPT = """You are a QA engineer doing a black-box test of an AI agent.

Agent's claimed purpose: {purpose}
Expected behavior: {expected}

Test query sent: {query}

Agent's actual response:
---
{response}
---

Agent's startup logs (for context):
---
{startup_logs}
---

Judge STRICTLY: did the agent ACTUALLY do what it claims to do?
Do NOT look at code. Judge only on whether the response demonstrates real functionality.

Examples of PASS:
- Flight booking agent returns actual flight options or confirmation details
- Weather agent returns temperature, conditions for the requested city  
- Research agent returns a structured report with relevant information
- Booking agent says it cannot find flights but shows it TRIED with real API calls

Examples of FAIL:
- Agent just echoes the query back
- Agent returns a generic error without trying
- Agent crashes or times out
- Response is completely unrelated to the query

Reply ONLY as JSON:
{{
  "verdict": "pass | fail | partial",
  "confidence": "high | medium | low",
  "what_worked": "what the agent actually did",
  "what_failed": "what it didn't do or did wrong (empty string if pass)",
  "evidence": "quote from the response that proves your verdict",
  "provider": ""
}}
"""


def call_llm(prompt: str) -> dict:
    """Try Claude → Gemini → Copilot."""
    def _strip(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return text.strip()

    # 1. Claude
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key and anthropic:
        try:
            client = anthropic.Anthropic(api_key=anthropic_key)
            r = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(_strip(r.content[0].text))
            data["provider"] = "Claude"
            return data
        except Exception as e:
            print(f"[LLM] Claude failed: {e}")

    # 2. Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key and genai:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            r = model.generate_content(prompt)
            data = json.loads(_strip(r.text))
            data["provider"] = "Gemini"
            return data
        except Exception as e:
            print(f"[LLM] Gemini failed: {e}")

    # 3. GitHub Copilot (GITHUB_TOKEN is always present in Actions)
    gh_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if gh_token and OpenAI:
        try:
            client = OpenAI(
                base_url="https://api.githubcopilot.com",
                api_key=gh_token,
            )
            r = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            data = json.loads(_strip(r.choices[0].message.content))
            data["provider"] = "Copilot"
            return data
        except Exception as e:
            print(f"[LLM] Copilot failed: {e}")

    return {"error": "No LLM provider available", "provider": "none"}


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Start agent, wait for readiness
# ─────────────────────────────────────────────────────────────────────────────

STARTUP_SUCCESS = [
    "agent address", "starting agent", "registering", "listening on",
    "running on", "bureau", "connected to agentverse", "serving on",
    "uvicorn running", "flask running", "started server",
]

STARTUP_CRASH = [
    "traceback (most recent call last)", "modulenotfounderror", "importerror",
    "syntaxerror", "no module named", "cannot import name", "invalid api key",
    "authenticationerror",
]


def port_open(port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def start_agent(agent_dir: Path, entry: str) -> tuple[subprocess.Popen, list[str]]:
    """Start agent process and collect startup logs for up to 30s."""
    cmd = [sys.executable, entry]
    print(f"[sandbox] Starting: {' '.join(cmd)} in {agent_dir}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(agent_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    logs = []
    deadline = time.time() + 30  # 30s to start

    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            line = line.rstrip()
            logs.append(line)
            print(f"  [agent] {line}")

            low = line.lower()
            if any(p in low for p in STARTUP_SUCCESS):
                print("[sandbox] ✅ Startup signal detected")
                break
            if any(p in low for p in STARTUP_CRASH):
                print(f"[sandbox] ❌ Crash detected: {line}")
                break

    # Drain remaining logs briefly
    time.sleep(2)
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        logs.append(line.rstrip())

    return proc, logs


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Send a real test query to the running agent
# ─────────────────────────────────────────────────────────────────────────────

def query_http(port: int, test_input: dict, test_query: str, timeout: int = 20) -> str:
    """Send POST to agent HTTP endpoint, return response text."""
    url = f"http://127.0.0.1:{port}"

    # Try common endpoint patterns
    endpoints = ["/", "/query", "/ask", "/chat", "/run", "/agent"]
    body = {**test_input, "query": test_query, "message": test_query, "text": test_query}

    for ep in endpoints:
        target = f"{url}{ep}"
        try:
            if httpx:
                r = httpx.post(target, json=body, timeout=timeout)
                if r.status_code < 500:
                    return r.text[:3000]
            else:
                import urllib.request, urllib.error
                req = urllib.request.Request(
                    target,
                    data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode()[:3000]
        except Exception:
            continue

    return "(no HTTP response — agent may use a different interface)"


def query_stdout(proc: subprocess.Popen, test_query: str, logs: list[str]) -> str:
    """For CLI/uAgent: check if startup logs already contain output, or send stdin."""
    # Many agents print results during startup based on internal logic
    existing = "\n".join(logs)
    if len(existing) > 100:
        return existing[:3000]

    try:
        # Try sending query to stdin
        proc.stdin.write(test_query + "\n")
        proc.stdin.flush()
        time.sleep(5)
        extra = []
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            extra.append(line.rstrip())
        return "\n".join(extra)[:3000] if extra else existing[:3000]
    except Exception:
        return existing[:3000]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-dir", required=True)
    parser.add_argument("--entry-file", required=True)
    parser.add_argument("--output", default="sandbox_result.json")
    args = parser.parse_args()

    agent_path = Path(args.agent_dir)
    result = {
        "agent_dir": args.agent_dir,
        "verdict": "fail",
        "confidence": "low",
        "what_worked": "",
        "what_failed": "Validation did not complete",
        "evidence": "",
        "startup_crashed": False,
        "agent_purpose": "",
        "test_query": "",
        "raw_response": "",
        "startup_logs": "",
        "provider": "none",
    }

    # 1. Parse README
    readme_path = agent_path / "README.md"
    readme = readme_path.read_text(errors="ignore") if readme_path.exists() else ""
    if not readme:
        result["what_failed"] = "No README.md found — cannot determine what to test"
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    print("\n[step 1] Parsing README to understand agent...", flush=True)
    agent_meta = call_llm(PARSE_README_PROMPT.format(readme=readme[:4000]))
    if "error" in agent_meta and "purpose" not in agent_meta:
        result["what_failed"] = f"LLM unavailable: {agent_meta.get('error')}"
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    interface = agent_meta.get("interface", "uagent")
    port = int(agent_meta.get("port", 8000))
    test_query = agent_meta.get("test_query", "Hello, what can you do?")
    test_input = agent_meta.get("test_input", {})
    expected = agent_meta.get("expected_behavior", "A useful response related to the query")
    purpose = agent_meta.get("agent_purpose", "unknown")

    result["agent_purpose"] = purpose
    result["test_query"] = test_query

    print(f"  Purpose:   {purpose}")
    print(f"  Interface: {interface} (port {port})")
    print(f"  Test query: {test_query}", flush=True)

    # 2. Start agent
    print(f"\n[step 2] Starting agent ({args.entry_file})...", flush=True)
    proc, startup_logs = start_agent(agent_path, args.entry_file)
    startup_text = "\n".join(startup_logs)
    result["startup_logs"] = startup_text[:2000]

    # Check for crash
    crashed = any(p in startup_text.lower() for p in STARTUP_CRASH)
    result["startup_crashed"] = crashed
    if crashed:
        result["what_failed"] = "Agent crashed on startup (see logs)"
        result["evidence"] = next(
            (l for l in startup_logs if any(p in l.lower() for p in STARTUP_CRASH)), ""
        )
        Path(args.output).write_text(json.dumps(result, indent=2))
        try:
            proc.kill()
        except Exception:
            pass
        sys.exit(0)

    # 3. Send real query
    print(f"\n[step 3] Sending test query: '{test_query}'", flush=True)
    agent_response = ""

    if interface == "http" or port_open(port):
        print(f"  → HTTP query to port {port}")
        time.sleep(3)  # let agent fully bind
        agent_response = query_http(port, test_input, test_query)
    else:
        print("  → Stdout/logs query (no HTTP detected)")
        agent_response = query_stdout(proc, test_query, startup_logs)

    result["raw_response"] = agent_response
    print(f"  Response ({len(agent_response)} chars): {agent_response[:300]}...", flush=True)

    # Kill agent
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass

    # 4. LLM judges the response
    print(f"\n[step 4] Asking LLM to judge the response...", flush=True)
    if agent_response.strip():
        judgment = call_llm(JUDGE_PROMPT.format(
            purpose=purpose,
            expected=expected,
            query=test_query,
            response=agent_response[:2000],
            startup_logs=startup_text[:500],
        ))
        result.update({
            "verdict": judgment.get("verdict", "fail"),
            "confidence": judgment.get("confidence", "low"),
            "what_worked": judgment.get("what_worked", ""),
            "what_failed": judgment.get("what_failed", ""),
            "evidence": judgment.get("evidence", ""),
            "provider": judgment.get("provider", "unknown"),
        })
    else:
        result["what_failed"] = "Agent produced no response to the test query"

    Path(args.output).write_text(json.dumps(result, indent=2))
    print(f"\n[done] Verdict: {result['verdict'].upper()} (confidence: {result['confidence']})")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()