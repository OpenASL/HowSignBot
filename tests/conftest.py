import os
from contextlib import suppress

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy_utils import create_database
from sqlalchemy_utils import drop_database

# Must be before bot import
os.environ["TESTING"] = "true"

from bot import settings, database  # noqa:E402


# https://www.starlette.io/database/#test-isolation
@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    url = str(settings.TEST_DATABASE_URL)
    engine = create_engine(url)
    with suppress(ProgrammingError):
        drop_database(url)
    create_database(url)
    database.store.metadata.create_all(engine)
    yield
    drop_database(url)


@pytest.fixture
async def store(create_test_database):
    await database.store.connect()
    yield database.store
    await database.store.disconnect()


@pytest.fixture
def db(store):
    return store.db
