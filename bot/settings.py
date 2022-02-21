import logging

from databases import DatabaseURL
from disnake import ActivityType
from environs import Env
from marshmallow.validate import OneOf

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
TEST_GUILDS = env.list("TEST_GUILDS", default=[], subcast=int)
PRESENCE_ACTIVITY = env.str(
    "PRESENCE_ACTIVITY",
    validate=OneOf(ActivityType._enum_member_names_),  # type: ignore
    default=None,
)
PRESENCE_CONTENT = env.str("PRESENCE_CONTENT", default=None)

GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)

SIGN_CAFE_SHEET_KEY = env.str("SIGN_CAFE_SHEET_KEY", required=True)
SIGN_CAFE_SYNC_TAGS = env.bool("SIGN_CAFE_SYNC_TAGS", default=True)
SIGN_CAFE_GUILD_ID = env.int("SIGN_CAFE_GUILD_ID", default=729838318963130449)
SIGN_CAFE_MOD_ROLE_ID = env.int("SIGN_CAFE_MOD_ROLE_ID", default=729845246384668723)
SIGN_CAFE_INTRODUCTIONS_CHANNEL_ID = env.int(
    "SIGN_CAFE_INTRODUCTIONS_CHANNEL_ID", required=False
)
SIGN_CAFE_ACKNOWLEDGED_RULES_ROLE_ID = env.int(
    "SIGN_CAFE_ACKNOWLEDGED_RULES_ROLE_ID", required=False
)
SIGN_CAFE_BOT_CHANNEL_ID = env.int("SIGN_CAFE_BOT_CHANNEL_ID", required=False)
SIGN_CAFE_AUTOTHREAD_CHANNEL_IDS = env.list(
    "SIGN_CAFE_AUTOTHREAD_CHANNEL_IDS", default=[], subcast=int
)
SIGN_CAFE_SKILL_ROLE_IDS = env.list("SIGN_CAFE_SKILL_ROLE_IDS", subcast=int)
SIGN_CAFE_HEARING_SPECTRUM_ROLE_IDS = env.list(
    "SIGN_CAFE_HEARING_SPECTRUM_ROLE_IDS", subcast=int
)
SIGN_CAFE_AGE_ROLE_IDS = env.list("SIGN_CAFE_AGE_ROLE_IDS", subcast=int)
SIGN_CAFE_ENABLE_UNMUTE_WARNING = env.bool("SIGN_CAFE_ENABLE_UNMUTE_WARNING", True)
SIGN_CAFE_ENABLE_STARS = env.bool("SIGN_CAFE_ENABLE_STARS", True)
SIGN_CAFE_INACTIVE_DAYS = env.int("SIGN_CAFE_INACTIVE_DAYS", 30)
SIGN_CAFE_PRUNE_DAYS = env.int("SIGN_CAFE_PRUNE_DAYS", 30)
SIGN_CAFE_ZOOM_WATCH_LIST = env.list("SIGN_CAFE_ZOOM_WATCH_LIST", default=[], subcast=str)
SIGN_CAFE_SURVEY_ID = env.str("SIGN_CAFE_SURVEY_ID", default=None)
SIGN_CAFE_SURVEY_VANITY_ROLE_ID = env.int(
    "SIGN_CAFE_SURVEY_VANITY_ROLE_ID", default=None, required=False
)

# Mapping of Discord user IDs => emails
ZOOM_USERS = env.dict("ZOOM_USERS", subcast_keys=int, required=True)
# Emails for Zoom users that should never be downgraded to Basic
ZOOM_NO_DOWNGRADE = env.list("ZOOM_NO_DOWNGRADE", default=[], subcast=str)
ZOOM_EMAILS = {email: zoom_id for zoom_id, email in ZOOM_USERS.items()}
ZOOM_JWT = env.str("ZOOM_JWT", required=True)
ZOOM_HOOK_TOKEN = env.str("ZOOM_HOOK_TOKEN", required=True)
ZOOM_REPOST_COOLDOWN = env.int("ZOOM_REPOST_COOLDOWN", 30)
ZZZZOOM_URL = env.str("ZZZZOOM_URL", "https://zzzzoom.us")

WATCH2GETHER_API_KEY = env.str("WATCH2GETHER_API_KEY", required=True)
# When to send practice schedules (in Eastern time)
DAILY_PRACTICE_SEND_TIME = env.time("DAILY_PRACTICE_SEND_TIME", "10:00")

SEND_DEPRECATION_MESSAGES = env.bool("SEND_DEPRECATION_MESSAGES", default=False)

env.seal()
