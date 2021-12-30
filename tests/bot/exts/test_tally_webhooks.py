import json
from pathlib import Path

import pytest

from bot.exts.tally_webhooks import make_submission


@pytest.mark.parametrize(
    "example_filename", ("example_tally_webhook.json", "example_tally_webhook2.json")
)
def test_make_submission(snapshot, example_filename):
    example_webhook_path = Path(__file__).parent / example_filename
    with example_webhook_path.open("r") as fp:
        webhook_data = json.load(fp)
    submission = make_submission(webhook_data)
    assert submission == snapshot
