# SPDX-License-Identifier: Apache-2.0
"""Keep the test runtime independent from a developer's Compose .env file."""

import os
from pathlib import Path
from uuid import uuid4

import pytest


TEST_DATABASE = Path("/tmp") / f"recordlane-pytest-{uuid4().hex}.db"
TEST_DATABASE_URL = os.environ.get("RECORDLANE_TEST_DATABASE_URL", f"sqlite:///{TEST_DATABASE}")
if not TEST_DATABASE_URL.startswith("sqlite") and not TEST_DATABASE_URL.rsplit("/", 1)[-1].startswith("recordlane_test"):
    raise RuntimeError("RECORDLANE_TEST_DATABASE_URL must target a database named recordlane_test*")
os.environ["RECORDLANE_ENVIRONMENT"] = "test"
os.environ["RECORDLANE_DATABASE_URL"] = TEST_DATABASE_URL
os.environ["RECORDLANE_DEMO_MODE"] = "true"
os.environ["RECORDLANE_DEMO_ALLOW_REVERSE_PROXY"] = "false"


@pytest.fixture(autouse=True)
def reset_test_database():
    from recordlane.database import Base, engine
    from recordlane.operations.migrate import migrate, schema_migrations

    schema_migrations.drop(engine, checkfirst=True)
    Base.metadata.drop_all(engine)
    migrate(engine)
    yield


@pytest.fixture(scope="session", autouse=True)
def remove_test_database_after_session():
    yield
    from recordlane.database import engine

    engine.dispose()
    if TEST_DATABASE_URL.startswith("sqlite"):
        TEST_DATABASE.unlink(missing_ok=True)
