"""Add events.start_date.

The classifier already extracted start_date but the column never existed, so the
value was silently dropped and staleness checks had nothing to test when an
opportunity stated an opening date but no deadline.

Idempotent — safe to run repeatedly:

    docker exec web3_agent_main python -m scripts.migrate_events_start_date
"""
from sqlalchemy import text

from src.db.database import engine


def main() -> int:
    with engine.begin() as conn:
        exists = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.columns"
                "  WHERE table_name = 'events' AND column_name = 'start_date'"
                ")"
            )
        ).scalar()

        if exists:
            print("events.start_date already present — nothing to do.")
            return 0

        conn.execute(
            text("ALTER TABLE events ADD COLUMN start_date TIMESTAMP WITH TIME ZONE")
        )
        print("Added events.start_date.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
