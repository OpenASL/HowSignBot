import datetime as dt
import subprocess

import jwt
from environs import Env

env = Env()
env.read_env()

ZOOM_API_KEY = env.str("ZOOM_API_KEY")
ZOOM_SECRET_KEY = env.str("ZOOM_SECRET_KEY")
HEROKU_APP = env.str("HEROKU_APP", "howsign")


def generate_token():
    now = dt.datetime.now(tz=dt.timezone.utc)
    payload = {
        "aud": None,
        "iss": ZOOM_API_KEY,
        "exp": now + dt.timedelta(days=8),
        "iat": now,
    }
    return jwt.encode(payload, ZOOM_SECRET_KEY, algorithm="HS256")


def main():
    token = generate_token()
    print("==> Setting ZOOM_JWT in Heroku")
    subprocess.check_call(("heroku", "config:set", f"ZOOM_JWT={token}", "-a", HEROKU_APP))
    print("==> Finished.")


if __name__ == "__main__":
    main()
