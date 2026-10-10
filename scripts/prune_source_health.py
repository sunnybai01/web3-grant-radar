#!/usr/bin/env python3
"""Report (and optionally purge) source_health rows for sources that no longer exist.

`source_health` is never pruned, so rows survive config changes. The production
database held 107 rows against 83 configured sources — 33 orphans left behind by
the removed DefiLlama chain path and the old RSSHub/bounty set. Those ghosts made
the heartbeat report "18 sources down" when most of them are simply not part of the
pipeline any more and can never recover.

Usage:
    python scripts/prune_source_health.py            # report only
    python scripts/prune_source_health.py --apply    # delete the orphans
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.database import SessionLocal
from src.db.models import SourceHealth
from src.fetchers.builder import load_sources_config


def _configured_names() -> set[str]:
    config = load_sources_config()
    return {source["name"] for source in config.get("sources", [])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually delete the orphan rows")
    args = parser.parse_args()

    configured = _configured_names()
    db = SessionLocal()
    try:
        rows = db.query(SourceHealth).order_by(SourceHealth.source_name).all()
        orphans = [row for row in rows if row.source_name not in configured]
        down_orphans = [row for row in orphans if row.status == "down"]

        print(f"configured sources : {len(configured)}")
        print(f"source_health rows : {len(rows)}")
        print(f"orphan rows        : {len(orphans)} (of which {len(down_orphans)} marked down)")

        for row in orphans:
            print(f"  - {row.source_name:<40} status={row.status} failures={row.consecutive_failures}")

        if not args.apply:
            print("\nReport only. Re-run with --apply to delete these rows.")
            return 0

        for row in orphans:
            db.delete(row)
        db.commit()
        print(f"\nDeleted {len(orphans)} orphan source_health row(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
