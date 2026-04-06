#!/usr/bin/env python3
"""
Run daily submissions for all currently open challenges.

Default target start: each selected challenge's next_target_start from the open
challenge API response.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _challenge_catalog import (  # noqa: E402
    get_challenge_infos,
    resolve_target_start_from_entry,
)
from _starter_core import (  # noqa: E402
    DEFAULT_API_BASE,
    _get_default_data_source,
    _load_env_file,
    _normalized_data_source,
    build_payload,
    parse_target_date,
    parse_target_start,
    save_payload_to_file,
    submit,
)


def _load_local_env_values() -> dict:
    repo_root = Path(__file__).resolve().parent
    return _load_env_file(repo_root / ".env")


def _payload_archive_root() -> Path:
    return Path(__file__).resolve().parent / "submitted_payloads"


def _safe_name_fragment(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)


def _archive_payload(
    *,
    payload: dict,
    challenge_id: str,
    area: str | None,
    dry_run: bool,
) -> Path:
    archive_root = _payload_archive_root()
    challenge_dir = archive_root / f"challenge_{_safe_name_fragment(challenge_id)}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target_start = str(payload.get("target_start") or "").strip()
    target_date = str(payload.get("target_date") or "").strip()
    filename_parts = [timestamp]
    if target_start:
        filename_parts.append(f"target_start_{_safe_name_fragment(target_start)}")
    elif target_date:
        filename_parts.append(f"target_date_{_safe_name_fragment(target_date)}")
    area_part = _safe_name_fragment(area)
    if area_part:
        filename_parts.append(f"area_{area_part}")
    if dry_run:
        filename_parts.append("dry_run")
    filename = "__".join(filename_parts) + ".json"
    return save_payload_to_file(payload, str(challenge_dir / filename))


def main() -> None:
    local_env = _load_local_env_values()
    parser = argparse.ArgumentParser(
        description="Submit forecasts for all currently open challenges."
    )
    parser.add_argument(
        "--target_date",
        type=str,
        default=None,
        help=(
            "Calendar-day shortcut in DD-MM-YYYY. Prefer --target_start for new "
            "work. If both target arguments are omitted, each challenge uses its "
            "next_target_start from the open challenge API."
        ),
    )
    parser.add_argument(
        "--target_start",
        type=str,
        default=None,
        help=(
            "Canonical target-period start in ISO8601 with timezone. When set, "
            "all selected challenges use this same target_start override."
        ),
    )
    parser.add_argument(
        "--data_source",
        type=str,
        default=_get_default_data_source(local_env),
        choices=["entsoe", "smard"],
        help="Baseline source for the built-in forecast generator (default: smard).",
    )
    parser.add_argument(
        "--challenge_id",
        action="append",
        default=[],
        help="Optional challenge id filter. Pass multiple times to limit the batch.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Build payloads only; do not submit.",
    )
    parser.add_argument(
        "--use_global_env",
        action="store_true",
        help="Allow fallback to globally set ENTSOE_API_KEY/ARENA_API_KEY if missing in local .env.",
    )
    parser.add_argument(
        "--include_quantiles",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--include_ensemble",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.include_quantiles or args.include_ensemble:
        print(
            "Warning: --include_quantiles and --include_ensemble are ignored. "
            "Each challenge now defines its own forecast objective.",
            file=sys.stderr,
        )
    if args.target_date and args.target_start:
        print(
            "Error: pass either --target_date or --target_start, not both.",
            file=sys.stderr,
        )
        sys.exit(1)

    data_source = _normalized_data_source(args.data_source)
    entsoe_key = local_env.get("ENTSOE_API_KEY", "").strip()
    arena_key = local_env.get("ARENA_API_KEY", "").strip()
    api_base = (
        local_env.get("ARENA_API_BASE_URL", "")
        or os.environ.get("ARENA_API_BASE_URL", "")
        or DEFAULT_API_BASE
    ).strip()

    if args.use_global_env:
        entsoe_key = entsoe_key or os.environ.get("ENTSOE_API_KEY", "").strip()
        arena_key = arena_key or os.environ.get("ARENA_API_KEY", "").strip()

    if data_source == "entsoe" and not entsoe_key:
        print(
            "Error: ENTSOE_API_KEY is required for --data_source entsoe.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not arena_key and not args.dry_run:
        print(
            "Error: ARENA_API_KEY must be set in local .env "
            "(or use --use_global_env / --dry_run).",
            file=sys.stderr,
        )
        sys.exit(1)

    explicit_target_date: date | None = None
    explicit_target_start = None
    if args.target_date:
        try:
            explicit_target_date = parse_target_date(args.target_date)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    if args.target_start:
        try:
            explicit_target_start = parse_target_start(args.target_start)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        challenge_infos = get_challenge_infos(api_base, arena_api_key=arena_key or None)
    except Exception as exc:
        print(f"Error: failed to fetch open challenges: {exc}", file=sys.stderr)
        sys.exit(1)

    active_entries = [
        entry
        for entry in (challenge_infos.get("active_challenges") or [])
        if isinstance(entry, dict) and str(entry.get("challenge_id") or "").strip()
    ]
    requested_ids = {str(item).strip() for item in args.challenge_id if str(item).strip()}
    if requested_ids:
        active_entries = [
            entry
            for entry in active_entries
            if str(entry.get("challenge_id") or "").strip() in requested_ids
        ]

    if not active_entries:
        print("No matching open challenges found.")
        return

    challenge_ids = [str(entry.get("challenge_id") or "").strip() for entry in active_entries]
    if explicit_target_start is not None:
        print(
            f"Target start override: {explicit_target_start.isoformat()} | source: {data_source} | "
            f"challenges: {challenge_ids}"
        )
    elif explicit_target_date is not None:
        print(
            f"Target date override: {explicit_target_date} | source: {data_source} | "
            f"challenges: {challenge_ids}"
        )
    else:
        print(
            "Target start default: per challenge from API next_target_start | "
            f"source: {data_source} | challenges: {challenge_ids}"
        )
    if args.dry_run:
        print("dry_run: no submissions will be sent.")
    print()

    ok_count = 0
    fail_count = 0
    work_items: list[tuple[dict, date | None, datetime | None]] = []
    for entry in active_entries:
        challenge_id = str(entry.get("challenge_id") or "").strip()
        next_target_start = str(entry.get("next_target_start") or "").strip()
        if explicit_target_start is not None:
            work_items.append((entry, None, explicit_target_start))
            print(
                f"Challenge {challenge_id}: target_start={explicit_target_start.isoformat()}"
            )
            continue
        if explicit_target_date is not None:
            target_date = explicit_target_date
        else:
            target_start = resolve_target_start_from_entry(entry)
            if target_start is None:
                print(
                    "  FAIL "
                    f"{challenge_id}: open challenge metadata does not expose a "
                    "parseable next_target_start. Pass --target_start or --target_date explicitly. "
                    f"(next_target_start={next_target_start or '-'})",
                    file=sys.stderr,
                )
                fail_count += 1
                continue
            print(
                f"Challenge {challenge_id}: target_start={target_start.isoformat()} "
                f"(next_target_start={next_target_start})"
            )
            work_items.append((entry, None, target_start))
            continue
        work_items.append((entry, target_date, None))

    if explicit_target_start is not None:
        print(f"All selected challenges use target_start={explicit_target_start.isoformat()}")
        print()
    elif explicit_target_date is not None:
        print(f"All selected challenges use target_date={explicit_target_date}")
        print()
    elif work_items:
        print()

    if not work_items:
        print("No challenges with a usable target start were found.")
        if fail_count and not args.dry_run:
            sys.exit(1)
        return

    for entry, target_date, target_start in work_items:
        challenge_id = str(entry.get("challenge_id") or "").strip()
        areas = [str(area).strip() for area in (entry.get("areas") or []) if str(area).strip()]
        area = areas[0] if areas else None
        target_label = (
            f"target_start: {target_start.isoformat()}"
            if target_start is not None
            else f"target_date: {target_date}"
        )
        print(f"Running challenge {challenge_id} | area: {area or '-'} | {target_label}")
        try:
            payload = build_payload(
                target_date=target_date,
                target_start=target_start,
                challenge_id=challenge_id,
                area=area,
                entsoe_api_key=entsoe_key,
                api_base=api_base,
                data_source=data_source,
                arena_api_key=arena_key or None,
            )
            archive_path = _archive_payload(
                payload=payload,
                challenge_id=challenge_id,
                area=area,
                dry_run=args.dry_run,
            )
            print(f"  Saved payload archive: {archive_path}")
            ok = submit(
                payload=payload,
                api_key=arena_key,
                api_base=api_base,
                dry_run=args.dry_run,
                verbose=True,
            )
            if ok:
                print(f"  RESULT {challenge_id}: ok")
                ok_count += 1
            else:
                print(f"  RESULT {challenge_id}: failed", file=sys.stderr)
                fail_count += 1
        except Exception as exc:
            print(f"  FAIL {challenge_id}: {exc}", file=sys.stderr)
            fail_count += 1
        print()

    print(f"Done: {ok_count} ok, {fail_count} failed (total {ok_count + fail_count})")
    if fail_count and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
