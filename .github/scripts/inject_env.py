#!/usr/bin/env python3
"""
inject_env.py
Reads .env.example, matches keys to available environment variables (from GitHub Secrets),
and writes a populated .env file.
Reports which keys are covered vs missing.
"""

import argparse
import os
import sys
from pathlib import Path


def parse_env_example(path: Path) -> dict[str, str]:
    """Parse .env.example into {KEY: example_value}."""
    keys = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            keys[key.strip()] = val.strip()
    return keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-example", default=".env.example")
    parser.add_argument("--output", default=".env")
    args = parser.parse_args()

    env_example = Path(args.env_example)
    if not env_example.exists():
        print("No .env.example found — skipping env injection")
        sys.exit(0)

    keys = parse_env_example(env_example)
    if not keys:
        print("Empty .env.example — nothing to inject")
        sys.exit(0)

    print(f"\nInjecting .env from {len(keys)} keys in .env.example")
    print("─" * 50)

    injected = []
    missing = []
    output_lines = []

    for key, example_val in keys.items():
        secret_val = os.environ.get(key, "").strip()
        if secret_val:
            output_lines.append(f"{key}={secret_val}")
            injected.append(key)
            print(f"  ✅ {key} — injected from secret")
        else:
            # Keep placeholder so agent can at least start and fail gracefully
            output_lines.append(f"{key}={example_val or 'PLACEHOLDER'}")
            missing.append(key)
            print(f"  ⚠️  {key} — NOT in repo secrets (using placeholder)")

    Path(args.output).write_text("\n".join(output_lines) + "\n")

    print("─" * 50)
    print(f"Injected: {len(injected)}/{len(keys)} keys")

    if missing:
        print(f"\n⚠️  Missing secrets (agent may fail or produce limited output):")
        for k in missing:
            print(f"   - {k}")
        # Write missing list for the report generator to pick up
        Path("missing_secrets.txt").write_text("\n".join(missing))

    print(f"\n✅ .env written to {args.output}")


if __name__ == "__main__":
    main()