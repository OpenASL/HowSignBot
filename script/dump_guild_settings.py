import json
from base64 import b64encode

dev_guild_settings = [
    # CHANGEME
    {
        "guild_id": 123,
        "schedule_sheet_key": "changeme",
        "daily_message_channel_id": 321,
        "include_handshape_of_the_day": True,
        "include_topics_of_the_day": True,
    }
]

prod_guild_settings = [
    # CHANGEME
    {
        "guild_id": 123,
        "schedule_sheet_key": "changeme",
        "daily_message_channel_id": 321,
        "include_handshape_of_the_day": True,
        "include_topics_of_the_day": True,
    }
]


def encode_settings(settings):
    return b64encode(bytes(json.dumps(settings), "utf-8")).decode("utf-8")


def main():
    print("Dev settings:\n")
    dev_encoded = encode_settings(dev_guild_settings)
    print(f"GUILD_SETTINGS={dev_encoded}")

    print()

    print("Prod settings:\n")
    prod_encoded = encode_settings(prod_guild_settings)
    print(f"GUILD_SETTINGS={prod_encoded}")


if __name__ == "__main__":
    main()
