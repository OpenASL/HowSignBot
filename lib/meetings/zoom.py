import base64
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import NamedTuple

import aiohttp


class ZoomTokenManager:
    """Utility class for getting and storing server-to-server access tokens via
    via the OAuth token API.

    https://developers.zoom.us/docs/internal-apps/s2s-oauth/#use-account-credentials-to-get-an-access-token
    """

    URL = "https://zoom.us/oauth/token"

    def __init__(
        self,
        *,
        account_id: str,
        client_id: str,
        client_secret: str,
        renew_pad_secs: int = 60,
    ):
        self.account_id = account_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.renew_pad_secs = renew_pad_secs
        self._token = None
        self._exp = None

    async def login(self):
        """Use account credentials to get and store an access token."""
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode("utf-8")
        async with aiohttp.ClientSession() as client:
            resp = await client.post(
                self.URL,
                params={
                    "grant_type": "account_credentials",
                    "account_id": self.account_id,
                },
                headers={
                    "Host": "zoom.us",
                    "Authorization": f"Basic {credentials}",
                },
            )
        resp.raise_for_status()
        data = await resp.json()

        self._token = data["access_token"]
        self._exp = time.time() + data["expires_in"] - self.renew_pad_secs

    async def token(self):
        if not self._token or not self._exp or time.time() > self._exp:
            await self.login()

        return self._token


# -----------------------------------------------------------------------------


class ZoomMeeting(NamedTuple):
    id: int
    join_url: str
    passcode: str
    topic: str


class ZoomPlanType(IntEnum):
    BASIC = 1
    LICENSED = 2


class ZoomUser(NamedTuple):
    id: str
    email: str
    type: ZoomPlanType


# -----------------------------------------------------------------------------


class ZoomClient:
    def __init__(
        self,
        *,
        account_id: str,
        client_id: str,
        client_secret: str,
    ):
        self.token_manager = ZoomTokenManager(
            account_id=account_id, client_id=client_id, client_secret=client_secret
        )

    @asynccontextmanager
    async def _zoom_request(
        self,
        method: str,
        path: str,
        *,
        raise_for_status: bool = True,
        timeout: int = 10,
        **kwargs,
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        token = await self.token_manager.token()
        async with aiohttp.request(
            method,
            f"https://api.zoom.us/v2/{path.lstrip('/')}",
            timeout=client_timeout,
            headers={"Host": "api.zoom.us", "Authorization": f"Bearer {token}"},
            **kwargs,
        ) as resp:
            if raise_for_status:
                resp.raise_for_status()
            yield resp

    async def create_zoom(
        self, *, user_id: str, topic: str, settings: dict
    ) -> ZoomMeeting:
        """Create and return a Zoom meeting via the Zoom API."""
        async with self._zoom_request(
            "POST",
            f"/users/{user_id}/meetings",
            json={
                "type": 1,
                "topic": topic,
                "settings": settings,
            },
        ) as resp:
            data = await resp.json()
        return ZoomMeeting(
            id=data["id"],
            join_url=data["join_url"],
            passcode=data["password"],
            # Pass topic directly so we don't get the default 'Zoom Meeting' topic
            topic=topic,
        )

    async def get_zoom(
        self,
        *,
        meeting_id: int,
    ) -> ZoomMeeting:
        """Get an existing Zoom meeting via the Zoom API."""
        async with self._zoom_request(
            "GET",
            f"/meetings/{meeting_id}",
        ) as resp:
            data = await resp.json()
        return ZoomMeeting(
            id=data["id"],
            join_url=data["join_url"],
            passcode=data["password"],
            topic=data["topic"],
        )

    async def list_zoom_users(self) -> list[ZoomUser]:
        async with self._zoom_request("GET", "/users") as resp:
            data = await resp.json()
        return [
            ZoomUser(id=u["id"], email=u["email"], type=u["type"]) for u in data["users"]
        ]
