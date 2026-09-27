"""Deterministic play-by-play ordering and revision-aware deduplication."""

from __future__ import annotations

from typing import Any


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def process_play_by_play(
    events: list[dict[str, Any]], seen_revisions: dict[str, int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return changed events in event order and newly observed goals.

    `eventUuid` is the stable identity. A higher revision updates that event
    once and is marked as a correction; it never generates a second goal.
    The observed SHL array may be newest-first, so output is explicitly sorted.
    """
    latest_by_uuid: dict[str, dict[str, Any]] = {}
    for event in events:
        uid = event.get("eventUuid")
        if not uid:
            continue
        uid = str(uid)
        previous_row = latest_by_uuid.get(uid)
        if previous_row is None or (
            _int(event.get("revision")), _int(event.get("eventId"))
        ) > (
            _int(previous_row.get("revision")), _int(previous_row.get("eventId"))
        ):
            latest_by_uuid[uid] = event

    changed: list[dict[str, Any]] = []
    new_goals: list[dict[str, Any]] = []
    for event in sorted(
        latest_by_uuid.values(),
        key=lambda item: (_int(item.get("eventId")), _int(item.get("revision"))),
    ):
        uid = event.get("eventUuid")
        if not uid:
            continue
        uid = str(uid)
        revision = _int(event.get("revision"))
        previous = seen_revisions.get(uid)
        if previous is not None and revision <= previous:
            continue
        is_new = previous is None
        seen_revisions[uid] = revision
        normalized = {**event, "eventUuid": uid, "revision": revision, "isCorrection": not is_new}
        changed.append(normalized)
        if is_new and str(event.get("type", "")).lower() == "goal":
            new_goals.append(normalized)
    return changed, new_goals
