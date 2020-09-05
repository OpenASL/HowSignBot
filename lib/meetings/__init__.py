import base64
import hmac
import hashlib
import uuid
from typing import NamedTuple

import aiohttp
from slugify import slugify


class ZoomMeeting(NamedTuple):
    join_url: str
    passcode: str


async def create_zoom(
    *, token: str, user_id: str, topic: str, settings: dict
) -> ZoomMeeting:
    """Create and return a Zoom meeting via the Zoom API."""
    async with aiohttp.ClientSession() as client:
        resp = await client.post(
            f"https://api.zoom.us/v2/users/{user_id}/meetings",
            json={
                "type": 1,
                "topic": topic,
                "settings": settings,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    resp.raise_for_status()
    data = await resp.json()
    return ZoomMeeting(join_url=data["join_url"], passcode=data["password"])


def _signature(s: str, *, secret: str) -> str:
    dig = hmac.new(
        secret.encode("utf-8"), msg=s.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(dig).decode()


def _slug_with_signature(s: str, *, secret: str):
    slug = slugify(s)
    return "-".join((slug, _signature(slug, secret=secret)[:16]))


def _pretty_uuid() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().replace("=", "")


def create_jitsi_meet(name: str = None, *, secret: str = None) -> str:
    """Return a Jitsi Meet URL with a unique ID."""
    # Return deterministic URLs when name is passed in
    #  so that the same meeting can be shared in multiple servers.
    #  The URL will be the slugified name with a 16-character signature appended
    if name:
        slug = _slug_with_signature(name, secret=secret)
    else:
        slug = _pretty_uuid()
    return f"https://meet.jit.si/{slug}"


async def create_watch2gether(api_key: str, video_url: str = None) -> str:
    """Create and return a watch2gether URL via the watch2gether API."""
    async with aiohttp.ClientSession() as client:
        payload = {"api_key": api_key, "video_url": video_url}
        resp = await client.post("https://w2g.tv/rooms/create.json", json=payload)
    resp.raise_for_status()
    data = await resp.json()
    stream_key = data["streamkey"]
    url = f"https://w2g.tv/rooms/{stream_key}"
    return url
