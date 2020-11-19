#!/usr/bin/env python3
from sqlalchemy_utils import create_database, drop_database

import bot


def main():
    drop_database(str(bot.DATABASE_URL))
    create_database(str(bot.DATABASE_URL))


if __name__ == "__main__":
    main()
