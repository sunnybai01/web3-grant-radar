import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.classifier.amount_filter import parse_amount_usd


@pytest.mark.parametrize(
    "text,expected",
    [
        ("$50,000", 50_000),
        ("50,000 USD", 50_000),
        ("$100k", 100_000),
        ("Up to $2.5M in grants", 2_500_000),
        ("10000 USDC", 10_000),
        ("€10,000", 11_000),
        ("5 ETH", 15_000),
        ("0.5 BTC", 30_000),
        # A range or a tiered pool is worth its top figure to an applicant.
        ("$1,000 - $50,000", 50_000),
        ("$100,000 total prize pool, $2,000 per winner", 100_000),
        # No currency stated at all — read as USD.
        ("3000", 3_000),
    ],
)
def test_parses_common_amount_formats(text, expected) -> None:
    assert parse_amount_usd(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "Not specified",
        "TBD",
        # Unpriceable token: could be worth anything, so it stays unknown.
        "500000 FOO tokens",
        # A year is not a prize.
        "Hackathon 2026",
        # A share, not a sum.
        "top 10%",
    ],
)
def test_unreadable_amounts_are_unknown(text) -> None:
    assert parse_amount_usd(text) is None


def test_currency_ticker_is_not_read_as_a_scale_suffix() -> None:
    # The "m" in "matic" must not turn 5 MATIC into 5 million.
    assert parse_amount_usd("5 MATIC") == pytest.approx(2.5)


def test_named_currency_wins_over_unknown_trailing_word() -> None:
    assert parse_amount_usd("$4,000 per team") == pytest.approx(4_000)


# ---------------------------------------------------------------------------
# Grouped thousands and non-USD formats.
#
# Regression guard: "10.000 €" parsed as 11.0 and "$1 000 000" as 1.0, so the
# MIN_AMOUNT_USD floor silently dropped real grants from European and
# space-grouped sources. "1,5 M" went the other way and inflated 10x.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("10.000 €", 11_000),
        ("50.000 EUR", 55_000),
        ("$1 000 000", 1_000_000),
        ("10 000 USDC", 10_000),
        ("1.000.000 USD", 1_000_000),
        ("€1.500.000", 1_650_000),
        ("$12,345.67", 12_345.67),
    ],
)
def test_grouped_thousands_are_read_at_full_scale(text, expected) -> None:
    assert parse_amount_usd(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,5 M", 1_500_000),
        ("1,5M", 1_500_000),
    ],
)
def test_decimal_comma_is_not_a_thousands_separator(text, expected) -> None:
    assert parse_amount_usd(text) == pytest.approx(expected)


def test_comma_thousands_still_parses() -> None:
    assert parse_amount_usd("$1,500") == pytest.approx(1_500)
    assert parse_amount_usd("1,500") == pytest.approx(1_500)


@pytest.mark.parametrize("text", ["0", "$0", "0.00 USD", "0 USDC"])
def test_zero_means_not_stated(text) -> None:
    """The floor must keep these: 0.0 was being read as "worth nothing"."""
    assert parse_amount_usd(text) is None
