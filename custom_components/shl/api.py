from __future__ import annotations
from typing import Any
import aiohttp
from .const import API_BASE

class ShlApiError(Exception):
    pass

class ShlApi:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _get(self, path: str) -> Any:
        try:
            async with self.session.get(
                f"{API_BASE}{path}",
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status != 200:
                    raise ShlApiError(f"HTTP {response.status}: {path}")
                return await response.json()
        except aiohttp.ClientError as err:
            raise ShlApiError(str(err)) from err

    async def game_info(self, game_uuid: str) -> dict[str, Any]:
        return await self._get(f"/api/gameday/game-info/{game_uuid}")

    async def play_by_play(self, game_uuid: str) -> list[dict[str, Any]]:
        data = await self._get(f"/api/gameday/play-by-play/{game_uuid}")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("events", "playByPlay", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        raise ShlApiError("Unexpected play-by-play response shape")

    async def team_stats(self, game_uuid: str) -> dict[str, Any]:
        return await self._get(f"/api/gameday/team-stats/{game_uuid}")

    async def game_schedule(self, season_uuid: str, series_uuid: str,
                            game_type_uuid: str) -> dict[str, Any]:
        return await self._get(
            "/api/sports-v2/game-schedule"
            f"?seasonUuid={season_uuid}&seriesUuid={series_uuid}"
            f"&gameTypeUuid={game_type_uuid}&gamePlace=all&played=all"
        )
