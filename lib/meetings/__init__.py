import base64
import uuid
from typing import NamedTuple

import aiohttp


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


def _pretty_uuid() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().replace("=", "")


def create_jitsi_meet() -> str:
    """Return a Jitsi Meet URL with a unique ID."""
    return f"https://meet.jit.si/{_pretty_uuid()}"


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
