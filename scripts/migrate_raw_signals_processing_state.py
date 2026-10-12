"""Add processing state to raw_signals: status, attempts, last_error, processed_at.

L1 dedup used to record a signal before it was judged, so an LLM outage or a
crash mid-item made that content "already seen" forever. Now a signal counts as
seen only once processed (status done); failed ones are retried when fetched
again, up to RAW_SIGNAL_MAX_ATTEMPTS.

Existing rows were all judged by the old pipeline (or lost without a trace), so
they are backfilled as "done". New rows start as "pending".

Idempotent — safe to run repeatedly:

    docker compose build pipeline chat-api
    docker compose run --rm pipeline python -m scripts.migrate_raw_signals_processing_state
"""
from sqlalchemy import text

from src.db.database import engine


def _column_exists(conn, column: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.columns"
                "  WHERE table_name = 'raw_signals' AND column_name = :column"
                ")"
            ),
            {"column": column},
        ).scalar()
    )


def main() -> int:
    with engine.begin() as conn:
        if _column_exists(conn, "status"):
            print("raw_signals.status already present — skipping add.")
        else:
            # The DEFAULT backfills existing rows as done; new rows default to pending.
            conn.execute(
                text("ALTER TABLE raw_signals ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'done'")
            )
            conn.execute(text("ALTER TABLE raw_signals ALTER COLUMN status SET DEFAULT 'pending'"))
            print("Added raw_signals.status (existing rows marked done).")

        if _column_exists(conn, "attempts"):
            print("raw_signals.attempts already present — skipping add.")
        else:
            conn.execute(
                text("ALTER TABLE raw_signals ADD COLUMN attempts INTEGER NOT NULL DEFAULT 1")
            )
            print("Added raw_signals.attempts.")

        if _column_exists(conn, "last_error"):
            print("raw_signals.last_error already present — skipping add.")
        else:
            conn.execute(text("ALTER TABLE raw_signals ADD COLUMN last_error TEXT"))
            print("Added raw_signals.last_error.")

        if _column_exists(conn, "processed_at"):
            print("raw_signals.processed_at already present — skipping add.")
        else:
            conn.execute(
                text("ALTER TABLE raw_signals ADD COLUMN processed_at TIMESTAMP WITH TIME ZONE")
            )
            print("Added raw_signals.processed_at.")

        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_raw_signals_status ON raw_signals (status)")
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
