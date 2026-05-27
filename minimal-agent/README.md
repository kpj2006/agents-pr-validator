# Minimal Uppercase Agent

## Overview
This is a no-API test agent for the validator workflow. It starts a small HTTP server and returns the uppercase version of the text it receives.

## Prerequisites
- Python 3.11 or newer
- No external API keys are required
- Optional: set `SEED` for deterministic startup metadata

## Usage
1. Create a `.env` file if you want to override the default seed.
2. Run `python agent.py` from this folder.
3. Send a POST request to `http://127.0.0.1:8000` with JSON that includes `query`, `message`, or `text`.

## Test Query
Use this exact query for the validator:

`please convert this to uppercase: agents pr validator`

## Expected Behavior
The agent should reply with JSON containing the original input and an uppercase `result`, for example `PLEASE CONVERT THIS TO UPPERCASE: AGENTS PR VALIDATOR`.

## Environment
- `SEED`: optional integer used to make startup metadata deterministic. Default: `42`.

## Local Check
```bash
python agent.py
```

In another terminal:

```bash
python - <<'PY'
import json, urllib.request
req = urllib.request.Request(
    'http://127.0.0.1:8000',
    data=json.dumps({'query': 'please convert this to uppercase: agents pr validator'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
print(urllib.request.urlopen(req).read().decode())
PY
```