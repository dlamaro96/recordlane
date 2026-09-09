# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import text

from recordlane.database import Base, engine
import recordlane.models  # noqa: F401


def main() -> None:
    # Alpha baseline. Future released schemas use numbered, compatibility-checked
    # migrations; create_all is intentionally limited to the initial fixture.
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(82374812)"))
        Base.metadata.create_all(connection)


if __name__ == "__main__":
    main()

