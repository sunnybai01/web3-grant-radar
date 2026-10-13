"""Re-verify every live Event with the current verifier.

Stored verdicts describe the verifier as it was when each Event was created.
Run this after the verifier changes. It makes network requests: one
reachability check and one GoPlus phishing-site lookup per Event (plus CertiK
and ScamSniffer when keys are set). --dry-run reports the new verdicts and
rolls back:

    docker compose run --rm pipeline python -m scripts.reverify_events --dry-run
    docker compose run --rm pipeline python -m scripts.reverify_events
"""
import argparse
from collections import Counter

from src.db.database import SessionLocal
from src.db.models import Event
from src.verifier.reverify import LIVE_STATUSES, reverify_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report without saving")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        before = Counter(
            ((e.verification_log or {}).get("verdict") or "none", bool(e.is_verified))
            for e in db.query(Event).filter(Event.status.in_(LIVE_STATUSES))
        )
        print("before (verdict, is_verified):", dict(before))
        after = reverify_events(db, commit=not args.dry_run)
        print("after:", after, "(dry run, not saved)" if args.dry_run else "(saved)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
