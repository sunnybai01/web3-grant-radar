import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.twitter_client import TwikitTimelineClient


def test_extract_user_rest_id_from_graphql_payload() -> None:
    payload = {
        "data": {
            "user": {
                "result": {
                    "rest_id": "123456",
                }
            }
        }
    }

    assert TwikitTimelineClient._extract_user_rest_id(payload) == "123456"


def test_extract_timeline_rows_and_cursor_from_graphql_payload() -> None:
    payload = {
        "data": {
            "user": {
                "result": {
                    "timeline_v2": {
                        "timeline": {
                            "instructions": [
                                {
                                    "type": "TimelineAddEntries",
                                    "entries": [
                                        {
                                            "entryId": "tweet-111",
                                            "content": {
                                                "itemContent": {
                                                    "tweet_results": {
                                                        "result": {
                                                            "rest_id": "111",
                                                            "legacy": {
                                                                "full_text": "Builder grants are open now https://t.co/demo",
                                                                "entities": {
                                                                    "urls": [
                                                                        {
                                                                            "expanded_url": "https://example.org/apply"
                                                                        }
                                                                    ]
                                                                },
                                                            },
                                                            "core": {
                                                                "user_results": {
                                                                    "result": {
                                                                        "legacy": {
                                                                            "screen_name": "gitcoin"
                                                                        }
                                                                    }
                                                                }
                                                            },
                                                            "quoted_status_result": {
                                                                "result": {
                                                                    "legacy": {
                                                                        "full_text": "Quoted tweet text"
                                                                    }
                                                                }
                                                            },
                                                        }
                                                    }
                                                }
                                            },
                                        },
                                        {
                                            "entryId": "cursor-bottom-222",
                                            "content": {
                                                "cursorType": "Bottom",
                                                "value": "NEXT_CURSOR",
                                            },
                                        },
                                    ],
                                }
                            ]
                        }
                    }
                }
            }
        }
    }

    rows, next_cursor = TwikitTimelineClient._extract_timeline_rows(payload, "fallback_user", max_count=1)

    assert next_cursor == "NEXT_CURSOR"
    assert rows == [
        {
            "id": "111",
            "url": "https://x.com/gitcoin/status/111",
            "text": "Builder grants are open now https://t.co/demo",
            "author_screen_name": "gitcoin",
            "quoted_text": "Quoted tweet text",
            "link_urls": ["https://example.org/apply"],
            # created_at is passed through for the staleness filter; a tweet
            # without it can only survive on an LLM-extracted deadline.
            "created_at": None,
        }
    ]