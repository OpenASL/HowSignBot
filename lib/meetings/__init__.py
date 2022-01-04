from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import IntEnum
from typing import Callable, NamedTuple

import aiohttp
import cuteid
from slugify import slugify


class ZoomClientError(Exception):
    pass


class MaxZoomLicensesError(ZoomClientError):
    pass


class BasicUserLimitReachedError(ZoomClientError):
    pass


@asynccontextmanager
async def zoom_request(
    method: str,
    path: str,
    *,
    token: str,
    raise_for_status: bool = True,
    timeout: int = 10,
    **kwargs,
) -> AsyncIterator[aiohttp.ClientResponse]:
    timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.request(
        method,
        f"https://api.zoom.us/v2/{path.lstrip('/')}",
        timeout=timeout,
        headers={"Authorization": f"Bearer {token}"},
        **kwargs,
    ) as resp:
        if raise_for_status:
            resp.raise_for_status()
        yield resp


class ZoomMeeting(NamedTuple):
    id: int
    join_url: str
    passcode: str
    topic: str


async def create_zoom(
    *, token: str, user_id: str, topic: str, settings: dict
) -> ZoomMeeting:
    """Create and return a Zoom meeting via the Zoom API."""
    async with zoom_request(
        "POST",
        f"/users/{user_id}/meetings",
        token=token,
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


class ZoomPlanType(IntEnum):
    BASIC = 1
    LICENSED = 2


class ZoomUser(NamedTuple):
    id: str
    email: str
    type: ZoomPlanType


async def list_zoom_users(*, token: str) -> list[ZoomUser]:
    async with zoom_request("GET", "/users", token=token) as resp:
        data = await resp.json()
    return [ZoomUser(id=u["id"], email=u["email"], type=u["type"]) for u in data["users"]]


async def update_zoom_user(*, token: str, user_id: str, data: dict):
    async with zoom_request(
        "PATCH",
        f"/users/{user_id}",
        token=token,
        json=data,
        raise_for_status=False,
    ) as resp:
        if resp.status >= 400:
            resp_data = await resp.json()
            error_code = int(resp_data["code"])
            message = resp_data["message"]
            # NOTE: Contrary to Zoom's docs, 3412 is used for max licenses exceeded
            if error_code in {2034, 3412}:
                raise MaxZoomLicensesError(message)
            elif error_code == 2033:
                raise BasicUserLimitReachedError(message)
            else:
                resp.raise_for_status()
        else:
            resp.raise_for_status()
    return None


async def get_zoom(
    *,
    token: str,
    meeting_id: int,
) -> ZoomMeeting:
    """Get an existing Zoom meeting via the Zoom API."""
    async with aiohttp.ClientSession() as client:
        resp = await client.get(
            f"https://api.zoom.us/v2/meetings/{meeting_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    resp.raise_for_status()
    data = await resp.json()
    return ZoomMeeting(
        id=data["id"],
        join_url=data["join_url"],
        passcode=data["password"],
        topic=data["topic"],
    )


async def create_watch2gether(api_key: str, video_url: str | None = None) -> str:
    """Create and return a watch2gether URL via the watch2gether API."""
    async with aiohttp.ClientSession() as client:
        payload = {"w2g_api_key": api_key, "share": video_url}
        resp = await client.post("https://w2g.tv/rooms/create.json", json=payload)
    resp.raise_for_status()
    data = await resp.json()
    stream_key = data["streamkey"]
    url = f"https://w2g.tv/rooms/{stream_key}"
    return url


def _signature(s: str, *, secret: str) -> str:
    dig = hmac.new(
        secret.encode("utf-8"), msg=s.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(dig).decode()


def _slug_with_signature(s: str, *, secret: str, signature_length=16):
    return "-".join((slugify(s), _signature(s, secret=secret)[:signature_length]))


def _get_secret_slug(
    name: str | None, secret: str, fallback: Callable = cuteid.cuteid
) -> str:
    """Return a hard-to-guess slug to use for meeting URLs.

    If name is passed, return the slugified name with a signature
    appended so that the same meeting can be shared in multiple servers.
    """
    return _slug_with_signature(name, secret=secret) if name else fallback()


class JitsiMeet(NamedTuple):
    join_url: str
    deeplink: str
    name: str | None


def create_jitsi_meet(name: str | None, *, secret: str) -> JitsiMeet:
    """Return a Jitsi Meet URL."""
    slug = _get_secret_slug(name, secret)
    return JitsiMeet(
        join_url=f"https://meet.jit.si/{slug}", deeplink=f"jitsi-meet://{slug}", name=name
    )


def create_speakeasy(name: str | None, *, secret: str) -> str:
    """Return a Speakeasy URL."""
    slug = _get_secret_slug(name, secret, fallback=cuteid.emojid)
    return f"https://speakeasy.co/{slug}"
