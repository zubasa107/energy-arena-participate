#!/usr/bin/env python3
"""
Build one local forecast payload for Energy Arena.

This script generates a payload locally with the built-in starter logic and
stores it as JSON. It does not submit anything to the API. Use
submit_payload.py for the actual POST request after inspecting the payload.
"""

from __future__ import annotations

import argparse
import os
import sys

from challenge_catalog import get_challenge_infos
from submit_forecast import (
    DEFAULT_API_BASE,
    _get_default_data_source,
    _load_local_env_values,
    _normalized_data_source,
    build_payload,
    parse_target_date,
    print_open_challenge_infos,
    run_setup_check,
    save_payload_to_file,
)


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Generate one local forecast payload with the starter model."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help="Target day in DD-MM-YYYY. Required unless --list_open_challenges or --check_setup is used.",
    )
    parser.add_argument(
        "--challenge_id",
        type=str,
        default="",
        help="Challenge id from python naiv_model.py --list_open_challenges.",
    )
    parser.add_argument(
        "--area",
        type=str,
        default="",
        help="Optional area override. Current challenges usually have exactly one area and do not need this.",
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
    parser.add_argument(
        "--check_setup",
        action="store_true",
        help="Validate local keys, API reachability, and custom model loading, then exit.",
    )
    parser.add_argument(
        "--list_open_challenges",
        action="store_true",
        help="Fetch currently open challenges from the Energy Arena API and exit.",
    )
    args = parser.parse_args()

    data_source = _normalized_data_source(args.data_source)
    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = (args.api_key or "").strip()
    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if args.check_setup:
        sys.exit(
            run_setup_check(
                entsoe_key=entsoe_key,
                arena_key=arena_key,
                api_base=args.api_base,
                data_source=data_source,
            )
        )

    if args.list_open_challenges:
        try:
            challenge_infos = get_challenge_infos(
                args.api_base,
                arena_api_key=arena_key or None,
            )
        except Exception as exc:
            print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(1)
        print_open_challenge_infos(
            challenge_infos,
            api_base=args.api_base,
            arena_api_key=arena_key or None,
        )
        return

    if data_source == "entsoe" and not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY is required for --data_source entsoe. "
            "Switch to --data_source smard for the default keyless workflow.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.challenge_id:
        print(
            "Error: --challenge_id is required unless --list_open_challenges or --check_setup is used.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not args.target_date:
        print(
            "Error: --target_date is required unless --list_open_challenges or --check_setup is used.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        target_date = parse_target_date(args.target_date)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

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
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if not str(exc).strip():
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    try:
        saved_path = save_payload_to_file(payload, args.save_payload)
    except Exception as exc:
        print(f"Error: failed to save payload: {exc}", file=sys.stderr)
        sys.exit(1)

    print(
        "Local payload created successfully "
        f"(challenge_id={payload.get('challenge_id')}, file={saved_path})."
    )
    if "target_date" in payload:
        print(f"Target date: {payload['target_date']}")
    if "target_start" in payload:
        print(f"Target start: {payload['target_start']}")
    print("No submission was sent. Inspect the file and then use submit_payload.py.")


if __name__ == "__main__":
    main()
