"""Bring stored Events in line with the current L2 dedup rules.

1. Normalize events.ecosystem to canonical ids ("bnb chain" / "binance" -> "bnb"),
   the same mapping the classifier now applies to new Events.
2. Re-embed every Event as title + description. Events created before the change
   were indexed from an LLM summary with a "| deadline:… | ecosystem:…" suffix,
   so incoming items and stored Events never compared like with like.

Idempotent — safe to run repeatedly. --dry-run reports without writing:

    docker compose run --rm pipeline python -m scripts.rebuild_dedup_index --dry-run
    docker compose run --rm pipeline python -m scripts.rebuild_dedup_index
"""
import argparse

from src.classifier.ecosystem import normalize_ecosystem
from src.db.database import SessionLocal
from src.db.models import Event
from src.dedup.reconcile import reconcile_vector_index
from src.dedup.vector_store import VectorStore

ALL_EVENTS_WINDOW_DAYS = 100_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        changes = []
        for event in db.query(Event).order_by(Event.id):
            canonical = normalize_ecosystem(event.ecosystem)
            if canonical != event.ecosystem:
                changes.append((event.id, event.ecosystem, canonical))
                if not args.dry_run:
                    event.ecosystem = canonical
        for event_id, old, new in changes:
            print(f"event #{event_id}: ecosystem {old!r} -> {new!r}")
        print(f"{len(changes)} ecosystem value(s) {'would change' if args.dry_run else 'normalized'}.")
        if args.dry_run:
            print(f"Would re-embed {db.query(Event).count()} Event(s).")
            return 0
        db.commit()

        summary = reconcile_vector_index(
            db, VectorStore(), window_days=ALL_EVENTS_WINDOW_DAYS, rebuild=True
        )
        print(f"Re-embedded {summary['indexed']}/{summary['candidates']} Event(s); {summary['failed']} failed.")
        return 1 if summary["failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
