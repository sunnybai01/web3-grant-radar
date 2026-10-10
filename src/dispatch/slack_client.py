"""Slack dispatch — Block Kit cards, Thread silent append, status updates."""
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from config.settings import settings
from src.classifier.scorer import stars_from_score

logger = logging.getLogger(__name__)


def _retry_handlers() -> list:
    """Retry handlers for the Slack client.

    slack_sdk's default set only covers connection errors, so a 429
    ("ratelimited") response dropped the card instead of waiting out the window.
    Pushing one message per event makes bursts likely.
    """
    return [RateLimitErrorRetryHandler(max_retry_count=3)]

EMOJI_MAP = {
    "GRANT": "💰",
    "HACKATHON": "🏆",
    "BOUNTY": "🔍",
}

COLOR_MAP = {
    "GRANT": "#2EB67D",     # green
    "HACKATHON": "#E01E5A", # red/pink
    "BOUNTY": "#36C5F0",    # blue
}

SOURCE_TYPE_LABELS = {
    "twitter": "Twitter",
    "tavily_search": "Tavily",
}


def _format_event_type(event_type: str) -> str:
    normalized = (event_type or "other").strip().upper()
    if normalized in {"GRANT", "HACKATHON", "BOUNTY"}:
        return normalized.title()
    return "Other"


def _format_source_type(source_type: str) -> str:
    normalized = (source_type or "").strip().lower()
    if not normalized:
        return "Unknown"
    return SOURCE_TYPE_LABELS.get(normalized, normalized.replace("_", " ").title())


def _format_slack_link(url: str, label: str) -> str:
    if not url:
        return ""
    return f"<{url}|{label}>"


def _format_counter_items(items: Dict[str, Any]) -> str:
    if not items:
        return "None"
    return ", ".join(f"{key}: {value}" for key, value in items.items())


# --- Daily summary table rendering -----------------------------------------
# Slack cannot do both aligned columns and clickable links in one element: a
# ``` block renders monospace but strips link markup, while mrkdwn linkifies but
# uses a proportional font where space-padding does not align. The summary table
# therefore lives in a code block and the URLs follow it as a numbered link row.

SUMMARY_TABLE_ROW_LIMIT = 25

TYPE_ABBREV = {"HACKATHON": "HACK", "GRANT": "GRANT", "BOUNTY": "BOUNTY"}

# (header, width, align) — one definition drives both the header and every row so
# the two cannot drift apart. Total renders at 80 chars: wide enough for real titles
# and amounts, and Slack scrolls a code block horizontally on narrow screens.
SUMMARY_COLUMNS = (
    ("#", 3, "r"),
    ("SCORE", 5, "r"),
    ("TYPE", 5, "l"),
    ("TITLE", 30, "l"),
    ("AMOUNT", 12, "l"),
    ("DEADLINE", 10, "l"),
    ("NEW", 3, "l"),
)


def _pad(value: str, width: int, align: str) -> str:
    return value.rjust(width) if align == "r" else value.ljust(width)


def _summary_table_line(cells: tuple) -> str:
    return "  ".join(
        _pad(_truncate(cell, width), width, align)
        for cell, (_head, width, align) in zip(cells, SUMMARY_COLUMNS)
    ).rstrip()


def _truncate(value: str, width: int) -> str:
    value = (value or "").strip()
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "…"


def _format_score(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, (int, float)) else "—"


def _format_type_abbrev(event_type: str) -> str:
    normalized = (event_type or "other").strip().upper()
    return TYPE_ABBREV.get(normalized, _truncate(normalized, 5))


def _summary_table_row(index: int, event: Dict[str, Any], is_new: bool) -> str:
    return _summary_table_line(
        (
            str(index),
            _format_score(event.get("final_score")),
            _format_type_abbrev(str(event.get("event_type") or "")),
            str(event.get("title") or "Untitled"),
            str(event.get("amount") or "—"),
            str(event.get("deadline") or "Rolling"),
            "*" if is_new else "",
        )
    )


def _score_sort_key(event: Dict[str, Any]) -> float:
    score = event.get("final_score")
    return score if isinstance(score, (int, float)) else -1.0


def _render_link_rows(links: list, per_row: int = 10) -> list:
    """Chunk the numbered links so a long table does not produce one giant line."""
    rows = []
    for start in range(0, len(links), per_row):
        chunk = links[start : start + per_row]
        prefix = "🔗 " if start == 0 else "     "
        rows.append(
            prefix + " · ".join(_format_slack_link(url, f"#{i}") for i, _label, url in chunk)
        )
    return rows


def _render_summary_table(events: list, new_ids: set) -> tuple[str, list]:
    """Return (code-block table, [(index, label, url)]) for the given events."""
    header = _summary_table_line(tuple(head for head, _width, _align in SUMMARY_COLUMNS))
    # Full width regardless of the header's trailing rstrip, so the rule spans the table.
    rule_width = sum(width for _head, width, _align in SUMMARY_COLUMNS) + 2 * (
        len(SUMMARY_COLUMNS) - 1
    )

    rows = [header, "─" * rule_width]
    links = []

    # The score column is the whole point of the table, so guarantee it reads top-down
    # here rather than trusting whatever order the caller happened to pass in.
    events = sorted(events, key=_score_sort_key, reverse=True)

    for index, event in enumerate(events[:SUMMARY_TABLE_ROW_LIMIT], start=1):
        event_id = event.get("id")
        is_new = event_id in new_ids if event_id is not None else False
        rows.append(_summary_table_row(index, event, is_new))

        url = event.get("application_url") or event.get("source_url") or ""
        if url:
            links.append((index, str(event.get("title") or "Untitled"), url))

    dropped = len(events) - SUMMARY_TABLE_ROW_LIMIT
    if dropped > 0:
        rows.append(f"… {dropped} more not shown")

    return "```\n" + "\n".join(rows) + "\n```", links


class SlackDispatcher:
    """Pushes structured opportunities to Slack via Block Kit."""

    def __init__(self):
        self._configured = bool(settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID)
        if self._configured:
            self.client = WebClient(token=settings.SLACK_BOT_TOKEN, retry_handlers=_retry_handlers())
            self.channel_id = settings.SLACK_CHANNEL_ID
        else:
            self.client = None
            self.channel_id = None
            logger.warning("Slack not configured — will generate Markdown reports only")

    @property
    def is_configured(self) -> bool:
        return self._configured

    def push_new_event(self, event: Dict[str, Any]) -> Optional[str]:
        """Push a rich Block Kit card for a new event.

        Returns the Slack message timestamp (slack_ts) on success, None on failure.
        If Slack is not configured, returns None immediately (no-op).
        """
        if not self._configured:
            return None
        event_type_raw = event.get("event_type", "other")
        event_type = (event_type_raw or "other").strip().upper()
        emoji = EMOJI_MAP.get(event_type, "📋")
        color = COLOR_MAP.get(event_type, "#808080")
        type_label = _format_event_type(event_type)
        stars = stars_from_score(event.get("final_score", 5.0))

        title = event.get("title", "Untitled Opportunity")
        amount = event.get("amount") or "Not specified"
        deadline = event.get("deadline") or "Rolling / Not specified"
        if hasattr(deadline, "strftime"):
            deadline = deadline.strftime("%Y-%m-%d")
        ecosystem = event.get("ecosystem", "Unknown").upper()
        track = event.get("track", "General")
        score = event.get("final_score", 0)
        source_tier = str(event.get("source_tier") or "").lower()
        official = bool(event.get("official", source_tier == "official"))
        source_trust = "Official" if official else "Discovery"
        verification = str(event.get("verification_verdict") or "unknown").title()
        app_url = event.get("application_url", "")
        source_url = event.get("source_url", app_url)
        source_type = _format_source_type(str(event.get("source_type") or ""))
        header_url = source_url or app_url or "https://slack.com"

        # Use a single-column fields block (one field only) to avoid two-column layout.
        detail_text = "\n".join([
            f"*Type:* `{type_label}`",
            f"*Score:* {stars} `{score}/10`",
            f"*Amount:* {amount}",
            f"*Deadline:* {deadline}",
            f"*Ecosystem:* {ecosystem}",
            f"*Track:* {track}",
            f"*Source type:* {source_type}",
            f"*Source trust:* {source_trust}",
            f"*Verification:* {verification}",
            f"*Heat:* {event.get('heat_count', 1)} source(s)",
        ])

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*<{header_url}|{emoji} [{event_type}] {title[:140]}>*",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": detail_text},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": event.get("description", "")[:500] or "No description available.",
                },
            },
            {"type": "divider"},
        ]

        # Action buttons
        actions = {"type": "actions", "elements": []}
        if app_url:
            actions["elements"].append({
                "type": "button",
                "text": {"type": "plain_text", "text": "🚀 Apply Now", "emoji": True},
                "url": app_url,
                "style": "primary",
            })

        if actions["elements"]:
            blocks.append(actions)

        try:
            resp = self.client.chat_postMessage(
                channel=self.channel_id,
                text=f"{emoji} [{event_type}] {title}",  # fallback text
                blocks=blocks,
                unfurl_links=False,
            )
            slack_ts = resp["ts"]
            logger.info(f"Slack push: event #{event.get('id')} -> ts={slack_ts}")
            return slack_ts
        except SlackApiError as e:
            logger.error(f"Slack push failed: {e.response['error']}")
            return None

    def append_to_thread(self, slack_ts: str, event_id: int,
                         source_type: str, source_name: str,
                         source_url: Optional[str] = None) -> bool:
        """Silently append a new source clue to the existing thread."""
        if not self._configured:
            return False
        source_link = f"<{source_url}|{source_name}>" if source_url else source_name
        text = f"🔗 *New source detected:* {source_link} ({source_type})\n_Heat increased for event #{event_id}_"

        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=slack_ts,
                text=text,
            )
            return True
        except SlackApiError as e:
            logger.error(f"Slack thread append failed: {e.response['error']}")
            return False

    def mark_expired(self, slack_ts: str, original_title: str) -> bool:
        """Update the original card: mark as [EXPIRED] and grey-out."""
        if not self._configured:
            return False
        title = f"🚫 [EXPIRED] {original_title[:120]}"
        try:
            self.client.chat_update(
                channel=self.channel_id,
                ts=slack_ts,
                text=title,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"~{title}~\n\n_This opportunity has expired. The card has been archived._",
                        },
                    },
                ],
            )
            return True
        except SlackApiError as e:
            logger.error(f"Slack update (expire) failed: {e.response['error']}")
            return False

    def send_heartbeat(self, stats: Dict[str, Any]) -> bool:
        """Send a heartbeat message with system stats."""
        if not self._configured:
            return False
        text = (
            f"💓 *Web3 Agent Heartbeat*\n"
            f"Today: {stats.get('fetched', 0)} fetched | "
            f"{stats.get('new', 0)} new | "
            f"{stats.get('deduped', 0)} deduped | "
            f"{stats.get('pushed', 0)} pushed\n"
            f"Unhealthy sources: {stats.get('unhealthy', 0)}"
        )
        try:
            self.client.chat_postMessage(channel=self.channel_id, text=text)
            return True
        except SlackApiError:
            return False

    def send_alert(self, message: str) -> bool:
        """Send an alert to the channel."""
        if not self._configured:
            return False
        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                text=f"⚠️ *Alert:* {message}",
                icon_emoji=":warning:",
            )
            return True
        except SlackApiError:
            return False

    def send_daily_summary(self, summary: Dict[str, Any]) -> Optional[str]:
        """Send a once-per-day operator summary to Slack."""
        if not self._configured:
            return None

        totals = summary.get("totals", {})
        today_scan_stats = summary.get("today_scan_stats", {}) or {}
        historical_high_score = summary.get("historical_high_score", {}) or {}
        source_names = summary.get("new_event_sources", []) or []
        new_events = summary.get("new_events", []) or []
        summary_date = summary.get("summary_date", "unknown-date")

        # One table, not two lists. new_events is a strict subset of the historical
        # set (same table, no date filter), so listing both repeated every one of
        # today's finds verbatim — that duplication was the main source of noise.
        active_events = historical_high_score.get("recent_events", []) or []
        new_ids = {event.get("id") for event in new_events if event.get("id") is not None}

        lines = [f"*📊 Daily Summary · {summary_date}*", ""]

        if active_events:
            new_today = sum(
                1 for event in active_events if event.get("id") in new_ids
            )
            headline = f"*🎯 Open opportunities · {len(active_events)} active"
            if new_today:
                headline += f", {new_today} new today"
            lines.append(headline + "*")

            table, links = _render_summary_table(active_events, new_ids)
            lines.append(table)
            lines.extend(_render_link_rows(links))
            if new_today:
                lines.append("_* = first seen today_")
        else:
            lines.append("_No open opportunities — everything is dismissed or expired._")

        funnel = " → ".join(
            [
                f"{totals.get('fetched', 0)} fetched",
                f"{totals.get('deduped', 0)} deduped",
                f"{totals.get('classified', 0)} classified",
                f"{totals.get('verified', 0)} verified",
                f"{totals.get('pushed', 0)} pushed",
            ]
        )

        lines.extend(["", f"*⚙️ Pipeline* · {funnel}"])

        # Only surface the breakdowns that actually have content — on a quiet day the
        # old layout printed "None · via None", which is noise pretending to be data.
        today_parts = [f"{today_scan_stats.get('total_new_events', 0)} new"]
        if today_scan_stats.get("by_event_type"):
            today_parts.append(_format_counter_items(today_scan_stats["by_event_type"]))
        if today_scan_stats.get("by_source_type"):
            today_parts.append(f"via {_format_counter_items(today_scan_stats['by_source_type'])}")
        lines.append("*📥 Today* · " + " · ".join(today_parts))

        if historical_high_score.get("by_event_type"):
            lines.append(
                "*📚 Active mix* · "
                + _format_counter_items(historical_high_score["by_event_type"])
            )
        if source_names:
            lines.append(f"*🌐 New sources today* · {', '.join(source_names)}")

        text = "\n".join(lines).strip()

        try:
            resp = self.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                unfurl_links=False,
            )
            return resp["ts"]
        except SlackApiError as e:
            logger.error(f"Slack daily summary failed: {e.response['error']}")
            return None

    def upload_report(self, report_path: Path, schedule: str, stats: Dict[str, Any]) -> bool:
        """Upload a generated Markdown report file to Slack as an attachment."""
        if not self._configured:
            return False

        try:
            summary = (
                f"📝 *Run report ({schedule})*\n"
                f"Fetched: {stats.get('fetched', 0)} | "
                f"New: {stats.get('new', 0)} | "
                f"Deduped: {stats.get('deduped', 0)} | "
                f"Verified: {stats.get('verified', 0)} | "
                f"Pushed: {stats.get('pushed', 0)}"
            )

            self.client.files_upload_v2(
                channel=self.channel_id,
                file=str(report_path),
                filename=report_path.name,
                title=f"Web3 Intelligence Report - {schedule}",
                initial_comment=summary,
            )
            logger.info(f"Slack report upload: {report_path}")
            return True
        except SlackApiError as e:
            logger.error(f"Slack report upload failed: {e.response['error']}")
            return False
        except Exception as e:
            logger.error(f"Slack report upload failed: {e}")
            return False
