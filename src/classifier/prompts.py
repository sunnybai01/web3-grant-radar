"""LLM prompt templates for classification and structured extraction."""
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# The team works in Asia/Shanghai; "today" in every prompt is that calendar day.
PROMPT_TIMEZONE = ZoneInfo("Asia/Shanghai")


def current_date_label(now: Optional[datetime] = None) -> str:
    """Today's date (Asia/Shanghai) as YYYY-MM-DD, for prompts that judge time."""
    return (now or datetime.now(PROMPT_TIMEZONE)).astimezone(PROMPT_TIMEZONE).date().isoformat()


# ---------------------------------------------------------------------------
# Classification prompt — determine if content is a web3 opportunity
# ---------------------------------------------------------------------------
CLASSIFY_SYSTEM = """You are a Web3 intelligence classifier. Your job is to determine whether a piece of content describes a real funding opportunity and, if so, classify it and extract structured data.

Output a single JSON object with no additional text.

Categories:
- "GRANT": Ecosystem fund, foundation grant, fellowship, RFP, quadratic funding round, retroactive funding, builder program with funding
- "HACKATHON": Hackathon, buildathon, code sprint, game jam, hacker house, prize competition that anyone can enter by building
- "NOISE": Not an in-scope opportunity (e.g., bug bounty / security bounty programs, marketing hype, airdrop announcement, general news, NFT mint, token sale)

The reader is a builder looking for money they can still apply for or compete for. Content that
mentions grants or hackathons is still NOISE when it offers the reader nothing to apply to:
- third_party_application: a specific team's own application, proposal, grant request, progress
  report or project introduction ("[Builder Grant Proposal] X", "Grant Application: X",
  "we are requesting 10,000 OP for our project"). Someone else asking for money is not a call.
- roundup: a roundup, digest, listicle or guide covering many programs ("Top 15 grants",
  "10+ funding programs", "weekly digest", "hackathons to watch"). The programs it lists may be
  opportunities; the roundup itself is not.
- funding_news: a company or project raised money, a foundation committed or allocated a budget,
  or a fund was launched, with no open call where builders can apply.
- non_building_event: a conference, summit, meetup, AMA, demo day or pitch day where
  pre-selected teams present. Attending or watching wins the reader nothing.
- non_cash_reward: the only reward is service credits (Dune, API, cloud or gas credits),
  discounts, swag, points or perks rather than money or tokens, even when the content says "apply".
- general_news: an ecosystem news update, newsletter issue or weekly recap that mentions programs
  in passing. If it announces an open call with cash or token rewards, classify that program
  instead and title it after the program.

Separately from the category, judge whether a reader could still act on this today.
Report it as opportunity_stage:
- "open": applications/registration are open right now, or the program accepts submissions on a rolling basis
- "upcoming": announced but not yet open; a future start date is stated or implied
- "closed": the application or registration window has already passed
- "results_announced": this reports an outcome, not a call for participants — winners, finalists,
  selected teams, a concluded round, or a grant already awarded to a named recipient

Judge the stage from what the content actually says, not from the category. Content that reads
like "X has approved a grant for <specific project>", "top N finalists announced", or "the round
has concluded" is "results_announced" even when it is clearly about a grant or hackathon.

Judge time against today's date and the publication date given with the content. A window is
open through its stated deadline day and "closed" only once that day has passed. A dated round, cohort or event announced long before today
with no sign that it is still running is "closed", not "open". A date written without a year
refers to its nearest occurrence after the publication date (or after today when the
publication date is unknown); output it with that year.

For GRANT/HACKATHON, extract all structured fields below. For NOISE, return only the category
and the noise_reason."""

CLASSIFY_USER_TEMPLATE = """Analyze this content and determine if it describes a Web3 funding opportunity.

Today's date: {today}
Published: {published}
Content title: {title}
Content text:
{content}

Source: {source_name} ({source_type})

Return JSON with these fields:
- category: "GRANT" | "HACKATHON" | "NOISE"
- noise_reason: for NOISE only, one of "third_party_application" | "roundup" | "funding_news" |
  "non_building_event" | "non_cash_reward" | "general_news" | "other"; null otherwise
- opportunity_stage: "open" | "upcoming" | "closed" | "results_announced"
- title: a clean, concise title for this opportunity (max 200 chars)
- description: 2-3 sentence summary (max 500 chars)
- start_date: ISO 8601 date when applications/registration opens or the program starts, or null if not found
- deadline: ISO 8601 date or null if not found
- is_rolling: true only if the content explicitly says applications are accepted on a rolling or
  ongoing basis with no fixed window; otherwise false
- amount: the prize/funding amount (e.g. "$50,000", "5 ETH", "Up to $100k") or null
- track: the focus area (e.g. "DeFi", "Security", "Infrastructure", "ZK", "AI", "Gaming") or null
- ecosystem: the blockchain ecosystem (e.g. "ethereum", "solana", "sui", "stellar", "polygon") or null
- application_url: direct link to apply or null
- source_platform: the platform name (e.g. "immunefi", "gitcoin", "ethglobal", "dorahacks") or null
- confidence: 0.0 to 1.0 how confident you are in this classification"""

# ---------------------------------------------------------------------------
# Scoring prompt — evaluate the commercial value of a verified opportunity
# ---------------------------------------------------------------------------
SCORE_SYSTEM = """You are a Web3 investment analyst. Evaluate the commercial value of a verified funding opportunity across four dimensions. Output a single JSON object.

Scoring scale: 1-10 for each dimension. Be strict — most opportunities should score 5-7. Only truly exceptional opportunities score 9-10.

Source trust context matters: opportunities published on approved official ecosystem sources deserve higher reputation confidence than items discovered only through aggregators or social discovery feeds.

Dimensions:
1. ROI (40% weight): How lucrative is this? $30k+ grants, $200k+ hackathon prize pools, or $120+/hr equivalent bounties score high. Low-pay, high-effort tasks score low.
2. Reputation (30% weight): Is the sponsor a top-tier L1/L2 foundation or blue-chip protocol (Ethereum, Solana, Base, Uniswap, Aave)? Anonymous teams with no backing score low.
3. Timeliness (20% weight): How much time remains? 2-3 weeks = ideal golden window. < 24 hours left or already expired = very low. Bounties posted within 24 hours = high.
4. Strategy (10% weight): Does this open doors to further ecosystem work, core dev communities, or KOL exposure? One-off isolated tasks score low."""

SCORE_USER_TEMPLATE = """Score this Web3 opportunity:

Today's date: {today}
Category: {category}
Title: {title}
Description: {description}
Deadline: {deadline}
Amount: {amount}
Ecosystem: {ecosystem}
Track: {track}
Platform: {platform}
Source tier: {source_tier}
Official source: {official}
Verification verdict: {verification_verdict}

Return JSON:
{{
  "score_roi": <1-10>,
  "score_reputation": <1-10>,
  "score_timeliness": <1-10>,
  "score_strategy": <1-10>,
  "rationale": "<2-3 sentence explanation>"}}"""

# ---------------------------------------------------------------------------
# Extraction schema — the combined classify+extract output format
# ---------------------------------------------------------------------------
EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": ["GRANT", "HACKATHON", "NOISE"],
        },
        "noise_reason": {
            "type": ["string", "null"],
            "enum": [
                "third_party_application", "roundup", "funding_news",
                "non_building_event", "non_cash_reward", "general_news", "other", None,
            ],
        },
        "opportunity_stage": {
            "type": "string",
            "enum": ["open", "upcoming", "closed", "results_announced"],
        },
        "title": {"type": "string", "maxLength": 200},
        "description": {"type": "string", "maxLength": 500},
        "start_date": {"type": ["string", "null"]},
        "deadline": {"type": ["string", "null"]},
        "is_rolling": {"type": "boolean"},
        "amount": {"type": ["string", "null"]},
        "track": {"type": ["string", "null"]},
        "ecosystem": {"type": ["string", "null"]},
        "application_url": {"type": ["string", "null"]},
        "source_platform": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["category", "title"],
}
