"""Schedule response parsing and team-specific game discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .api import ShlApi, ShlApiError


@dataclass(frozen=True)
class ScheduleGame:
    """The schedule fields needed before fetching live game details."""

    game_uuid: str
    start_time: datetime | None
    state: str
    home_team: dict[str, Any]
    away_team: dict[str, Any]
    raw: dict[str, Any]

    @property
    def is_live(self) -> bool:
        return is_live_state(self.state)

    @property
    def is_finished(self) -> bool:
        return is_finished_state(self.state)

    def started_recently(self, now: datetime | None = None) -> bool:
        return not self.is_finished and self.within_active_window(now)

    def within_active_window(
        self, now: datetime | None = None, window: timedelta = timedelta(hours=6)
    ) -> bool:
        """True when the game started recently, live or already finished."""
        if self.start_time is None:
            return False
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return timedelta(0) <= now - self.start_time <= window


def normalize_state(value: Any) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value or ""))
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def is_live_state(value: Any) -> bool:
    state = normalize_state(value)
    live = (
        state in {"live", "in_progress", "game_started", "started", "period_break", "intermission", "overtime", "shootout", "ongoing"}
        or "period" in state
        or "overtime" in state
        or "shootout" in state
        or "intermission" in state
        or state.endswith("_live")
    )
    return live and not is_finished_state(state)


def is_finished_state(value: Any) -> bool:
    state = normalize_state(value)
    return any(term in state for term in (
        "finished", "ended", "final", "completed", "cancelled", "postponed", "post_game"
    ))


def is_cancelled_state(value: Any) -> bool:
    state = normalize_state(value)
    return "cancelled" in state or "postponed" in state


def is_period_break(value: Any) -> bool:
    state = normalize_state(value)
    return "break" in state or "intermission" in state


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if mapping.get(key) is not None:
            return mapping[key]
    return None


def _team(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    nested = raw.get("teamInfo") or raw.get("team")
    if isinstance(nested, dict):
        return {**raw, **nested}
    return raw


def team_codes(team: dict[str, Any]) -> set[str]:
    names = team.get("names") if isinstance(team.get("names"), dict) else {}
    codes = {
        str(value).strip().upper()
        for value in [
            *(team.get(key) for key in ("teamCode", "code", "shortName", "teamShortName")),
            *(names.get(key) for key in ("short", "shortName", "code", "codeSite")),
        ]
        if value
    }
    # SHL has used both SKE and SAIK for Skellefteå in different feeds.
    if "SAIK" in codes:
        codes.add("SKE")
    if "SKE" in codes:
        codes.add("SAIK")
    return codes


def parse_team_standing(payload: Any, configured_team_code: str) -> dict[str, Any] | None:
    """Select and normalize one team's row from the SHL standings response."""
    if not isinstance(payload, dict):
        return None
    rows = payload.get("leagueStandings")
    if not isinstance(rows, list):
        return None
    # Keep a compact, JSON-safe copy of the complete table for the League
    # position sensor. The standalone team fields below remain convenient for
    # the numeric sensors.
    all_teams = []
    configured = configured_team_code.strip().upper()
    selected: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        info = row.get("info") if isinstance(row.get("info"), dict) else {}
        team_info = info.get("teamInfo") if isinstance(info.get("teamInfo"), dict) else {}
        names = team_info.get("teamNames") if isinstance(team_info.get("teamNames"), dict) else {}
        team_name = (
            team_info.get("siteTeamDisplayName") or names.get("full")
            or names.get("long") or names.get("short") or info.get("code")
        )
        all_teams.append({
            "team_code": row.get("id") or team_info.get("teamId"),
            "team_name": team_name,
            "rank": row.get("rank"),
            "points": row.get("P"),
            "games_played": row.get("GP"),
            "wins": row.get("W"),
            "overtime_wins": row.get("OTW"),
            "overtime_losses": row.get("OTL"),
            "losses": row.get("L"),
            "goals_for": row.get("GF"),
            "goals_against": row.get("GA"),
            "goal_difference": row.get("Diff"),
        })
        if selected is not None:
            continue
        candidate_codes = {
            str(value).strip().upper()
            for value in (
                row.get("id"), info.get("code"), info.get("teamId"),
                team_info.get("teamId"), names.get("code"), names.get("code_site"),
                names.get("codeSite"),
            )
            if value
        }
        if "SAIK" in candidate_codes:
            candidate_codes.add("SKE")
        if "SKE" in candidate_codes:
            candidate_codes.add("SAIK")
        if configured not in candidate_codes:
            continue
        selected = {
            "team_code": configured,
            "team_name": team_name,
            "rank": row.get("rank"),
            "rank_diff": row.get("rankDiff"),
            "points": row.get("P"),
            "games_played": row.get("GP"),
            "wins": row.get("W"),
            "overtime_wins": row.get("OTW"),
            "overtime_losses": row.get("OTL"),
            "losses": row.get("L"),
            "goals_for": row.get("GF"),
            "goals_against": row.get("GA"),
            "goal_difference": row.get("Diff"),
        }
    if selected is None:
        return None
    all_teams.sort(key=lambda team: team.get("rank") or 999)
    return {
        **selected,
        "teams": len(rows),
        "league_standings": all_teams,
        "season": payload.get("season"),
        "game_type": payload.get("gameType"),
    }


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def schedule_local_offset(raw: dict[str, Any]) -> timedelta | None:
    """The schedule row's local-to-UTC offset, for converting feed timestamps.

    `rawStartDateTime` is UTC while `startDateTime` is timezone-less local
    time; their difference is the offset of the feed's naive timestamps.
    """
    utc_start = _parse_datetime(raw.get("rawStartDateTime"))
    local_start = _parse_datetime(raw.get("startDateTime"))
    if utc_start is None or local_start is None:
        return None
    return local_start - utc_start


def _game_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract schedule rows from observed and commonly wrapped responses."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("gameInfo", "games", "gameList", "schedule", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            nested = _game_rows(value)
            if nested:
                return nested
    return []


def parse_schedule(payload: Any) -> list[ScheduleGame]:
    games: list[ScheduleGame] = []
    for row in _game_rows(payload):
        game_uuid = _first(row, "uuid", "gameUuid", "gameUUID")
        if not game_uuid:
            continue
        state = _first(row, "state", "gameState", "status") or "unknown"
        home = _team(_first(row, "homeTeamInfo", "homeTeam", "home") or {})
        away = _team(_first(row, "awayTeamInfo", "awayTeam", "away") or {})
        games.append(ScheduleGame(
            game_uuid=str(game_uuid),
            start_time=_parse_datetime(_first(row, "rawStartDateTime", "startDateTime", "startTime")),
            state=str(state), home_team=home, away_team=away, raw=row,
        ))
    return games


def parse_team_options(payload: Any) -> list[dict[str, str]]:
    """Extract selectable team code/name pairs from schedule data."""
    if not isinstance(payload, dict):
        return []
    raw_teams = payload.get("teamList")
    teams = [team for team in raw_teams if isinstance(team, dict)] if isinstance(raw_teams, list) else []
    if not teams:
        for row in _game_rows(payload):
            for key in ("homeTeamInfo", "awayTeamInfo", "homeTeam", "awayTeam"):
                value = row.get(key)
                if isinstance(value, dict):
                    teams.append(value)

    options: dict[str, str] = {}
    for team in teams:
        names = team.get("teamNames") or team.get("names")
        names = names if isinstance(names, dict) else {}
        # teamCode matches schedule rows; codeSite can be a display label such
        # as "DIF Herr" and should only be used when the stable code is absent.
        code = str(
            team.get("teamCode") or team.get("code") or names.get("code")
            or names.get("codeSite") or names.get("code_site") or ""
        ).strip().upper()
        if code == "SAIK":
            code = "SKE"
        if not code:
            continue
        name = (
            names.get("long") or names.get("longSite") or names.get("long_site")
            or team.get("displayName") or names.get("full") or names.get("short")
        )
        if name:
            options.setdefault(code, str(name).strip())
    return [
        {"code": code, "name": name}
        for code, name in sorted(options.items(), key=lambda item: item[1].casefold())
    ]


def _option_uuid(options: Any, preferred: str | None = None) -> str | None:
    if not isinstance(options, list):
        return None
    for option in options:
        if not isinstance(option, dict):
            continue
        if preferred and str(option.get("code", "")).upper() == preferred.upper():
            return str(option.get("uuid")) if option.get("uuid") else None
        if preferred and isinstance(option.get("names"), list):
            labels = " ".join(
                str(item.get("translation", "")) for item in option["names"]
                if isinstance(item, dict)
            )
            if preferred.lower() in labels.lower() and option.get("uuid"):
                return str(option["uuid"])
        if not preferred and option.get("uuid"):
            return str(option["uuid"])
    return None


def schedule_identifiers(
    payload: Any, series_code: str = "SHL", season_label: str | None = None
) -> tuple[str | None, str | None, str | None]:
    """Select the identifiers from the live filter endpoint response."""
    if not isinstance(payload, dict):
        return None, None, None
    default_filter = payload.get("defaultSsgtFilter")
    default_filter = default_filter if isinstance(default_filter, dict) else {}
    season = default_filter.get("season") or payload.get("seasonUuid")
    series = default_filter.get("series") or payload.get("seriesUuid")
    game_type = default_filter.get("gameType") or payload.get("gameTypeUuid")

    seasons = payload.get("season")
    if not season and season_label and isinstance(seasons, list):
        for option in seasons:
            if not isinstance(option, dict):
                continue
            labels = [
                str(item.get("translation", ""))
                for item in option.get("names", []) if isinstance(item, dict)
            ]
            if season_label in labels or str(option.get("code", "")) == season_label.split("/")[0]:
                season = option.get("uuid")
                break
    season = season or _option_uuid(seasons)
    series = series or _option_uuid(payload.get("series"), series_code)
    game_type = game_type or _option_uuid(payload.get("gameType"))
    return (
        str(season) if season else None,
        str(series) if series else None,
        str(game_type) if game_type else None,
    )


def game_type_identifiers(payload: Any) -> list[str]:
    """Return every game type offered for the selected season and series."""
    if not isinstance(payload, dict):
        return []
    game_types = payload.get("gameType")
    if isinstance(game_types, list):
        identifiers = [
            str(option["uuid"])
            for option in game_types
            if isinstance(option, dict) and option.get("uuid")
        ]
        if identifiers:
            return list(dict.fromkeys(identifiers))
    default = payload.get("defaultSsgtFilter")
    if isinstance(default, dict) and default.get("gameType"):
        return [str(default["gameType"])]
    return []


def latest_ssgt_identifiers(payload: Any) -> tuple[str | None, str | None, str | None]:
    """Extract season, series, and game-type UUIDs from latest-SSGT."""
    if not isinstance(payload, dict):
        return None, None, None
    season = payload.get("season") if isinstance(payload.get("season"), dict) else {}
    series = payload.get("series") if isinstance(payload.get("series"), dict) else {}
    game_type = payload.get("gameType") if isinstance(payload.get("gameType"), dict) else {}
    return tuple(
        str(value.get("uuid")) if value.get("uuid") else None
        for value in (season, series, game_type)
    )  # type: ignore[return-value]


def choose_current_game(games: list[ScheduleGame], team_code: str, now: datetime | None = None) -> ScheduleGame | None:
    """Select the team's current game: the live one, or the most recently started.

    A finished game stays selected until the next game starts, so its final
    score and statistics remain visible. Cancelled and postponed games are
    never selected.
    """
    team_code = team_code.strip().upper()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    matching = [game for game in games if team_code in team_codes(game.home_team) | team_codes(game.away_team)]
    live = [game for game in matching if game.is_live]
    if live:
        return max(live, key=lambda game: game.start_time or datetime.min.replace(tzinfo=timezone.utc))
    started = [
        game for game in matching
        if game.start_time is not None
        and game.start_time <= now
        and not is_cancelled_state(game.state)
    ]
    if started:
        return max(started, key=lambda game: game.start_time)
    return None


def choose_next_game(
    games: list[ScheduleGame], team_code: str, now: datetime,
    current_game: ScheduleGame | None = None,
) -> ScheduleGame | None:
    """Select the next scheduled game, including a selected pre-game fixture."""
    now = now.astimezone(timezone.utc)
    current_is_active = bool(
        current_game and (current_game.is_live or current_game.started_recently(now))
    )
    candidates = []
    for game in games:
        if (
            game.is_finished
            or not game.start_time
            or team_code.strip().upper() not in team_codes(game.home_team) | team_codes(game.away_team)
        ):
            continue
        if current_is_active and current_game and current_game.start_time:
            if game.start_time <= current_game.start_time:
                continue
        elif game.start_time < now:
            continue
        candidates.append(game)
    return min(candidates, key=lambda game: game.start_time) if candidates else None


def current_season_label(now: datetime | None = None) -> str:
    """SHL season label, which turns over in summer."""
    now = now or datetime.now(timezone.utc)
    start_year = now.year if now.month >= 6 else now.year - 1
    return f"{start_year}/{start_year + 1}"


async def _current_schedule_payloads(api: ShlApi) -> list[dict[str, Any]]:
    """Resolve the active SHL season and fetch its schedule payloads."""
    season_label = current_season_label()
    initial_filter = await api.season_series_game_types_filter("SHL", season_label)
    season_uuid, series_uuid, fallback_game_type = schedule_identifiers(
        initial_filter, season_label=season_label
    )
    if not season_uuid or not series_uuid:
        raise ShlApiError("SHL filter response did not include season and series identifiers")

    # latest-ssgt is the same source used by the SHL website to find the active
    # season/series/game type (including the current postseason when active).
    try:
        latest = await api.latest_ssgt(series_uuid)
    except ShlApiError:
        latest = None
    latest_season, latest_series, latest_game_type = latest_ssgt_identifiers(latest)
    if latest_game_type:
        season_uuid = latest_season or season_uuid
        series_uuid = latest_series or series_uuid
        game_type_uuids = [latest_game_type]
    else:
        # The selected filter response lists every applicable game type.
        try:
            selected_filter = await api.season_series_game_types_filter(series_uuid, season_uuid)
        except ShlApiError:
            selected_filter = initial_filter
        game_type_uuids = game_type_identifiers(selected_filter)
        if not game_type_uuids and fallback_game_type:
            game_type_uuids = [fallback_game_type]
    if not game_type_uuids:
        raise ShlApiError("SHL API did not provide an active game type")

    schedules: list[dict[str, Any]] = []
    for game_type_uuid in game_type_uuids:
        schedule = await api.game_schedule(season_uuid, series_uuid, game_type_uuid)
        schedules.append(schedule)
    return schedules


async def discover_team_options(api: ShlApi) -> list[dict[str, str]]:
    """Fetch current SHL teams for the config flow selector."""
    schedules = await _current_schedule_payloads(api)
    options: dict[str, str] = {}
    for schedule in schedules:
        for team in parse_team_options(schedule):
            options.setdefault(team["code"], team["name"])
    if not options:
        raise ShlApiError("SHL schedule did not include any team options")
    return [
        {"code": code, "name": name}
        for code, name in sorted(options.items(), key=lambda item: item[1].casefold())
    ]


async def discover_team_game(api: ShlApi, team_code: str) -> tuple[ScheduleGame | None, list[ScheduleGame]]:
    """Resolve current schedule identifiers and pick a team's current game."""
    games_by_uuid: dict[str, ScheduleGame] = {}
    for schedule in await _current_schedule_payloads(api):
        games_by_uuid.update({game.game_uuid: game for game in parse_schedule(schedule)})
    games = list(games_by_uuid.values())
    return choose_current_game(games, team_code), games
