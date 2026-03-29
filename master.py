#!/usr/bin/env python3
"""
Run the full manual starter flow in one command:
1. generate a local payload
2. save it
3. submit it to Energy Arena
"""

from __future__ import annotations

import argparse
import os
import sys

from submit_forecast import (
    DEFAULT_API_BASE,
    _get_default_data_source,
    _load_local_env_values,
    _normalized_data_source,
    build_payload,
    parse_target_date,
    save_payload_to_file,
    submit,
)


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Generate one payload and submit it to Energy Arena in one command."
    )
    parser.add_argument("--target_date", type=str, required=True, help="Target day in DD-MM-YYYY.")
    parser.add_argument("--challenge_id", type=str, required=True, help="Challenge id.")
    parser.add_argument("--area", type=str, default="", help="Optional area override.")
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
        "--data_source",
        type=str,
        default=_get_default_data_source(local_env),
        choices=["entsoe", "smard"],
        help="Baseline source for the built-in forecast generator (default: smard).",
    )
    parser.add_argument(
        "--save_payload",
        type=str,
        default="test_payload.txt",
        help="Write the generated payload to a local JSON text file (default: test_payload.txt).",
    )
    parser.add_argument(
        "--use_global_env",
        action="store_true",
        help="Allow fallback to globally set ENTSOE_API_KEY/ARENA_API_KEY if missing in local .env.",
    )
    args = parser.parse_args()

    data_source = _normalized_data_source(args.data_source)
    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = (args.api_key or "").strip()
    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if not arena_key:
        print(
            "Error: Arena API key required. Set ARENA_API_KEY in local .env, "
            "pass --api_key, or use --use_global_env.",
            file=sys.stderr,
        )
        sys.exit(1)
    if data_source == "entsoe" and not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY is required for --data_source entsoe.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print("1/2 Generate local payload...")
    try:
        payload = build_payload(
            target_date=target_date,
            challenge_id=args.challenge_id,
            area=args.area or None,
            entsoe_api_key=entsoe_key,
            api_base=args.api_base,
            data_source=data_source,
            arena_api_key=arena_key or None,
        )
        saved_path = save_payload_to_file(payload, args.save_payload)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Saved payload to {saved_path}")

    print("2/2 Submit payload to Energy Arena...")
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
