#!/usr/bin/env python3
"""Minimal no-API HTTP agent for sandbox validation.

The agent reads an optional SEED env var, starts an HTTP server on port 8000,
and returns a deterministic uppercase transformation of the input text.
"""

from __future__ import annotations

import json
import os
import random
from http.server import BaseHTTPRequestHandler, HTTPServer


PORT = 8000


def load_seed() -> int:
    value = os.getenv("SEED", "42").strip()
    try:
        return int(value)
    except ValueError:
        return 42


SEED = load_seed()
random.seed(SEED)
BUILD_ID = random.randint(1000, 9999)


def extract_text(payload: dict[str, object]) -> str:
    for key in ("query", "message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "hello from the minimal agent"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body: dict[str, object]) -> None:
        data = json.dumps(body, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "seed": SEED, "build_id": BUILD_ID})
            return
        self._send_json(200, {"status": "ready", "seed": SEED, "build_id": BUILD_ID})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload = {}

        text = extract_text(payload)
        response = {
            "status": "ok",
            "seed": SEED,
            "build_id": BUILD_ID,
            "input": text,
            "result": text.upper(),
            "mode": "uppercase",
        }
        self._send_json(200, response)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Minimal uppercase agent ready on http://127.0.0.1:{PORT}")
    print(f"Seed: {SEED} | Build ID: {BUILD_ID}")
    server.serve_forever()


if __name__ == "__main__":
    main()