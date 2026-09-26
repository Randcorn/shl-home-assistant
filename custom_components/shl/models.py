from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class GoalEvent:
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

def _player_name(player: dict[str, Any] | None) -> str | None:
    if not player:
        return None
    name = f"{player.get('firstName', '')} {player.get('familyName', '')}".strip()
    return name or None

def parse_goal(event: dict[str, Any]) -> GoalEvent | None:
    if event.get("type") != "goal":
        return None
    team = event.get("eventTeam") or {}
    player = event.get("player") or {}
    assists_obj = event.get("assists") or {}
    assists = tuple(
        value for key in ("first", "second")
        if isinstance((value := assists_obj.get(key)), dict)
    )
    return GoalEvent(
        event_uuid=str(event.get("eventUuid", "")),
        event_id=int(event.get("eventId", 0)),
        revision=int(event.get("revision", 0)),
        game_uuid=str(event.get("gameUuid", "")),
        team_code=str(team.get("teamCode", "")),
        team_name=str(team.get("teamName", "")),
        player_id=str(player["playerId"]) if player.get("playerId") else None,
        player_name=_player_name(player),
        jersey=str(player["jerseyToday"]) if player.get("jerseyToday") is not None else None,
        period=event.get("period"),
        time=event.get("time"),
        home_score=event.get("homeGoals"),
        away_score=event.get("awayGoals"),
        goal_status=event.get("goalStatus"),
        is_penalty_shot=bool(event.get("isPenaltyShot", False)),
        is_empty_net=bool(event.get("isEmptyNetGoal", False)),
        assists=assists,
    )
