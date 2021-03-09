#!/usr/bin/env python3
from sqlalchemy_utils import create_database
from sqlalchemy_utils import drop_database

from bot import settings


def main():
    drop_database(str(settings.DATABASE_URL))
    create_database(str(settings.DATABASE_URL))


if __name__ == "__main__":
    main()
