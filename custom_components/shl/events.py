"""Deterministic play-by-play ordering and revision-aware deduplication."""

from __future__ import annotations

from typing import Any

from .discovery import is_finished_state, is_live_state, is_period_break


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


def lifecycle_events(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    team_code: str,
    ended_periods: set[tuple[str, int]],
) -> list[tuple[str, dict[str, Any]]]:
    """Decide which game lifecycle events a game-state transition fires.

    Returns (event_type, payload) pairs in firing order. ``previous`` is the
    stored game data: ``None`` right after setup or a restart establishes a
    baseline and fires nothing, while an empty dict (no game selected) lets a
    newly appearing game fire ``shl_game_started``.

    ``ended_periods`` tracks (game_uuid, period) pairs whose
    ``shl_period_ended`` already fired and is updated in place, so a
    transitional feed state (Ongoing with the old period at the next puck
    drop) cannot make the same period end fire twice.
    """
    if previous is None:
        return []
    game_uuid = str(current.get("gameUuid") or "")
    context = {
        "game_uuid": game_uuid,
        "team_code": team_code,
        "home_team": current.get("home_team"),
        "away_team": current.get("away_team"),
    }
    if previous.get("gameUuid") != game_uuid:
        # The selection switched to a newly started game.
        old_state = None
        old_period = 0
    else:
        old_state = previous.get("state")
        old_period = _int(previous.get("period"))
    new_state = current.get("state")
    new_period = _int(current.get("period"))
    fired: list[tuple[str, dict[str, Any]]] = []

    def period_ended(period: int) -> None:
        if period > 0 and (game_uuid, period) not in ended_periods:
            fired.append(("shl_period_ended", {**context, "period": period}))
            ended_periods.add((game_uuid, period))

    if old_state != new_state:
        if not is_live_state(old_state) and is_live_state(new_state):
            fired.append(("shl_game_started", context))
        if is_live_state(old_state) and is_finished_state(new_state):
            fired.append(("shl_game_ended", context))
            if not is_period_break(old_state):
                period_ended(old_period)
    if new_period > old_period:
        if not is_period_break(old_state):
            period_ended(old_period)
        fired.append(("shl_period_started", {**context, "period": new_period}))
    elif old_period > 0 and is_period_break(new_state) and not is_period_break(old_state):
        period_ended(old_period)
    return fired
