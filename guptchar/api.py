"""Thin async client for the relay API (PROTOCOL.md section 2)."""

from __future__ import annotations

import httpx

from . import __version__


class ApiError(Exception):
    def __init__(self, code: str, status: int = 0):
        super().__init__(code)
        self.code = code
        self.status = status


class Api:
    def __init__(self, base_url: str):
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/api/v1/",
            timeout=30.0,
            headers={"Accept": "application/json", "User-Agent": "guptchar-cli"},
            follow_redirects=False,
        )

    async def call(self, endpoint: str, body: dict) -> dict | None:
        try:
            res = await self._client.post(endpoint, json=body)
        except httpx.HTTPError as exc:
            raise ApiError("network") from exc
        finally:
            self._client.cookies.clear()  # the server never sets any; never keep one

        if res.status_code == 204:
            return None
        try:
            data = res.json()
        except ValueError:
            data = None
        if res.is_error:
            code = data.get("error") if isinstance(data, dict) else None
            raise ApiError(code or ("network" if res.status_code >= 500 else "server_error"), res.status_code)
        return data

    async def close(self) -> None:
        await self._client.aclose()
