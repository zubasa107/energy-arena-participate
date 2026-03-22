from __future__ import annotations

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
        challenge_id = entry.get("challenge_id")
        if isinstance(challenge_id, str) and challenge_id:
            lookup[challenge_id] = entry
    return lookup
