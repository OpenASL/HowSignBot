import json
from pathlib import Path

from environs import Env

from bot import get_gsheet_client

env = Env()
env.read_env()

CLTHAT_SHEET_KEY = env.str("CLTHAT_SHEET_KEY")

HERE = Path(__file__).parent

TEXT_OUTPUT_PATH = HERE.parent / "lib" / "clthat" / "text.json"
GIFS_OUTPUT_PATH = HERE.parent / "lib" / "clthat" / "gifs.json"


def main():
    client = get_gsheet_client()
    sheet = client.open_by_key(CLTHAT_SHEET_KEY)
    text_worksheet = sheet.get_worksheet(0)
    gifs_worksheet = sheet.get_worksheet(1)

    with TEXT_OUTPUT_PATH.open("w") as fp:
        json.dump(text_worksheet.col_values(1), fp, indent=2)
        print(f"Wrote to: {TEXT_OUTPUT_PATH}")

    gifs_values = gifs_worksheet.get_all_values()
    with GIFS_OUTPUT_PATH.open("w") as fp:
        json.dump(
            [{"url": row[0], "description": row[1]} for row in gifs_values], fp, indent=2
        )
        print(f"Wrote to: {GIFS_OUTPUT_PATH}")
    print("Done.")


if __name__ == "__main__":
    main()
