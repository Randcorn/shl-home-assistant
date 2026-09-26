from __future__ import annotations
from datetime import timedelta
from typing import Any
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import ShlApi, ShlApiError
from .const import DOMAIN, OFF_GAME_INTERVAL, LIVE_GAME_INTERVAL

class ShlCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass, api: ShlApi, team_code: str):
        self.api = api
        self.team_code = team_code
        self.current_game_uuid: str | None = None
        self.seen_revisions: dict[str, int] = {}
        super().__init__(hass, __name__, name=DOMAIN,
                         update_interval=timedelta(seconds=OFF_GAME_INTERVAL))

    async def _async_update_data(self) -> dict[str, Any]:
        if not self.current_game_uuid:
            return {"game": None, "events": [], "new_events": [], "goals": []}
        try:
            info = await self.api.game_info(self.current_game_uuid)
            events = await self.api.play_by_play(self.current_game_uuid)
        except ShlApiError as err:
            raise UpdateFailed(str(err)) from err

        new_events = []
        for event in sorted(events, key=lambda e: (
            int(e.get("eventId", 0)), int(e.get("revision", 0)))):
            uid = event.get("eventUuid")
            if not uid:
                continue
            revision = int(event.get("revision", 0))
            previous = self.seen_revisions.get(uid)
            if previous is None or revision > previous:
                self.seen_revisions[uid] = revision
                new_events.append(event)

        state = info.get("gameInfo", {})
        live = str(state.get("state", "")).lower() in {
            "live", "in_progress", "in-progress", "game_started"
        }
        self.update_interval = timedelta(
            seconds=LIVE_GAME_INTERVAL if live else OFF_GAME_INTERVAL
        )
        return {
            "game": {**state, "home_team": info.get("homeTeam", {}),
                     "away_team": info.get("awayTeam", {})},
            "events": events, "new_events": new_events,
            "goals": [e for e in new_events if e.get("type") == "goal"],
        }
