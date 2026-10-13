"""Merge stored Events that the current L2 dedup rules treat as one opportunity.

Groups come from src.dedup.duplicates.find_duplicate_groups: a shared per-item
source URL (tweet, feed entry, search result, listing entry), or equal title keys
whose deadlines and chains do not conflict. In each group the survivor is the
Event the team triaged (shortlisted before dismissed), else the best-sourced,
else the oldest. Sources, push history and missing fields move to it; the
duplicates and their vectors are deleted.

Dry run by default; --apply writes:

    docker compose run --rm pipeline python -m scripts.merge_duplicate_events
    docker compose run --rm pipeline python -m scripts.merge_duplicate_events --apply
"""
import argparse

from src.db.database import SessionLocal
from src.dedup.duplicates import choose_survivor, find_duplicate_groups, merge_group
from src.dedup.vector_store import VectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="merge (default: only report)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        groups = find_duplicate_groups(db)
        store = VectorStore() if args.apply else None
        for group in groups:
            keep = choose_survivor(db, group)
            print(f"keep #{keep.id} [{keep.triage_status}] {keep.title[:70]}")
            for event in group:
                if event.id != keep.id:
                    print(f"  merge #{event.id} [{event.triage_status}] {event.title[:70]}")
            if args.apply:
                merge_group(db, group, vector_store=store)
        verb = "Merged" if args.apply else "Would merge"
        print(f"{verb} {sum(len(g) - 1 for g in groups)} duplicate Event(s) in {len(groups)} group(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
