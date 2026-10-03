"""Normalize SHL payloads independently from Home Assistant entities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def _player_name(player: dict[str, Any] | None) -> str | None:
    if not player:
        return None
    name = f"{player.get('firstName', '')} {player.get('familyName', '')}".strip()
    return name or player.get("name")


@dataclass(frozen=True)
class GoalEvent:
    """Normalized scoring event; `event_uuid` is its stable identity."""

    event_uuid: str
    event_id: int
    revision: int
    game_uuid: str
    team_code: str
    team_name: str
    player_id: str | None
    player_name: str | None
    jersey: str | None
    period: int | None
    time: str | None
    home_score: int | None
    away_score: int | None
    goal_status: str | None
    is_penalty_shot: bool
    is_empty_net: bool
    assists: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload suitable for HA event data."""
        return asdict(self)


def parse_goal(event: dict[str, Any]) -> GoalEvent | None:
    """Parse a play-by-play goal event; ignore other event types."""
    if str(event.get("type", "")).lower() != "goal":
        return None
    team = event.get("eventTeam") or {}
    team = team if isinstance(team, dict) else {}
    player = event.get("player") or {}
    player = player if isinstance(player, dict) else {}
    assists_obj = event.get("assists") or {}
    if isinstance(assists_obj, list):
        assists = tuple(item for item in assists_obj if isinstance(item, dict))
    elif isinstance(assists_obj, dict):
        assists = tuple(
            assists_obj[key] for key in ("first", "second")
            if isinstance(assists_obj.get(key), dict)
        )
    else:
        assists = ()
    return GoalEvent(
        event_uuid=str(event.get("eventUuid") or ""),
        event_id=_as_int(event.get("eventId")),
        revision=_as_int(event.get("revision")),
        game_uuid=str(event.get("gameUuid") or ""),
        team_code=str(team.get("teamCode") or ""),
        team_name=str(team.get("teamName") or ""),
        player_id=str(player["playerId"]) if player.get("playerId") is not None else None,
        player_name=_player_name(player),
        jersey=str(player["jerseyToday"]) if player.get("jerseyToday") is not None else None,
        period=_optional_int(event.get("period")),
        time=str(event["time"]) if event.get("time") is not None else None,
        home_score=_optional_int(event.get("homeGoals")),
        away_score=_optional_int(event.get("awayGoals")),
        goal_status=str(event["goalStatus"]) if event.get("goalStatus") is not None else None,
        is_penalty_shot=_as_bool(event.get("isPenaltyShot", False)),
        is_empty_net=_as_bool(event.get("isEmptyNetGoal", False)),
        assists=assists,
    )


def parse_live_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Get current scoreboard and clock values from the newest event row."""
    if not events:
        return {}
    try:
        latest = max(
            events,
            key=lambda item: (_as_int(item.get("eventId")), _as_int(item.get("revision"))),
        )
    except (TypeError, ValueError):
        return {}
    snapshot: dict[str, Any] = {}
    for source, target in (
        ("period", "period"), ("time", "time"), ("gameState", "state"),
        ("realWorldTime", "realWorldTime"), ("updatedTime", "updatedTime"),
    ):
        if latest.get(source) is not None:
            snapshot[target] = latest[source]
    for side in ("homeTeam", "awayTeam"):
        value = latest.get(side)
        if isinstance(value, dict):
            snapshot["home_team" if side == "homeTeam" else "away_team"] = value
    return snapshot


def parse_game_overview(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize SHL's dedicated scoreboard/clock response."""
    result: dict[str, Any] = {}
    for source, target in (("gameUuid", "gameUuid"), ("state", "state")):
        if payload.get(source) is not None:
            result[target] = payload[source]
    time_data = payload.get("time") if isinstance(payload.get("time"), dict) else {}
    if time_data.get("period") is not None:
        result["period"] = _optional_int(time_data["period"])
    if time_data.get("periodTime") is not None:
        result["time"] = str(time_data["periodTime"])
    for side, score_key in (("homeTeam", "homeGoals"), ("awayTeam", "awayGoals")):
        team = payload.get(side)
        if not isinstance(team, dict):
            continue
        normalized = dict(team)
        score = payload.get(score_key)
        if score is None:
            score = team.get("score")
        if score is not None:
            normalized["score"] = _optional_int(score)
        result["home_team" if side == "homeTeam" else "away_team"] = normalized
    return result


def parse_shots_on_goal(payload: Any) -> dict[str, int | None]:
    """Extract each team's total shots on goal from SHL game statistics."""
    result: dict[str, int | None] = {"home": None, "away": None}
    if not isinstance(payload, dict):
        return result
    for side in ("home", "away"):
        team = payload.get(side)
        if not isinstance(team, dict):
            continue
        periods = team.get("statistics")
        if not isinstance(periods, list):
            continue
        total = next(
            (period for period in periods
             if isinstance(period, dict) and _as_int(period.get("period"), -1) == 0),
            None,
        )
        if not isinstance(total, dict):
            continue
        stats = total.get("parsedTotalStatistics")
        if not isinstance(stats, list):
            continue
        stat = next(
            (item for item in stats
             if isinstance(item, dict) and item.get("key") == "SOG"),
            None,
        )
        if isinstance(stat, dict):
            result[side] = _optional_int(stat.get("value"))
    return result
