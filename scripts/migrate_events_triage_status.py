"""Add events.triage_status and events.triaged_at.

The dashboard triages every opportunity as new, shortlisted or dismissed.
is_dismissed could only say "dismissed or not", so it could not tell an item
nobody has looked at from one the team decided to pursue. Existing dismissals
are carried over; everything else starts as "new".

is_dismissed stays in place (and is kept in sync on writes) so a rollback to the
previous release still sees the same dismissals.

Idempotent — safe to run repeatedly:

    docker exec grant_radar_pipeline python -m scripts.migrate_events_triage_status
"""
from sqlalchemy import text

from src.db.database import engine


def _column_exists(conn, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.columns"
                "  WHERE table_name = 'events' AND column_name = :column"
                ")"
            ),
            {"column": column},
        ).scalar()
    )


def main() -> int:
    with engine.begin() as conn:
        if _column_exists(conn, "triage_status"):
            print("events.triage_status already present — skipping add.")
        else:
            conn.execute(
                text(
                    "ALTER TABLE events "
                    "ADD COLUMN triage_status VARCHAR(16) NOT NULL DEFAULT 'new'"
                )
            )
            print("Added events.triage_status.")

        if _column_exists(conn, "triaged_at"):
            print("events.triaged_at already present — skipping add.")
        else:
            conn.execute(
                text("ALTER TABLE events ADD COLUMN triaged_at TIMESTAMP WITH TIME ZONE")
            )
            print("Added events.triaged_at.")

        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_events_triage_status "
                "ON events (triage_status)"
            )
        )

        # Only rows still at the default are backfilled, so a re-run never
        # overwrites a decision made in the dashboard after the first run.
        backfilled = conn.execute(
            text(
                "UPDATE events SET triage_status = 'dismissed' "
                "WHERE is_dismissed IS TRUE AND triage_status = 'new'"
            )
        ).rowcount
        print(f"Backfilled {backfilled} dismissed event(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
