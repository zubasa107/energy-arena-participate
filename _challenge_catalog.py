from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict

import requests


def get_challenge_infos(
    api_base: str,
    arena_api_key: str | None = None,
) -> Dict[str, Any]:
    """
    Fetch the currently open challenge catalog from the Energy Arena API.

    Returns the JSON body as a dictionary with an ``active_challenges`` list.
    Raises RuntimeError on request or payload errors.
    """
    url = f"{api_base.rstrip('/')}/api/v1/challenges/open"
    api_key = (arena_api_key or "").strip()
    headers = {"X-API-Key": api_key} if api_key else None

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch open challenges: {exc}") from exc

    if not response.ok:
        detail = response.text.strip()
        message = f"HTTP {response.status_code}"
        if detail:
            message = f"{message} - {detail}"
        raise RuntimeError(f"Failed to fetch open challenges: {message}")

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Open challenge endpoint did not return valid JSON."
        ) from exc

    if not isinstance(body, dict):
        raise RuntimeError("Open challenge endpoint returned an unexpected payload.")

    active = body.get("active_challenges")
    if active is None:
        body["active_challenges"] = []
        return body
    if not isinstance(active, list):
        raise RuntimeError(
            "Open challenge endpoint returned an invalid active_challenges field."
        )

    return body


def get_active_challenge_lookup(
    api_base: str,
    arena_api_key: str | None = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Return active challenges keyed by ``challenge_id`` for quick lookups.
    """
    body = get_challenge_infos(api_base, arena_api_key=arena_api_key)
    lookup: Dict[str, Dict[str, Any]] = {}
    for entry in body.get("active_challenges", []):
        if not isinstance(entry, dict):
            continue
        challenge_id = str(entry.get("challenge_id") or "").strip()
        if challenge_id:
            lookup[challenge_id] = entry
    return lookup


def parse_catalog_datetime(raw: Any) -> datetime | None:
    """
    Parse an ISO-8601 datetime string returned by the challenge catalog.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def resolve_target_start_from_entry(entry: Dict[str, Any]) -> datetime | None:
    """
    Return the canonical ``next_target_start`` timestamp for one open challenge.
    """
    return parse_catalog_datetime(entry.get("next_target_start"))


def resolve_target_date_from_entry(entry: Dict[str, Any]) -> date | None:
    """
    Return the target date implied by ``next_target_start`` for one open challenge.
    """
    next_target_start = resolve_target_start_from_entry(entry)
    if next_target_start is None:
        return None
    return next_target_start.date()


def get_challenge_detail(
    api_base: str,
    challenge_id: str,
    arena_api_key: str | None = None,
) -> Dict[str, Any]:
    """
    Fetch full challenge metadata for one challenge id.

    The endpoint is public, but an Arena API key may still be passed for
    consistency with other helpers.
    """
    url = f"{api_base.rstrip('/')}/api/v1/challenges/{str(challenge_id).strip()}"
    api_key = (arena_api_key or "").strip()
    headers = {"X-API-Key": api_key} if api_key else None

    try:
        response = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to fetch challenge detail for {challenge_id}: {exc}"
        ) from exc

    if not response.ok:
        detail = response.text.strip()
        message = f"HTTP {response.status_code}"
        if detail:
            message = f"{message} - {detail}"
        raise RuntimeError(
            f"Failed to fetch challenge detail for {challenge_id}: {message}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Challenge detail endpoint returned invalid JSON for {challenge_id}."
        ) from exc

    if not isinstance(body, dict):
        raise RuntimeError(
            f"Challenge detail endpoint returned an unexpected payload for {challenge_id}."
        )
    return body
