"""Read a free-text prize/funding amount into a rough USD figure.

The classifier emits `amount` as whatever the source wrote ("$50,000", "Up to
100k USDC", "5 ETH", "Not specified"), so the pipeline needs a best-effort
number before it can apply a minimum-reward floor.

Design bias: never invent a small number. Every ambiguity resolves toward
"unknown" (return None) or toward the larger reading, because a wrong drop
loses a real opportunity while a wrong keep only costs one operator glance.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Longest-first: "usdc" must win over "usd", "weth" over "eth".
_CURRENCIES = (
    "pyusd", "fdusd", "tusd", "usdc", "usdt", "usdg", "usde", "usds", "usd", "us$", "eur", "gbp", "cny", "rmb", "jpy",
    "weth", "eth", "wbtc", "btc", "sol", "bnb", "matic", "avax", "near",
    "atom", "dot", "sui", "apt", "arb", "dai",
    "strk", "op", "pol", "xlm", "ton",
)

# Rough USD rates — only ever used to decide which side of the floor an amount
# falls on, never shown to anyone, so precision is irrelevant. Rounded upward
# where they are uncertain, so a moving market can't turn a real prize into a
# silent drop. A ticker missing from this table makes the amount unknown.
_USD_RATES = {
    "$": 1.0, "usd": 1.0, "us$": 1.0, "usdc": 1.0, "usdt": 1.0, "dai": 1.0,
    # USD stablecoins. Superteam pays in USDG; unread, "up to 200 USDG" slipped
    # past the minimum-reward floor.
    "usdg": 1.0, "pyusd": 1.0, "usde": 1.0, "usds": 1.0, "fdusd": 1.0, "tusd": 1.0,
    "€": 1.1, "eur": 1.1, "£": 1.25, "gbp": 1.25,
    "¥": 0.15, "cny": 0.15, "rmb": 0.15, "jpy": 0.01,
    "eth": 3000.0, "weth": 3000.0, "btc": 60000.0, "wbtc": 60000.0,
    "sol": 150.0, "bnb": 600.0, "matic": 0.5, "avax": 30.0, "near": 5.0,
    "atom": 8.0, "dot": 6.0, "sui": 3.0, "apt": 8.0, "arb": 1.0,
    "op": 1.0, "strk": 0.5, "pol": 0.5, "xlm": 0.4, "ton": 5.0,
}

_MULTIPLIERS = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "billion": 1e9,
}

_CUR_ALT = "|".join(re.escape(code) for code in _CURRENCIES)
_MULT_ALT = "|".join(sorted(_MULTIPLIERS, key=len, reverse=True))

# One money token: optional currency in front, the number, an optional scale
# suffix, an optional currency (or "%") behind. Both currency slots reject a
# match glued to more letters so "matic" isn't read as the "m" million suffix
# and "dotted" isn't read as DOT.
_TOKEN_RE = re.compile(
    rf"(?:(?P<pre>[$€£¥]|(?<![a-z])(?:{_CUR_ALT})(?![a-z]))\s*)?"
    rf"(?<![\d.])(?P<num>\d+(?:\.\d+)?)"
    rf"\s*(?P<mult>(?:{_MULT_ALT})(?![a-z]))?"
    rf"\s*(?P<post>%|[$€£¥]|(?<![a-z])(?:{_CUR_ALT})(?![a-z]))?",
    re.IGNORECASE,
)

# A number, optionally scaled ("200M"), trailed by a word we don't recognise as a
# currency — "500000 FOO", "2000 points", "200,000,000 S" (Sonic). Treated as an
# unreadable amount rather than as bare USD: read as dollars, Sonic's grant topped
# the reward sort at $200M.
_UNKNOWN_UNIT_RE = re.compile(
    rf"\d\s*(?:(?:{_MULT_ALT})\s+)?(?!(?:{_CUR_ALT}|{_MULT_ALT})(?![a-z]))[a-z]{{1,10}}(?![a-z])",
    re.IGNORECASE,
)

_THOUSANDS_SEP_RE = re.compile(r"(?<=\d),(?=\d)")

# Space- and dot-grouped thousands: "10 000 USDC", "1.000.000 USD", "50.000 EUR".
# Without this, the tokenizer read "10.000" as ten-point-zero and the minimum
# reward floor silently dropped real grants.
_SPACE_GROUPED_RE = re.compile(r"(?<=\d)[ \u00a0\u202f](?=\d{3}(?!\d))")
_DOT_GROUPED_RE = re.compile(r"(?<=\d)\.(?=\d{3}(?!\d))")

# A comma with one or two digits behind it is a decimal comma, not a thousands
# separator ("1,5 M" = 1.5 million, not 15 million). Grouped thousands always
# carry exactly three digits.
_DECIMAL_COMMA_RE = re.compile(r"(?<=\d),(?=\d{1,2}(?!\d))")


def _normalize_grouping(text: str) -> str:
    """Rewrite separators so the tokenizer sees one number in the right scale.

    Order matters: decimal commas first, then the three-digit groupings.
    """
    normalized = _DECIMAL_COMMA_RE.sub(".", text)
    normalized = _SPACE_GROUPED_RE.sub("", normalized)
    normalized = _DOT_GROUPED_RE.sub("", normalized)
    return normalized


def parse_amount_usd(text: str | None) -> float | None:
    """Largest USD value stated in `text`, or None when nothing is readable.

    The largest reading wins on purpose: a range ("$1k–$50k") or a tiered pool
    ("$100k total, $2k per winner") is worth its top figure to an applicant.

    A literal zero is not a prize: "$0" and "0" mean "not stated" in practice, so
    they return None (kept by the floor) rather than 0.0 (dropped by the floor).
    """
    if not text:
        return None

    norm = _normalize_grouping(str(text).lower())
    norm = _THOUSANDS_SEP_RE.sub("", norm)

    values = []
    saw_currency = False
    for match in _TOKEN_RE.finditer(norm):
        pre = match.group("pre")
        post = match.group("post")

        if post == "%":  # "top 10%" is a share, not a sum
            continue

        code = pre or post
        if code:
            saw_currency = True
        rate = _USD_RATES.get(code) if code else 1.0
        if rate is None:  # a currency we matched but can't price
            continue

        mult = _MULTIPLIERS[match.group("mult")] if match.group("mult") else 1.0

        number = float(match.group("num"))
        if not code and mult == 1.0 and 1900 <= number <= 2100 and number.is_integer():
            continue  # a bare "2026" is a year, not a prize

        values.append(number * mult * rate)

    if not values:
        return None

    # Bare numbers were read as USD above. If nothing in the string named a
    # currency and some number carries an unrecognised unit, that assumption is
    # unsafe ("500000 FOO tokens") — report unknown instead.
    if not saw_currency and _UNKNOWN_UNIT_RE.search(norm):
        return None

    largest = max(values)
    if largest <= 0:
        # "0", "$0", "0 USD": the model uses these for "amount not stated". The
        # floor must not read them as a prize worth nothing.
        return None
    return largest
