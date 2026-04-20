from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import check_database_connection, engine, get_table_names


EXPECTED_TABLES = {
    "alembic_version",
    "conversations",
    "documents",
    "knowledge_bases",
    "messages",
    "team_invites",
    "team_members",
    "teams",
    "users",
}


def main() -> int:
    try:
        check_database_connection()

        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                current_database = connection.execute(text("SELECT current_database()")).scalar_one()
            else:
                current_database = connection.engine.url.database or str(connection.engine.url)
            alembic_version = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()

        tables = set(get_table_names())
        missing_tables = sorted(EXPECTED_TABLES - tables)

        print(f"Database connected: {current_database}")
        print(f"Alembic version: {alembic_version}")
        print("Tables:", ", ".join(sorted(tables)))

        if missing_tables:
            print("Missing tables:", ", ".join(missing_tables), file=sys.stderr)
            return 1

        print("Database verification passed.")
        return 0
    except Exception as exc:
        print(f"Database verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
