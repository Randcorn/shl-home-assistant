import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.shl.discovery import (
    choose_current_game,
    choose_next_game,
    current_season_label,
    discover_team_game,
    game_type_identifiers,
    latest_ssgt_identifiers,
    parse_team_standing,
    parse_team_options,
    parse_schedule,
    schedule_identifiers,
    schedule_local_offset,
)
from custom_components.shl.events import process_play_by_play
from custom_components.shl.models import parse_feed_datetime, period_break_start
from custom_components.shl.polling import (
    PERIOD_BREAK_MAX_PAUSE,
    effective_standings_interval,
    next_idle_poll_interval,
    period_break_poll_interval,
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
    now = datetime(2026, 9, 26, 16, 30, tzinfo=timezone.utc)
    selected = choose_current_game(games, "ske", now)

    assert [game.game_uuid for game in games] == ["previous", "active", "next"]
    assert selected is not None and selected.game_uuid == "active"
    assert selected.is_live
    next_game = choose_next_game(games, "SKE", now, selected)
    assert next_game is not None and next_game.game_uuid == "next"


def test_choose_next_game_for_any_configured_team():
    games = parse_schedule({"games": [{
        "gameUuid": "next",
        "rawStartDateTime": "2026-09-29T19:00:00+02:00",
        "state": "Upcoming",
        "homeTeamInfo": {"teamCode": "SKE"},
        "awayTeamInfo": {"teamCode": "LHF"},
    }]})
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    assert choose_current_game(games, "LHF", now) is None
    selected = choose_next_game(games, "LHF", now)
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


def test_real_schedule_fixture_selects_finished_game_and_next_game():
    games = parse_schedule(_fixture("game_schedule_2026-2027_saik.json"))
    now = datetime(2026, 9, 26, 19, 0, tzinfo=timezone.utc)
    selected = choose_current_game(games, "SKE", now)
    assert len(games) == 52
    assert selected is not None
    assert selected.game_uuid == "u0ribje54r"
    assert selected.is_finished
    assert selected.away_team["code"] == "SAIK"
    next_game = choose_next_game(games, "SKE", now, selected)
    assert next_game is not None
    assert next_game.game_uuid == "xheynl9ev5"
    assert next_game.home_team["code"] == "SAIK"
    assert next_game.state == "pre-game"


def test_finished_game_stays_current_until_next_game_starts():
    games = parse_schedule({"games": [
        {"gameUuid": "finished", "rawStartDateTime": "2026-10-10T16:00:00Z",
         "state": "post-game", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "RBK"}},
        {"gameUuid": "upcoming", "rawStartDateTime": "2026-10-15T17:00:00Z",
         "state": "pre-game", "homeTeamInfo": {"code": "VLH"},
         "awayTeamInfo": {"code": "SAIK"}},
    ]})
    now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    current = choose_current_game(games, "SKE", now)
    assert current is not None and current.game_uuid == "finished"
    assert choose_next_game(games, "SKE", now, current).game_uuid == "upcoming"

    live_games = parse_schedule({"games": [
        {"gameUuid": "finished", "rawStartDateTime": "2026-10-10T16:00:00Z",
         "state": "post-game", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "RBK"}},
        {"gameUuid": "upcoming", "rawStartDateTime": "2026-10-15T17:00:00Z",
         "state": "Period1", "homeTeamInfo": {"code": "VLH"},
         "awayTeamInfo": {"code": "SAIK"}},
    ]})
    current = choose_current_game(live_games, "SKE", datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc))
    assert current is not None and current.game_uuid == "upcoming"
    assert current.is_live


def test_live_game_is_preferred_over_finished_game():
    games = parse_schedule({"games": [
        {"gameUuid": "finished", "rawStartDateTime": "2026-10-10T16:00:00Z",
         "state": "post-game", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "RBK"}},
        {"gameUuid": "live", "rawStartDateTime": "2026-10-11T17:00:00Z",
         "state": "Period2", "homeTeamInfo": {"code": "LHF"},
         "awayTeamInfo": {"code": "SAIK"}},
    ]})
    current = choose_current_game(games, "SKE", datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc))
    assert current is not None and current.game_uuid == "live"


def test_cancelled_and_postponed_games_are_never_current():
    games = parse_schedule({"games": [
        {"gameUuid": "cancelled", "rawStartDateTime": "2026-10-10T16:00:00Z",
         "state": "cancelled", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "RBK"}},
        {"gameUuid": "postponed", "rawStartDateTime": "2026-10-11T16:00:00Z",
         "state": "postponed", "homeTeamInfo": {"code": "SAIK"},
         "awayTeamInfo": {"code": "RBK"}},
        {"gameUuid": "upcoming", "rawStartDateTime": "2026-10-15T17:00:00Z",
         "state": "pre-game", "homeTeamInfo": {"code": "VLH"},
         "awayTeamInfo": {"code": "SAIK"}},
    ]})
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    assert choose_current_game(games, "SKE", now) is None
    assert choose_next_game(games, "SKE", now).game_uuid == "upcoming"


def test_active_window_covers_finished_games_but_started_recently_does_not():
    game = parse_schedule({"games": [{
        "gameUuid": "finished", "rawStartDateTime": "2026-10-10T16:00:00Z",
        "state": "post-game", "homeTeamInfo": {"code": "SAIK"},
        "awayTeamInfo": {"code": "RBK"}},
    ]})[0]
    within = datetime(2026, 10, 10, 20, 0, tzinfo=timezone.utc)
    assert game.within_active_window(within)
    assert not game.started_recently(within)
    outside = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    assert not game.within_active_window(outside)


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
    assert game is None
    assert len(games) == 1
    next_game = choose_next_game(games, "SKE", datetime.now(timezone.utc))
    assert next_game is not None and next_game.game_uuid == "next-game"
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


def test_period_break_poll_interval_pauses_but_caps_each_pause():
    now = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    live = timedelta(seconds=15)
    # One minute into the break: 16 minutes of pause left, capped at five.
    assert period_break_poll_interval(
        now, now - timedelta(minutes=1), live
    ) == timedelta(minutes=5)
    # Fifteen minutes in: only the remaining pause before the resume lead.
    assert period_break_poll_interval(
        now, now - timedelta(minutes=15), live
    ) == timedelta(minutes=2)


def test_period_break_poll_interval_uses_live_rate_near_puck_drop():
    now = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    live = timedelta(seconds=15)
    # At the resume lead: poll at the live rate for the expected puck drop.
    assert period_break_poll_interval(now, now - timedelta(minutes=17), live) == live
    # Past the expected resume (delayed puck drop): keep the live rate.
    assert period_break_poll_interval(now, now - timedelta(minutes=25), live) == live


def test_period_break_poll_interval_without_anchor_uses_max_pause():
    now = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    assert period_break_poll_interval(
        now, None, timedelta(seconds=15)
    ) == PERIOD_BREAK_MAX_PAUSE


def test_period_break_poll_interval_never_shorter_than_live_rate():
    now = datetime(2026, 10, 15, 18, 0, tzinfo=timezone.utc)
    live = timedelta(seconds=90)
    # 30 seconds of pause left before the resume lead: wait for the lead,
    # but never poll slower than the configured live rate.
    assert period_break_poll_interval(
        now, now - timedelta(minutes=16, seconds=30), live
    ) == live


def test_schedule_local_offset_uses_raw_utc_and_local_start():
    raw = {
        "rawStartDateTime": "2026-09-26T16:00:00.000Z",
        "startDateTime": "2026-09-26 18:00:00",
    }
    assert schedule_local_offset(raw) == timedelta(hours=2)
    assert schedule_local_offset({"rawStartDateTime": raw["rawStartDateTime"]}) is None
    assert schedule_local_offset({}) is None


def test_parse_feed_datetime_treats_stamps_as_local_wall_clock():
    assert parse_feed_datetime("2026-09-26T18:30:49.019Z") == datetime(
        2026, 9, 26, 18, 30, 49, 19000
    )
    assert parse_feed_datetime("2026-09-26T18:30:49.194768") == datetime(
        2026, 9, 26, 18, 30, 49, 194768
    )
    assert parse_feed_datetime(None) is None
    assert parse_feed_datetime("not a time") is None


def test_period_break_start_uses_latest_finished_period_event():
    events = [
        {"type": "period", "period": 1, "finished": True,
         "finishedAt": "2026-09-26T18:30:49.019Z"},
        {"type": "period", "period": 2, "finished": True,
         "finishedAt": "2026-09-26T19:23:54.036Z"},
        {"type": "period", "period": 3, "finished": False,
         "startedAt": "2026-09-26T19:41:56.023Z"},
        {"type": "shot", "realWorldTime": "2026-09-26T19:50:00"},
    ]
    started = period_break_start(events, timedelta(hours=2))
    assert started == datetime(2026, 9, 26, 17, 23, 54, 36000, tzinfo=timezone.utc)


def test_period_break_start_falls_back_to_real_world_time():
    events = [{
        "type": "period", "finished": True,
        "realWorldTime": "2026-09-26T18:30:49.194768",
    }]
    started = period_break_start(events, timedelta(hours=2))
    assert started == datetime(2026, 9, 26, 16, 30, 49, 194768, tzinfo=timezone.utc)


def test_period_break_start_ignores_unfinished_periods_and_missing_offset():
    events = [{
        "type": "period", "period": 1, "finished": False,
        "startedAt": "2026-09-26T18:00:52.047Z",
        "realWorldTime": "2026-09-26T18:00:52.047",
    }]
    assert period_break_start(events, timedelta(hours=2)) is None
    assert period_break_start([], timedelta(hours=2)) is None
    assert period_break_start(
        [{"type": "period", "finished": True,
          "finishedAt": "2026-09-26T18:30:49.019Z"}],
        None,
    ) is None


def test_real_fixtures_give_break_start_and_intermission_length():
    schedule = _fixture("game_schedule_2026-2027_saik.json")
    rows = schedule.get("gameInfo") if isinstance(schedule, dict) else schedule
    row = next(item for item in rows if item.get("uuid") == "u0ribje54r")
    offset = schedule_local_offset(row)
    assert offset == timedelta(hours=2)

    events = _fixture("play_by_play_20260926_OHK_SAIK.json")
    started = period_break_start(events, offset)
    assert started == datetime(2026, 9, 26, 18, 11, 27, 38000, tzinfo=timezone.utc)

    # The observed intermissions bracket the 18-minute break length.
    periods = sorted(
        (event for event in events if event.get("type") == "period"),
        key=lambda event: event["period"],
    )
    breaks = [
        parse_feed_datetime(later["startedAt"]) - parse_feed_datetime(earlier["finishedAt"])
        for earlier, later in zip(periods, periods[1:])
    ]
    assert len(breaks) == 2
    assert all(timedelta(minutes=17) <= length <= timedelta(minutes=19) for length in breaks)
