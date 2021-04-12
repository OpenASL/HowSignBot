import logging

from databases import DatabaseURL
from environs import Env

env = Env(eager=False)
env.read_env()

DEBUG = env.bool("DEBUG", False)
DATABASE_URL = DatabaseURL(env.str("DATABASE_URL", required=True))
TEST_DATABASE_URL = DATABASE_URL.replace(database="test_" + DATABASE_URL.database)
TESTING = env.bool("TESTING", cast=bool, default=False)
LOG_LEVEL = env.log_level("LOG_LEVEL", logging.INFO)
DISCORD_TOKEN = env.str("DISCORD_TOKEN", required=True)
OWNER_ID = env.int("OWNER_ID", required=True)
SECRET_KEY = env.str("SECRET_KEY", required=True)
COMMAND_PREFIX = env.str("COMMAND_PREFIX", "?")
PARTICIPANT_EMOJI = env.str("PARTICIPANT_EMOJI", default=None)
DAILY_MESSAGE_RANDOM_SEED = env.str("DAILY_MESSAGE_RANDOM_SEED", default=None)
PORT = env.int("PORT", 5000)

GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)
ASLPP_SHEET_KEY = env.str("ASLPP_SHEET_KEY", required=True)

# Mapping of Discord user IDs => emails
ZOOM_USERS = env.dict("ZOOM_USERS", subcast_keys=int, required=True)
ZOOM_EMAILS = {email: zoom_id for zoom_id, email in ZOOM_USERS.items()}
ZOOM_JWT = env.str("ZOOM_JWT", required=True)
ZOOM_HOOK_TOKEN = env.str("ZOOM_HOOK_TOKEN", required=True)
ZOOM_REPOST_COOLDOWN = env.int("ZOOM_REPOST_COOLDOWN", 30)
ZZZZOOM_URL = env.str("ZZZZOOM_URL", "https://zzzzoom.us")

WATCH2GETHER_API_KEY = env.str("WATCH2GETHER_API_KEY", required=True)
# When to send practice schedules (in Eastern time)
DAILY_PRACTICE_SEND_TIME = env.time("DAILY_PRACTICE_SEND_TIME", "10:00")

env.seal()
