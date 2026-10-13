import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.dispatch.slack_client import SlackDispatcher


def test_push_new_event_includes_source_type_label() -> None:
    sent = {}

    class FakeClient:
        def chat_postMessage(self, **kwargs):
            sent.update(kwargs)
            return {"ts": "123.456"}

    dispatcher = SlackDispatcher.__new__(SlackDispatcher)
    dispatcher._configured = True
    dispatcher.client = FakeClient()
    dispatcher.channel_id = "C123"

    ts = dispatcher.push_new_event(
        {
            "id": 42,
            "event_type": "grant",
            "title": "Base Builder Rewards",
            "description": "Funding opportunity.",
            "amount": "$50,000",
            "deadline": "2026-07-30",
            "ecosystem": "base",
            "track": "DeFi",
            "final_score": 7.8,
            "heat_count": 1,
            "verification_verdict": "verified",
            "source_url": "https://x.com/buildonbase/status/1",
            "source_type": "twitter",
        }
    )

    assert ts == "123.456"
    detail_block = sent["blocks"][1]["fields"][0]["text"]
    assert "*Source type:* Twitter" in detail_block


def test_send_daily_summary_posts_message(monkeypatch) -> None:
    sent = {}

    class FakeClient:
        def chat_postMessage(self, **kwargs):
            sent.update(kwargs)
            return {"ts": "123.456"}

    dispatcher = SlackDispatcher.__new__(SlackDispatcher)
    dispatcher._configured = True
    dispatcher.client = FakeClient()
    dispatcher.channel_id = "C123"

    ts = dispatcher.send_daily_summary(
        {
            "summary_date": "2026-07-06",
            "totals": {"fetched": 60, "new": 2, "deduped": 35, "classified": 13, "verified": 4, "pushed": 1},
            "today_scan_stats": {
                "total_new_events": 2,
                "by_event_type": {"grant": 1, "bounty": 1},
                "by_source_type": {"twitter": 1, "rss": 1},
            },
            "historical_high_score": {
                "total_count": 2,
                "by_event_type": {"grant": 1, "hackathon": 1},
                "recent_events": [
                    {
                        "id": 1,
                        "event_type": "grant",
                        "title": "Base Builder Rewards",
                        "final_score": 7.8,
                        "amount": "$50,000",
                        "deadline": "2026-07-30",
                        "source_type": "twitter",
                        "source_name": "twitter_buildonbase",
                        "source_url": "https://x.com/buildonbase/status/1",
                    },
                    {
                        "id": 2,
                        "event_type": "hackathon",
                        "title": "ETHGlobal New York",
                        "final_score": 8.6,
                        "amount": "",
                        "deadline": "",
                        "source_type": "rss",
                        "source_name": "ethglobal_rss",
                        "source_url": "https://ethglobal.com/events/ny",
                    },
                ],
            },
            "new_events_count": 1,
            "new_event_sources": ["twitter_buildonbase"],
            "new_events": [
                {
                    "id": 1,
                    "event_type": "grant",
                    "title": "Base Builder Rewards",
                    "final_score": 7.8,
                    "amount": "$50,000",
                    "deadline": "2026-07-30",
                    "source_type": "twitter",
                    "source_name": "twitter_buildonbase",
                    "source_url": "https://x.com/buildonbase/status/1",
                }
            ],
        }
    )

    text = sent["text"]

    assert ts == "123.456"
    assert sent["channel"] == "C123"
    assert "Daily Summary · 2026-07-06" in text

    # One table, score-sorted: 8.6 outranks 7.8 even though it was passed second.
    assert "SCORE" in text and "DEADLINE" in text
    body = [line for line in text.splitlines() if "ETHGlobal" in line or "Base Builder" in line]
    assert body[0].strip().startswith("1")
    assert "ETHGlobal New York" in body[0]
    assert "8.6" in body[0]
    assert body[1].strip().startswith("2")
    assert "Base Builder Rewards" in body[1]
    assert "$50,000" in body[1]
    assert "2026-07-30" in body[1]
    # Missing amount/deadline degrade to placeholders, never to "None".
    assert "Rolling" in body[0]
    assert "None" not in text

    # Today's find is marked in-table instead of repeated as a second list.
    assert body[1].rstrip().endswith("*")
    assert "_* = first seen today_" in text
    assert text.count("Base Builder Rewards") == 1

    # URLs survive as a numbered link row (links cannot live inside a code block).
    assert "<https://ethglobal.com/events/ny|#1>" in text
    assert "<https://x.com/buildonbase/status/1|#2>" in text

    assert "515 fetched" not in text
    assert "60 fetched → 35 deduped → 13 classified → 4 verified → 1 pushed" in text
    assert "*📥 Today* · 2 new · grant: 1, bounty: 1 · via twitter: 1, rss: 1" in text
    assert "*🌐 New sources today* · twitter_buildonbase" in text


def test_send_daily_summary_quiet_day_omits_empty_breakdowns() -> None:
    sent = {}

    class FakeClient:
        def chat_postMessage(self, **kwargs):
            sent.update(kwargs)
            return {"ts": "123.456"}

    dispatcher = SlackDispatcher.__new__(SlackDispatcher)
    dispatcher._configured = True
    dispatcher.client = FakeClient()
    dispatcher.channel_id = "C123"

    dispatcher.send_daily_summary(
        {
            "summary_date": "2026-07-07",
            "totals": {"fetched": 10, "deduped": 10},
            "today_scan_stats": {"total_new_events": 0, "by_event_type": {}, "by_source_type": {}},
            "historical_high_score": {"total_count": 0, "by_event_type": {}, "recent_events": []},
            "new_events": [],
            "new_event_sources": [],
        }
    )

    text = sent["text"]

    assert "No open opportunities" in text
    assert "*📥 Today* · 0 new" in text
    # The old layout printed "None · via None" here.
    assert "None" not in text
    assert "Active mix" not in text
    assert "New sources today" not in text


def test_summary_table_truncates_beyond_the_row_limit() -> None:
    from src.dispatch.slack_client import SUMMARY_TABLE_ROW_LIMIT, _render_summary_table

    events = [
        {"id": i, "event_type": "grant", "title": f"Grant {i}", "final_score": float(i)}
        for i in range(SUMMARY_TABLE_ROW_LIMIT + 4)
    ]

    table, links = _render_summary_table(events, set())

    assert table.count("\n") == SUMMARY_TABLE_ROW_LIMIT + 4  # header + rule + rows + notice
    assert "… 4 more not shown" in table
    assert links == []  # no urls supplied


def test_push_new_event_tolerates_a_missing_ecosystem_and_track() -> None:
    """A Devpost hackathon with no ecosystem crashed the card build (#181 never pushed)."""
    sent = {}

    class FakeClient:
        def chat_postMessage(self, **kwargs):
            sent.update(kwargs)
            return {"ts": "1.2"}

    dispatcher = SlackDispatcher.__new__(SlackDispatcher)
    dispatcher._configured = True
    dispatcher.client = FakeClient()
    dispatcher.channel_id = "C123"

    ts = dispatcher.push_new_event({
        "id": 181, "event_type": "hackathon", "title": "SUSTAIN-A-THON 2.0",
        "amount": "$150,000", "deadline": "2026-10-28", "ecosystem": None, "track": None,
        "final_score": 4.95, "source_url": "https://sustain-a-thon.devpost.com/",
        "source_type": "devpost_api",
    })

    assert ts == "1.2"
    fields = " ".join(f["text"] for f in sent["blocks"][1]["fields"])
    assert "None" not in fields
