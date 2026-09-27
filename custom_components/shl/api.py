"""Small, typed boundary around the SHL website API."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    API_BASE,
    GAME_INFO_PATH,
    GAME_OVERVIEW_PATH,
    GAME_SCHEDULE_PATH,
    LATEST_SSGT_PATH,
    PLAY_BY_PLAY_PATH,
    SEASON_SERIES_FILTER_PATH,
    TEAM_STATS_PATH,
)


class ShlApiError(Exception):
    """An HTTP, transport, or response-shape error from the SHL API."""


class ShlApi:
    """Client for the first-party SHL website endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            async with self.session.get(
                f"{API_BASE}{path}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "Origin": API_BASE,
                    "Referer": f"{API_BASE}/",
                    "User-Agent": "Home Assistant SHL integration",
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status != 200:
                    raise ShlApiError(f"HTTP {response.status}: {path}")
                body = await response.read()
                if not body:
                    return None
                try:
                    return json.loads(body)
                except (ValueError, UnicodeDecodeError) as err:
                    raise ShlApiError(f"Invalid JSON response: {path}") from err
        except ShlApiError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ShlApiError(f"Request failed for {path}: {err}") from err

    async def season_series_game_types_filter(
        self, series: str, season: str
    ) -> Any:
        """Return filter options used by the schedule endpoint."""
        return await self._get(
            SEASON_SERIES_FILTER_PATH,
            {"series": series, "season": season},
        )

    async def latest_ssgt(self, series_uuid: str) -> dict[str, Any]:
        """Return the latest active season/series/game-type selection."""
        path = LATEST_SSGT_PATH.format(series_uuid=quote(series_uuid, safe=""))
        data = await self._get(path)
        if not isinstance(data, dict):
            raise ShlApiError("Unexpected latest-SSGT response shape")
        return data

    async def game_schedule(
        self,
        season_uuid: str | None = None,
        series_uuid: str | None = None,
        game_type_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Fetch schedule rows, optionally scoped by discovered identifiers."""
        params = {"gamePlace": "all", "played": "all"}
        if season_uuid:
            params["seasonUuid"] = season_uuid
        if series_uuid:
            params["seriesUuid"] = series_uuid
        if game_type_uuid:
            params["gameTypeUuid"] = game_type_uuid
        data = await self._get(GAME_SCHEDULE_PATH, params)
        if not isinstance(data, dict) or not isinstance(data.get("gameInfo"), list):
            raise ShlApiError("Unexpected game-schedule response shape")
        return data

    async def game_info(self, game_uuid: str) -> dict[str, Any]:
        path = GAME_INFO_PATH.format(game_uuid=quote(game_uuid, safe=""))
        data = await self._get(path)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ShlApiError("Unexpected game-info response shape")
        return data

    async def game_overview(self, game_uuid: str) -> dict[str, Any]:
        """Return the scoreboard, game state, period, and clock."""
        path = GAME_OVERVIEW_PATH.format(game_uuid=quote(game_uuid, safe=""))
        data = await self._get(path)
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ShlApiError("Unexpected game-overview response shape")
        return data

    async def play_by_play(self, game_uuid: str) -> list[dict[str, Any]]:
        path = PLAY_BY_PLAY_PATH.format(game_uuid=quote(game_uuid, safe=""))
        data = await self._get(path)
        if data is None:
            return []
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            events = next(
                (data[key] for key in ("events", "playByPlay", "data")
                 if isinstance(data.get(key), list)),
                None,
            )
        else:
            events = None
        if events is None or not all(isinstance(event, dict) for event in events):
            raise ShlApiError("Unexpected play-by-play response shape")
        return events

    async def team_stats(self, game_uuid: str) -> Any:
        path = TEAM_STATS_PATH.format(game_uuid=quote(game_uuid, safe=""))
        return await self._get(path)
