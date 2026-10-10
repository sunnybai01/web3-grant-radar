"""Markdown report generator — fallback and complement to Slack push.

When Slack is not configured, the report serves as the primary output.
When Slack is configured, the report acts as a local audit trail.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from config.settings import settings
from src.classifier.scorer import stars_from_score

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"

EMOJI_MAP = {"grant": "💰", "hackathon": "🏆", "bounty": "🔍", "other": "📋"}


def _is_official_signal(event: Dict[str, Any]) -> bool:
    source_tier = str(event.get("source_tier") or "").lower()
    return bool(event.get("official", source_tier == "official"))


def _render_event(lines: List[str], event: Dict[str, Any], index: int) -> None:
    event_type = (event.get("event_type") or "other").lower()
    emoji = EMOJI_MAP.get(event_type, "📋")
    title = event.get("title", "Untitled")
    score = event.get("final_score")
    stars = stars_from_score(score) if score else ""
    amount = event.get("amount") or "Not specified"
    deadline = event.get("deadline") or "Rolling"
    if hasattr(deadline, "strftime"):
        deadline = deadline.strftime("%Y-%m-%d")
    ecosystem = (event.get("ecosystem") or "Unknown").upper()
    track = event.get("track") or "General"
    heat = event.get("heat_count", 1)
    desc = event.get("description") or ""
    app_url = event.get("application_url") or ""
    source_url = event.get("source_url") or ""
    source_trust = "Official" if _is_official_signal(event) else "Discovery"
    verification = str(event.get("verification_verdict") or "unknown").title()

    lines.append(f"### {index}. {emoji} [{event_type.upper()}] {title}")
    lines.append("")
    lines.append(f"| Field | Detail |")
    lines.append(f"|---|---|")
    lines.append(f"| **Score** | {stars} `{score}/10` |" if score else "| **Score** | — |")
    lines.append(f"| **Source trust** | {source_trust} |")
    lines.append(f"| **Verification** | {verification} |")
    lines.append(f"| **Amount** | {amount} |")
    lines.append(f"| **Deadline** | {deadline} |")
    lines.append(f"| **Ecosystem** | {ecosystem} |")
    lines.append(f"| **Track** | {track} |")
    lines.append(f"| **Heat** | {heat} source(s) |")
    if app_url:
        lines.append(f"| **Apply** | [{app_url}]({app_url}) |")
    if source_url and source_url != app_url:
        lines.append(f"| **Source** | [{source_url}]({source_url}) |")
    lines.append("")
    if desc:
        lines.append(f"{desc}")
        lines.append("")
    lines.append("---")
    lines.append("")


def generate_report(
    events: List[Dict[str, Any]],
    schedule: str,
    stats: Dict[str, Any],
) -> Path:
    """Generate a Markdown report from a list of event dicts.

    Args:
        events: list of event dicts with keys: id, event_type, title, amount,
                deadline, ecosystem, track, final_score, heat_count, description,
                application_url, source_url
        schedule: 'grant_hackathon' or 'bounty'
        stats: dict with fetched, new, deduped, classified, verified, fraud, pushed

    Returns:
        Path to the written report file.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M")
    filename = f"{schedule}_{ts}.md"
    filepath = REPORTS_DIR / filename

    lines = []
    lines.append(f"# Web3 Intelligence Report — {schedule.replace('_', ' ').title()}")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("## 📊 Pipeline Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Fetched | {stats.get('fetched', 0)} |")
    lines.append(f"| New events | {stats.get('new', 0)} |")
    lines.append(f"| Duplicates (L1+L2) | {stats.get('deduped', 0)} |")
    lines.append(f"| Classified | {stats.get('classified', 0)} |")
    lines.append(f"| Verified | {stats.get('verified', 0)} |")
    lines.append(f"| Fraud rejected | {stats.get('fraud', 0)} |")
    lines.append(f"| Pushed | {stats.get('pushed', 0)} |")
    lines.append("")

    if not events:
        lines.append("> ℹ️ No new opportunities found in this run.")
    else:
        lines.append(f"## 🎯 Opportunities Found ({len(events)})")
        lines.append("")
        confirmed = [event for event in events if _is_official_signal(event)]
        discovery = [event for event in events if not _is_official_signal(event)]

        index = 1
        if confirmed:
            lines.append("### Confirmed / Official Signals")
            lines.append("")
            for event in confirmed:
                _render_event(lines, event, index)
                index += 1

        if discovery:
            lines.append("### Discovery / Review Needed")
            lines.append("")
            for event in discovery:
                _render_event(lines, event, index)
                index += 1

    lines.append(f"*Report generated by Web3 Grant Radar V1*")
    lines.append("")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Report written: {filepath} ({len(events)} events)")

    return filepath


def generate_health_report(
    unhealthy_sources: List[Any],
) -> Path:
    """Generate a standalone health alert report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d_%H%M")
    filepath = REPORTS_DIR / f"health_alert_{ts}.md"

    lines = []
    lines.append(f"# ⚠️ Source Health Alert")
    lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.append("The following sources are in a degraded or down state:")
    lines.append("")
    lines.append("| Source | Status | Failures | Last Error |")
    lines.append("|--------|--------|----------|------------|")
    for s in unhealthy_sources:
        err = (s.last_error or "")[:80]
        lines.append(f"| {s.source_name} | {s.status} | {s.consecutive_failures} | {err} |")

    content = "\n".join(lines)
    filepath.write_text(content, encoding="utf-8")
    return filepath
