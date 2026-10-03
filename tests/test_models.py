import json
from pathlib import Path
from custom_components.shl.models import parse_goal, parse_shots_on_goal

FIXTURE = json.loads((Path(__file__).parent / "fixture_goal.json").read_text())

def test_parse_goal_fixture():
    goal = parse_goal(FIXTURE)
    assert goal is not None
    assert goal.event_id == 48
    assert goal.team_code == "SKE"
    assert goal.player_name == "Oliver Okuliar"
    assert goal.jersey == "8"
    assert goal.period == 2
    assert goal.time == "01:58"
    assert goal.home_score == 2
    assert goal.away_score == 0
    assert goal.goal_status == "PP1"
    assert [a["familyName"] for a in goal.assists] == ["Lundberg", "Johansson"]

def test_non_goal_is_ignored():
    assert parse_goal({"type": "shot"}) is None

def test_goal_false_string_flags_stay_false():
    goal = parse_goal({
        "type": "goal", "isPenaltyShot": "false", "isEmptyNetGoal": "false"
    })
    assert goal is not None
    assert goal.is_penalty_shot is False
    assert goal.is_empty_net is False

def test_parse_shots_on_goal_uses_period_zero_totals():
    stats = {
        "home": {"statistics": [
            {"period": 1, "parsedTotalStatistics": [{"key": "SOG", "value": 2}]},
            {"period": 0, "parsedTotalStatistics": [{"key": "SOG", "value": 7}]},
        ]},
        "away": {"statistics": [
            {"period": 0, "parsedTotalStatistics": [{"key": "SOG", "value": "4"}]},
        ]},
    }
    assert parse_shots_on_goal(stats) == {"home": 7, "away": 4}
