"""Add events.amount_usd and events.is_rolling, and backfill amount_usd.

amount is free text ("3.89M OP", "$30,000 + 4,000 APT"), so the dashboard could
not sort or filter by reward. amount_usd is its rough USD reading, the same one
the minimum-reward floor uses. is_rolling records whether the content said
applications are accepted on a rolling basis, so a missing deadline can read
"rolling" instead of "not stated"; it is unknown (NULL) for existing rows.

Idempotent — safe to run repeatedly. --recompute re-reads every amount, for
when the amount parser changes:

    docker compose build pipeline chat-api
    docker compose run --rm pipeline python -m scripts.migrate_events_amount_usd_rolling
    docker compose run --rm pipeline python -m scripts.migrate_events_amount_usd_rolling --recompute
"""
import argparse

from sqlalchemy import text

from src.classifier.amount_filter import parse_amount_usd
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recompute", action="store_true", help="re-read amount_usd for every event")
    args = parser.parse_args()

    with engine.begin() as conn:
        for column, ddl in (("amount_usd", "DOUBLE PRECISION"), ("is_rolling", "BOOLEAN")):
            if _column_exists(conn, column):
                print(f"events.{column} already present — skipping add.")
            else:
                conn.execute(text(f"ALTER TABLE events ADD COLUMN {column} {ddl}"))
                print(f"Added events.{column}.")

        where = "amount IS NOT NULL" + ("" if args.recompute else " AND amount_usd IS NULL")
        rows = conn.execute(text(f"SELECT id, amount, amount_usd FROM events WHERE {where}")).all()
        changed = 0
        for event_id, amount, current in rows:
            usd = parse_amount_usd(amount)
            if usd != current:
                conn.execute(text("UPDATE events SET amount_usd = :usd WHERE id = :id"), {"usd": usd, "id": event_id})
                changed += 1
                if args.recompute:
                    print(f"event #{event_id}: {amount!r} {current} -> {usd}")
        print(f"Updated amount_usd for {changed} of {len(rows)} event(s) with an amount.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
