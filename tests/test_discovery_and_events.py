import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.shl.discovery import (
    choose_team_game,
    choose_next_game,
    current_season_label,
    discover_team_game,
    game_type_identifiers,
    latest_ssgt_identifiers,
    parse_team_standing,
    parse_team_options,
    parse_schedule,
    schedule_identifiers,
)
from custom_components.shl.events import process_play_by_play
from custom_components.shl.polling import (
    effective_standings_interval,
    next_idle_poll_interval,
    standings_should_poll_frequently,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_schedule_and_prefer_active_configured_team_game():
    payload = {
        "gameInfo": [
            {
                "uuid": "previous",
                "startDateTime": "2026-09-26T15:00:00+02:00",
                "state": "GameEnded",
                "homeTeamInfo": {"teamCode": "SKE"},
                "awayTeamInfo": {"teamCode": "LHF"},
            },
            {
                "uuid": "active",
                "startDateTime": "2026-09-26T17:00:00+02:00",
                "state": "Period2",
                "homeTeamInfo": {"teamCode": "SKE"},
                "awayTeamInfo": {"teamCode": "FHC"},
            },
            {
                "uuid": "next",
                "startDateTime": "2026-09-29T19:00:00+02:00",
                "state": "Upcoming",
                "homeTeamInfo": {"teamCode": "SKE"},
                "awayTeamInfo": {"teamCode": "LHF"},
            },
        ]
    }

    games = parse_schedule(payload)
    selected = choose_team_game(
        games, "ske", datetime(2026, 9, 26, 16, 30, tzinfo=timezone.utc)
    )

    assert [game.game_uuid for game in games] == ["previous", "active", "next"]
    assert selected is not None and selected.game_uuid == "active"
    assert selected.is_live


def test_choose_next_game_for_any_configured_team():
    games = parse_schedule({"games": [{
        "gameUuid": "next",
        "rawStartDateTime": "2026-09-29T19:00:00+02:00",
        "state": "Upcoming",
        "homeTeamInfo": {"teamCode": "SKE"},
        "awayTeamInfo": {"teamCode": "LHF"},
    }]})
    selected = choose_team_game(
        games, "LHF", datetime(2026, 9, 26, tzinfo=timezone.utc)
    )
    assert selected is not None and selected.game_uuid == "next"


def test_next_game_includes_pregame_selected_game_and_advances_during_live_game():
    games = parse_schedule({"games": [
        {"gameUuid": "current", "rawStartDateTime": "2026-09-29T17:00:00Z",
         "state": "pre-game", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "LHF"}},
        {"gameUuid": "following", "rawStartDateTime": "2026-10-02T17:00:00Z",
         "state": "pre-game", "homeTeamInfo": {"code": "LHC"},
         "awayTeamInfo": {"code": "SKE"}},
    ]})
    now = datetime(2026, 9, 29, 16, 0, tzinfo=timezone.utc)
    assert choose_next_game(games, "SKE", now, games[0]).game_uuid == "current"

    live = parse_schedule({"games": [{
        "gameUuid": "current-live", "rawStartDateTime": "2026-09-29T15:00:00Z",
        "state": "Period1", "homeTeamInfo": {"code": "SAIK"},
        "awayTeamInfo": {"code": "LHF"},
    }, *[
        {"gameUuid": game.game_uuid, **game.raw}
        for game in games[1:]
    ]]})
    assert choose_next_game(live, "SKE", now, live[0]).game_uuid == "following"


def test_schedule_filter_identifier_extraction_and_season_rollover():
    assert schedule_identifiers(
        _fixture("season_series_game_types_filter.json"),
        season_label="2026/2027",
    ) == ("ndcf81nlb3", "qQ9-bb0bzEWUk", "qQ9-af37Ti40B")
    assert game_type_identifiers(
        _fixture("season_series_game_types_filter_selected.json")
    ) == ["qQ9-af37Ti40B"]
    assert latest_ssgt_identifiers(
        _fixture("latest_ssgt_shl_2026-2027.json")
    ) == ("ndcf81nlb3", "qQ9-bb0bzEWUk", "qQ9-af37Ti40B")
    assert current_season_label(datetime(2027, 2, 1, tzinfo=timezone.utc)) == "2026/2027"


def test_real_play_by_play_exposes_latest_score_period_and_clock():
    from custom_components.shl.models import parse_live_snapshot

    events = _fixture("play_by_play_20260926_OHK_SAIK.json")
    snapshot = parse_live_snapshot(events)
    assert snapshot["state"] == "GameEnded"
    assert snapshot["period"] == 3
    assert snapshot["time"] == "20:00"
    assert snapshot["home_team"]["score"] == 3
    assert snapshot["away_team"]["score"] == 0


def test_game_overview_is_authoritative_over_nested_team_scores():
    from custom_components.shl.models import parse_game_overview

    overview = parse_game_overview(_fixture("game_overview_20260926_OHK_SAIK.json"))
    assert overview["state"] == "GameEnded"
    assert overview["period"] == 3
    assert overview["time"] == "20:00"
    assert overview["home_team"]["score"] == 3
    assert overview["away_team"]["score"] == 0


def test_real_schedule_fixture_matches_ske_and_selects_next_game():
    games = parse_schedule(_fixture("game_schedule_2026-2027_saik.json"))
    selected = choose_team_game(
        games, "SKE", datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
    )
    assert len(games) == 52
    assert selected is not None
    assert selected.game_uuid == "xheynl9ev5"
    assert selected.home_team["code"] == "SAIK"
    assert selected.state == "pre-game"


def test_real_schedule_team_list_produces_named_team_choices():
    options = parse_team_options(_fixture("game_schedule_2026-2027_saik.json"))
    assert len(options) == 14
    assert options == sorted(options, key=lambda team: team["name"].casefold())
    assert {"code": "SKE", "name": "Skellefteå AIK"} in options
    assert {"code": "IFB", "name": "Björklöven"} in options
    assert {"code": "DIF", "name": "Djurgårdens IF"} in options
    assert {"code": "OHK", "name": "Örebro Hockey"} in options
    assert all(team["code"] and team["name"] for team in options)


def test_real_standings_fixture_finds_skelleftea_through_either_team_code():
    standings = _fixture("team_standings_2026-2027.json")
    ske = parse_team_standing(standings, "SKE")
    saik = parse_team_standing(standings, "SAIK")
    assert ske is not None
    assert saik is not None
    assert ske["rank"] == saik["rank"]
    assert ske["points"] == saik["points"]
    assert ske["rank"] == 8
    assert ske["points"] == 4
    assert ske["games_played"] == 3
    assert ske["wins"] == 1
    assert ske["overtime_wins"] == 0
    assert ske["overtime_losses"] == 1
    assert ske["losses"] == 1
    assert ske["goals_for"] == 10
    assert ske["goals_against"] == 9
    assert ske["goal_difference"] == 1
    assert ske["rank_diff"] == -4
    assert ske["team_name"] == "Skellefteå AIK"
    assert ske["teams"] == 14


def test_discovery_uses_latest_ssgt_identifiers_and_schedule():
    class FakeApi:
        def __init__(self):
            self.calls = []

        async def season_series_game_types_filter(self, series, season):
            self.calls.append(("filter", series, season))
            return _fixture("season_series_game_types_filter.json")

        async def latest_ssgt(self, series_uuid):
            self.calls.append(("latest", series_uuid))
            return _fixture("latest_ssgt_shl_2026-2027.json")

        async def game_schedule(self, season_uuid, series_uuid, game_type_uuid):
            self.calls.append(("schedule", season_uuid, series_uuid, game_type_uuid))
            start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            return {"gameInfo": [{
                "uuid": "next-game", "rawStartDateTime": start, "state": "pre-game",
                "homeTeamInfo": {"code": "SAIK"},
                "awayTeamInfo": {"code": "LHF"},
            }]}

    api = FakeApi()
    game, games = asyncio.run(discover_team_game(api, "SKE"))
    assert game is not None and game.game_uuid == "next-game"
    assert len(games) == 1
    assert api.calls[1] == ("latest", "qQ9-bb0bzEWUk")
    assert api.calls[2] == (
        "schedule", "ndcf81nlb3", "qQ9-bb0bzEWUk", "qQ9-af37Ti40B"
    )


def test_play_by_play_orders_and_deduplicates_by_uuid_and_revision():
    events = _fixture("play_by_play_20260926_OHK_SAIK.json")
    seen = {}
    changed, goals = process_play_by_play(events, seen)
    assert [event["eventId"] for event in changed] == sorted(
        event["eventId"] for event in changed
    )
    assert len(goals) == 3
    valid_ids = [event["eventId"] for event in events if event.get("eventId") is not None]
    assert valid_ids[0] > valid_ids[-1]  # captured newest-first

    changed, goals = process_play_by_play(events, seen)
    assert changed == []
    assert goals == []

    original_goal = next(event for event in events if event.get("type") == "goal")
    correction = {**original_goal, "revision": int(original_goal["revision"]) + 1, "homeGoals": 2}
    changed, goals = process_play_by_play([correction], seen)
    assert len(changed) == 1
    assert changed[0]["isCorrection"] is True
    assert changed[0]["homeGoals"] == 2
    assert goals == []


def test_multiple_revisions_in_one_poll_keep_only_latest_revision():
    seen = {}
    changed, goals = process_play_by_play([
        {"eventId": 10, "eventUuid": "goal", "revision": 1, "type": "goal", "homeGoals": 1},
        {"eventId": 10, "eventUuid": "goal", "revision": 2, "type": "goal", "homeGoals": 2},
    ], seen)
    assert len(changed) == 1
    assert changed[0]["revision"] == 2
    assert changed[0]["homeGoals"] == 2
    assert len(goals) == 1


def test_idle_poll_is_scheduled_for_known_game_start():
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    assert next_idle_poll_interval(
        now, [now + timedelta(minutes=2)], timedelta(minutes=15)
    ) == timedelta(minutes=2)


def test_known_start_near_now_uses_fifteen_second_minimum():
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    assert next_idle_poll_interval(
        now, [now + timedelta(seconds=5)], timedelta(minutes=15)
    ) == timedelta(seconds=15)


def test_start_outside_idle_interval_keeps_regular_interval():
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    assert next_idle_poll_interval(
        now, [now + timedelta(minutes=20)], timedelta(minutes=15)
    ) == timedelta(minutes=15)


def test_idle_poll_uses_closest_start_across_league_schedule():
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    starts = [now + timedelta(minutes=20), now + timedelta(minutes=4)]
    assert next_idle_poll_interval(now, starts, timedelta(minutes=60)) == timedelta(minutes=4)


def test_standings_poll_frequently_during_and_after_league_game():
    now = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    live_game = parse_schedule({"games": [{
        "gameUuid": "live", "rawStartDateTime": (now - timedelta(minutes=40)).isoformat(),
        "state": "Period2", "homeTeamInfo": {"code": "SKE"},
        "awayTeamInfo": {"code": "LHF"},
    }]})[0]
    finished_game = parse_schedule({"games": [{
        "gameUuid": "finished", "rawStartDateTime": (now - timedelta(hours=2)).isoformat(),
        "state": "GameEnded", "homeTeamInfo": {"code": "SKE"},
        "awayTeamInfo": {"code": "LHF"},
    }]})[0]
    assert standings_should_poll_frequently(now, [live_game])
    assert standings_should_poll_frequently(now, [finished_game])


def test_standings_uses_separate_active_and_idle_intervals():
    now = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    active_interval = timedelta(minutes=15)
    idle_interval = timedelta(minutes=60)
    active_game = parse_schedule({"games": [{
        "gameUuid": "live", "rawStartDateTime": (now - timedelta(minutes=20)).isoformat(),
        "state": "Period1", "homeTeamInfo": {"code": "SKE"},
        "awayTeamInfo": {"code": "LHF"},
    }]})[0]
    future_game = parse_schedule({"games": [{
        "gameUuid": "future", "rawStartDateTime": (now + timedelta(days=2)).isoformat(),
        "state": "pre-game", "homeTeamInfo": {"code": "SKE"},
        "awayTeamInfo": {"code": "LHF"},
    }]})[0]
    assert effective_standings_interval(
        now, [active_game], active_interval, idle_interval
    ) == active_interval
    assert effective_standings_interval(
        now, [future_game], active_interval, idle_interval
    ) == idle_interval
