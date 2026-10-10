"""Migrate raw_signals L1 dedup key from canonical_url to (canonical_url, content_hash).

A url-only unique key permanently blocks re-ingesting a page whose URL is stable
but whose content rolls over (grant listing pages, hackathon index pages), so every
opportunity added after the first fetch was invisible. Keying on the pair lets a
changed page back in; L2 semantic dedup still catches genuine reposts.

Idempotent — safe to run repeatedly. Run before deploying the matching code:

    docker exec grant_radar_pipeline python -m scripts.migrate_raw_signals_content_hash
"""
import sys

from sqlalchemy import text

from src.db.database import engine

OLD_CONSTRAINT = "uq_raw_signals_canonical_url"
NEW_CONSTRAINT = "uq_raw_signals_canonical_url_content"
NEW_INDEX = "ix_raw_signals_url_hash"


def _constraint_exists(conn, name: str) -> bool:
    return conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = :name)"
        ),
        {"name": name},
    ).scalar()


def _index_exists(conn, name: str) -> bool:
    return conn.execute(
        text("SELECT EXISTS (SELECT 1 FROM pg_class WHERE relname = :name AND relkind = 'i')"),
        {"name": name},
    ).scalar()


def main() -> int:
    with engine.begin() as conn:
        null_hashes = conn.execute(
            text("SELECT count(*) FROM raw_signals WHERE content_hash IS NULL")
        ).scalar()
        if null_hashes:
            # Postgres treats NULLs as distinct in a unique key, so these rows would
            # stop deduping entirely. Refuse rather than silently degrade L1.
            print(
                f"ABORT: {null_hashes} raw_signals rows have content_hash IS NULL. "
                "Backfill them before migrating.",
                file=sys.stderr,
            )
            return 1

        if _constraint_exists(conn, NEW_CONSTRAINT):
            print(f"{NEW_CONSTRAINT} already present — nothing to do.")
        else:
            # Duplicate (url, hash) pairs would block the new constraint. The old
            # url-only key made them impossible, but check rather than assume.
            dupes = conn.execute(
                text(
                    "SELECT count(*) FROM ("
                    "  SELECT canonical_url, content_hash FROM raw_signals"
                    "  GROUP BY canonical_url, content_hash HAVING count(*) > 1"
                    ") d"
                )
            ).scalar()
            if dupes:
                print(
                    f"ABORT: {dupes} duplicate (canonical_url, content_hash) pairs exist.",
                    file=sys.stderr,
                )
                return 1

            conn.execute(
                text(
                    f"ALTER TABLE raw_signals ADD CONSTRAINT {NEW_CONSTRAINT} "
                    "UNIQUE (canonical_url, content_hash)"
                )
            )
            print(f"Added {NEW_CONSTRAINT}.")

        if _constraint_exists(conn, OLD_CONSTRAINT):
            conn.execute(text(f"ALTER TABLE raw_signals DROP CONSTRAINT {OLD_CONSTRAINT}"))
            print(f"Dropped {OLD_CONSTRAINT}.")
        else:
            print(f"{OLD_CONSTRAINT} already absent.")

        if _index_exists(conn, NEW_INDEX):
            print(f"{NEW_INDEX} already present.")
        else:
            conn.execute(
                text(
                    f"CREATE INDEX {NEW_INDEX} ON raw_signals (canonical_url, content_hash)"
                )
            )
            print(f"Created {NEW_INDEX}.")

    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
