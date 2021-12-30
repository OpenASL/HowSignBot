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
TEST_GUILDS = env.list("TEST_GUILDS", default=[], subcast=int)

GOOGLE_PROJECT_ID = env.str("GOOGLE_PROJECT_ID", required=True)
GOOGLE_PRIVATE_KEY = env.str("GOOGLE_PRIVATE_KEY", required=True)
GOOGLE_PRIVATE_KEY_ID = env.str("GOOGLE_PRIVATE_KEY_ID", required=True)
GOOGLE_CLIENT_EMAIL = env.str("GOOGLE_CLIENT_EMAIL", required=True)
GOOGLE_TOKEN_URI = env.str("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
TOPICS_SHEET_KEY = env.str("TOPICS_SHEET_KEY", required=True)
FEEDBACK_SHEET_KEY = env.str("FEEDBACK_SHEET_KEY", required=True)

ASLPP_SHEET_KEY = env.str("ASLPP_SHEET_KEY", required=True)
ASLPP_SYNC_TAGS = env.bool("ASLPP_SYNC_TAGS", default=True)
ASLPP_GUILD_ID = env.int("ASLPP_GUILD_ID", default=729838318963130449)
ASLPP_MOD_ROLE_ID = env.int("ASLPP_MOD_ROLE_ID", default=729845246384668723)
ASLPP_INTRODUCTIONS_CHANNEL_ID = env.int("ASLPP_INTRODUCTIONS_CHANNEL_ID", required=False)
ASLPP_ACKNOWLEDGED_RULES_ROLE_ID = env.int(
    "ASLPP_ACKNOWLEDGED_RULES_ROLE_ID", required=False
)
ASLPP_BOT_CHANNEL_ID = env.int("ASLPP_BOT_CHANNEL_ID", required=False)
ASLPP_SKILL_ROLE_IDS = env.list("ASLPP_SKILL_ROLE_IDS", subcast=int)
ASLPP_HEARING_SPECTRUM_ROLE_IDS = env.list("ASLPP_HEARING_SPECTRUM_ROLE_IDS", subcast=int)
ASLPP_AGE_ROLE_IDS = env.list("ASLPP_AGE_ROLE_IDS", subcast=int)
ASLPP_ENABLE_UNMUTE_WARNING = env.bool("ASLPP_ENABLE_UNMUTE_WARNING", True)
ASLPP_INACTIVE_DAYS = env.int("ASLPP_INACTIVE_DAYS", 30)
ASLPP_ZOOM_WATCH_LIST = env.list("ASLPP_ZOOM_WATCH_LIST", default=[], subcast=str)
ASLPP_SURVEY_ID = env.str("ASLPP_SURVEY_ID", default=None)
ASLPP_SURVEY_VANITY_ROLE_ID = env.int(
    "ASLPP_SURVEY_VANITY_ROLE_ID", default=None, required=False
)

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

SEND_DEPRECATION_MESSAGES = env.bool("SEND_DEPRECATION_MESSAGES", default=False)

env.seal()
