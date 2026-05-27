# fetch-agent-validator

GitHub Actions CI that automatically validates every PR adding a new agent to `fetchai/innovation-lab-examples`.

## What It Does

On every PR, the bot:

1. **Detects** which agent folder was added/changed
2. **Runs static checks** — required files, Python syntax, ruff lint, README sections, env var docs
3. **Injects `.env`** from GitHub Secrets and runs the agent for 45s
4. **Classifies the output** — crash vs. success vs. daemon (timeout = OK)
5. **Asks Claude/Gemini/Copilot** to review README quality and whether the output matches what was described
6. **Posts a PR comment** with the full report (updates on re-push, no spam)

## Setup

### 1. Copy files into the repo

```
.github/
  workflows/
    validate-agent.yml     ← main workflow
  scripts/
    detect_agent.py        ← detects changed folder + agent type
    static_checks.py       ← file/syntax/lint/readme checks
    inject_env.py          ← populates .env from secrets
    generate_report.py     ← builds + posts the PR comment
```

### 2. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Purpose |
|---|---|
| `AGENTVERSE_KEY` | Fetch.ai Agentverse API key |
| `AGENT_SECRET_KEY` | uAgent seed/secret key |
| `ASI1_API_KEY` | ASI:One LLM key |
| `OPENAI_API_KEY` | OpenAI key |
| `ANTHROPIC_API_KEY` | Used by the validator LLM review |
| `GEMINI_API_KEY` | Google Gemini key |
| `PERPLEXITY_API_KEY` | Perplexity key |
| `STRIPE_API_KEY` | Stripe test key |

> The validator matches `.env.example` keys to these secrets automatically.
> Missing keys are reported in the PR comment as warnings, not failures.

### 3. Grant workflow permissions

In **Settings → Actions → General → Workflow permissions**:
- Select: **Read and write permissions**
- Check: **Allow GitHub Actions to create and approve pull requests**

---

## Agent Type Classification

The validator classifies agents and adjusts behaviour:

| Type | Runtime | Notes |
|---|---|---|
| `uagent` | ✅ Run 45s | Default; detects startup via log patterns |
| `mcp` | ✅ Run 45s | Same as uagent |
| `crewai` / `ag2` | ✅ Run 45s | Multi-agent crew |
| `a2a` | ✅ Run 45s | A2A protocol agents |
| `web3` | ⏭️ Skip runtime | Needs funded wallet |
| `frontend` | ⏭️ Skip runtime | Needs browser/full stack |

---

## PR Comment Example

```
## ✅ Agent Validation Report — trip-planner-agent

> Agent type: `uagent` | Verdict: Looks Good

### 📋 Static Checks

| Check | Result |
|---|---|
| README.md | ✅ Found |
| requirements.txt | ✅ Found |
| .env.example | ✅ Found |
| Python syntax | ✅ 3 files OK |
| Ruff lint | ✅ No critical lint issues |
| README sections | ✅ README has all required sections |
| Env vars in README | ✅ All 2 env vars referenced in README |

### 🚀 Runtime Check

Status: ✅ PASS
Reason: Agent started successfully (detected: `Agent address`)

### 🤖 AI Review

Recommendation: ✅ Approve
README quality: ✅ Clear and complete with setup instructions
Runtime matches README: ✅ Yes — Agent started and registered as described
```

---

## Adding New Secret Keys

If a contributor's agent needs a new API key not in the secrets list:
1. The validator will warn in the PR comment: `⚠️ Missing secrets: MY_NEW_KEY`
2. A maintainer adds it to repo secrets
3. Re-run the workflow — no code changes needed

---

## Extending

**Add a new agent type classification** → edit `FOLDER_TYPE_MAP` in `detect_agent.py`

**Add new startup success signals** → edit `SUCCESS_PATTERNS` in `generate_report.py`

**Change timeout** → edit `timeout 45` in `validate-agent.yml`

**Skip runtime for a specific folder** → add to `SKIP_FOLDERS` in `detect_agent.py`