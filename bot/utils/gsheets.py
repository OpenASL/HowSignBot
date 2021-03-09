import gspread
from google.auth.crypt._python_rsa import RSASigner
from google.oauth2.service_account import Credentials

from bot.settings import GOOGLE_CLIENT_EMAIL
from bot.settings import GOOGLE_PRIVATE_KEY
from bot.settings import GOOGLE_PRIVATE_KEY_ID
from bot.settings import GOOGLE_PROJECT_ID
from bot.settings import GOOGLE_TOKEN_URI


def get_gsheet_client():
    signer = RSASigner.from_string(key=GOOGLE_PRIVATE_KEY, key_id=GOOGLE_PRIVATE_KEY_ID)
    credentials = Credentials(
        signer=signer,
        service_account_email=GOOGLE_CLIENT_EMAIL,
        token_uri=GOOGLE_TOKEN_URI,
        scopes=gspread.auth.DEFAULT_SCOPES,
        project_id=GOOGLE_PROJECT_ID,
    )
    return gspread.authorize(credentials)
