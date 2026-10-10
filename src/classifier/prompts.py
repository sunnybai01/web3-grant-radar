"""LLM prompt templates for classification and structured extraction."""

# ---------------------------------------------------------------------------
# Classification prompt — determine if content is a web3 opportunity
# ---------------------------------------------------------------------------
CLASSIFY_SYSTEM = """You are a Web3 intelligence classifier. Your job is to determine whether a piece of content describes a real funding opportunity and, if so, classify it and extract structured data.

Output a single JSON object with no additional text.

Categories:
- "GRANT": Ecosystem fund, foundation grant, fellowship, RFP, quadratic funding round, retroactive funding, builder program with funding
- "HACKATHON": Hackathon, buildathon, code sprint, game jam, hacker house, demo day, pitch competition
- "NOISE": Not an in-scope opportunity (e.g., bug bounty / security bounty programs, marketing hype, airdrop announcement, general news, NFT mint, token sale)

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

For GRANT/HACKATHON, extract all structured fields below. For NOISE, return only the category."""

CLASSIFY_USER_TEMPLATE = """Analyze this content and determine if it describes a Web3 funding opportunity.

Content title: {title}
Content text:
{content}

Source: {source_name} ({source_type})

Return JSON with these fields:
- category: "GRANT" | "HACKATHON" | "NOISE"
- opportunity_stage: "open" | "upcoming" | "closed" | "results_announced"
- title: a clean, concise title for this opportunity (max 200 chars)
- description: 2-3 sentence summary (max 500 chars)
- start_date: ISO 8601 date when applications/registration opens or the program starts, or null if not found
- deadline: ISO 8601 date or null if not found
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
        "opportunity_stage": {
            "type": "string",
            "enum": ["open", "upcoming", "closed", "results_announced"],
        },
        "title": {"type": "string", "maxLength": 200},
        "description": {"type": "string", "maxLength": 500},
        "start_date": {"type": ["string", "null"]},
        "deadline": {"type": ["string", "null"]},
        "amount": {"type": ["string", "null"]},
        "track": {"type": ["string", "null"]},
        "ecosystem": {"type": ["string", "null"]},
        "application_url": {"type": ["string", "null"]},
        "source_platform": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["category", "title"],
}
