# SPDX-License-Identifier: Apache-2.0
"""Keep the test runtime independent from a developer's Compose .env file."""

import os
from pathlib import Path
from uuid import uuid4

import pytest


TEST_DATABASE = Path("/tmp") / f"recordlane-pytest-{uuid4().hex}.db"
os.environ["RECORDLANE_ENVIRONMENT"] = "test"
os.environ["RECORDLANE_DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"
os.environ["RECORDLANE_DEMO_MODE"] = "true"
os.environ["RECORDLANE_DEMO_ALLOW_REVERSE_PROXY"] = "false"


@pytest.fixture(autouse=True)
def reset_test_database():
    from recordlane.database import Base, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(scope="session", autouse=True)
def remove_test_database_after_session():
    yield
    from recordlane.database import engine

    engine.dispose()
    TEST_DATABASE.unlink(missing_ok=True)
