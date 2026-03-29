#!/usr/bin/env python3
"""
Submit a previously generated payload to the Energy Arena API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from submit_forecast import (
    DEFAULT_API_BASE,
    _load_local_env_values,
    _validate_payload,
    submit,
)


def load_payload(path: str) -> dict:
    payload_path = Path(path).expanduser()
    if not payload_path.exists() or not payload_path.is_file():
        raise RuntimeError(f"Payload file not found: {payload_path}")
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Payload file is not valid JSON: {exc}") from exc
    return _validate_payload(payload, source="submit_forecast_to_energy_arena.py")


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Submit a saved payload to the Energy Arena API."
    )
    parser.add_argument(
        "--payload_path",
        type=str,
        default="test_payload.txt",
        help="Path to the saved payload file (default: test_payload.txt).",
    )
    parser.add_argument(
        "--api_key",
        type=str,
        default=local_env.get("ARENA_API_KEY", "").strip(),
        help="Arena API key (default: local .env ARENA_API_KEY).",
    )
    parser.add_argument(
        "--api_base",
        type=str,
        default=(
            local_env.get("ARENA_API_BASE_URL", "")
            or os.environ.get("ARENA_API_BASE_URL", "")
            or DEFAULT_API_BASE
        ).strip(),
        help="Arena API base URL.",
    )
    parser.add_argument(
        "--use_global_env",
        action="store_true",
        help="Allow fallback to globally set ARENA_API_KEY if missing in local .env.",
    )
    args = parser.parse_args()

    arena_key = (args.api_key or "").strip()
    if args.use_global_env:
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()
    if not arena_key:
        print(
            "Error: Arena API key required. Set ARENA_API_KEY in local .env, "
            "pass --api_key, or use --use_global_env.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        payload = load_payload(args.payload_path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Submitting payload from {Path(args.payload_path).expanduser()} "
        f"(challenge_id={payload.get('challenge_id')})"
    )
    if "target_date" in payload:
        print(f"Target date: {payload['target_date']}")
    if "target_start" in payload:
        print(f"Target start: {payload['target_start']}")

    ok = submit(
        payload=payload,
        api_key=arena_key,
        api_base=args.api_base,
        dry_run=False,
        verbose=True,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
