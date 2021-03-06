import os

import pytest

# Must be before bot import
os.environ["TESTING"] = "true"

from bot.bot import bot  # noqa:E402
from bot.exts.meetings.zoom_webhooks import handle_zoom_event  # noqa:E402

# Copied examples from https://marketplace.zoom.us/docs/api-reference/webhook-reference/meeting-events/
PARTICIPANT_JOINED = {
    "event": "meeting.participant_joined",
    "event_ts": 1234566789900,
    "payload": {
        "account_id": "o8KK_AAACq6BBEyA70CA",
        "object": {
            "uuid": "czLF6FFFoQOKgAB99DlDb9g==",
            "id": "111111111",
            "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
            "topic": "My Meeting",
            "type": 2,
            "start_time": "2019-07-09T17:00:00Z",
            "duration": 60,
            "timezone": "America/Los_Angeles",
            "participant": {
                "user_id": "167782040",
                "user_name": "shree",
                "email": "hdgfmjdfgh@vbhhf.cindfs",
                "id": "iFxeBPYun6SAiWUzBcEkX",
                "join_time": "2019-07-16T17:13:13Z",
            },
        },
    },
}

PARTICIPANT_LEFT = {
    "event": "meeting.participant_left",
    "event_ts": 1234566789900,
    "payload": {
        "account_id": "o8KK_AAACq6BBEyA70CA",
        "object": {
            "uuid": "czLF6FFFoQOKgAB99DlDb9g==",
            "id": "111111111",
            "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
            "topic": "My Meeting",
            "type": 2,
            "start_time": "2019-07-09T17:00:00Z",
            "duration": 60,
            "timezone": "America/Los_Angeles",
            "participant": {
                "user_id": "167782040",
                "user_name": "shree",
                "id": "iFxeBPYun6SAiWUzBcEkX",
                "email": "shffdhj@xdvjfhcb.com",
                "leave_time": "2019-07-16T17:13:13Z",
            },
        },
    },
}

MEETING_ENDED = {
    "event": "meeting.ended",
    "event_ts": 1234566789900,
    "payload": {
        "account_id": "o8KK_AAACq6BBEyA70CA",
        "object": {
            "uuid": "czLF6FFFoQOKgAB99DlDb9g==",
            "id": "111111111",
            "host_id": "uLoRgfbbTayCX6r2Q_qQsQ",
            "topic": "My Meeting",
            "type": 2,
            "start_time": "2019-07-09T17:00:00Z",
            "duration": 10,
            "timezone": "America/Los_Angeles",
            "end_time": "2019-07-09T17:00:50Z",
        },
    },
}


@pytest.mark.parametrize(
    "data",
    (
        pytest.param(PARTICIPANT_JOINED, id="participant_joined"),
        pytest.param(PARTICIPANT_LEFT, id="participant_left"),
        pytest.param(MEETING_ENDED, id="meeting_ended"),
    ),
)
@pytest.mark.asyncio
async def test_handle_zoom_event(data, db):
    # Just test that the handler doesn't raise any uncaught exceptions
    await handle_zoom_event(bot, data)
