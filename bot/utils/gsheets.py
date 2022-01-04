import gspread

from bot.settings import (
    GOOGLE_CLIENT_EMAIL,
    GOOGLE_PRIVATE_KEY,
    GOOGLE_PRIVATE_KEY_ID,
    GOOGLE_PROJECT_ID,
    GOOGLE_TOKEN_URI,
)

credentials = {
    "type": "service_account",
    "project_id": GOOGLE_PROJECT_ID,
    "private_key_id": GOOGLE_PRIVATE_KEY_ID,
    "private_key": GOOGLE_PRIVATE_KEY,
    "client_email": GOOGLE_CLIENT_EMAIL,
    "token_uri": GOOGLE_TOKEN_URI,
}


def get_gsheet_client():
    return gspread.service_account_from_dict(credentials)
