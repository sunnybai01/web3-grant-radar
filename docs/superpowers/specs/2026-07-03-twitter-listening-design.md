# Twitter Listening Design

## 1. Context

The repository already has a complete post-ingestion opportunity pipeline in [src/main.py](../../../src/main.py): fetch, URL deduplication, semantic deduplication, classification, verification, scoring, Slack push, and Markdown reporting.

Twitter/X is already represented in the source model, but the current implementation depends on RSSHub in [src/fetchers/twitter_fetcher.py](../../../src/fetchers/twitter_fetcher.py) and is disabled in [config/sources.yaml](../../../config/sources.yaml) because the upstream route is no longer stable.

The project goal is not broad social listening. The goal is targeted Web3 opportunity discovery: grants, hackathons, builder programs, bounty announcements, and adjacent early discovery signals that are still close enough to structured opportunities to fit the existing pipeline.

The user clarified four design constraints:

- the target mode is semi-discovery rather than official-only or full-firehose monitoring;
- polling should be medium frequency rather than near-real-time;
- cookie or session based access is acceptable instead of requiring the official Twitter API;
- official accounts and discovery accounts should not share the same ingestion path.

## 2. Goal

Design a Twitter/X listening architecture that restores social-source coverage for the repository while preserving the quality bar of the existing opportunity pipeline.

The design must:

- replace the broken RSSHub dependency with a production-capable Twitter ingestion approach;
- separate high-trust official Twitter sources from noisier discovery sources;
- prevent discovery noise from overwhelming Slack pushes and downstream verification;
- reuse the repository's existing classification, verification, scoring, and reporting flow wherever possible;
- define the role of MCP-based tools without making them a production dependency.

## 3. Scope

In scope:

- production Twitter ingestion strategy;
- source modeling for official accounts, KOL accounts, and Twitter Lists;
- preprocessing rules for discovery sources;
- scheduler behavior for a dedicated social watch pipeline;
- alerting and throttling policy for Twitter-derived opportunities;
- MCP positioning for analyst workflows.

Out of scope:

- implementation code;
- migration of all existing source configuration entries;
- building a full social graph or sentiment platform;
- using the official Twitter API as the primary source of truth;
- UI redesign for the dashboard.

## 4. Recommended Approach

The recommended production approach is:

- use Twikit as the primary Twitter ingestion layer;
- introduce a dedicated `social_watch` schedule;
- send official Twitter sources directly into the existing main pipeline;
- send discovery Twitter sources through a lightweight social preprocessing layer before they reach the main pipeline;
- keep MCP-based Twitter tools as an analyst sidecar, not as a production ingestion dependency.

This is a two-lane ingestion model rather than a single undifferentiated Twitter feed.

## 5. Architecture Overview

The design adds a Twitter-specific ingestion branch ahead of the existing event-processing core.

### 5.1 Official lane

Official foundation, grant program, builder program, hackathon organizer, and bounty platform accounts are treated as higher-trust social sources.

Flow:

1. Twikit fetches recent tweets for approved official accounts.
2. Tweets are normalized into the repository's `FetchedItem` model.
3. The items enter the existing fetch-to-event pipeline directly.
4. Classification, verification, scoring, and Slack dispatch continue unchanged.

This lane behaves like a social equivalent of an official blog feed or official grants page.

### 5.2 Discovery lane

KOL accounts, researchers, scientists, and curated Twitter Lists are treated as discovery sources.

Flow:

1. Twikit fetches recent tweets for approved discovery accounts or Lists.
2. Raw tweets enter a `SocialPreprocessor`.
3. The preprocessor drops obvious noise and upgrades only candidate opportunity signals.
4. Surviving items are adapted into `FetchedItem` records.
5. Those records enter the existing main pipeline.

This lane exists to stop high-volume discovery chatter from directly hitting classification and Slack.

## 6. Source Modeling

Twitter sources should not be represented with only `enabled` and `fetch_method`. They need source-level social metadata so the scheduler and preprocessor can apply different behavior.

Recommended source metadata fields:

- `source_kind`: `account` or `list`
- `trust_tier`: `official` or `discovery`
- `ingestion_mode`: `direct` or `preprocessed`
- `watch_priority`: `high`, `normal`, or `low`
- `schedule`: `social_watch`
- `signal_type`: `social`
- `official`: boolean trust hint carried into verification

### 6.1 Official social sources

Examples:

- ecosystem foundations;
- grant program accounts;
- hackathon operators;
- bounty platforms such as Immunefi when the account itself regularly announces specific opportunities.

Rules:

- official accounts use `ingestion_mode=direct`;
- they enter the main pipeline without discovery preprocessing;
- they still go through downstream classification and verification;
- they are marked as higher-trust origins but not auto-verified.

### 6.2 Discovery social sources

Examples:

- KOLs;
- researchers;
- smart-money style accounts;
- curated Twitter Lists built from those sources.

Rules:

- discovery accounts use `ingestion_mode=preprocessed`;
- they never bypass the social preprocessor;
- Lists default to discovery even if they contain official accounts;
- discovery origin alone must not be enough to trigger direct Slack pushes.

## 7. Component Design

The Twitter integration should be split into focused units instead of one large fetcher with embedded heuristics.

### 7.1 `TwikitFetcher`

Responsibility: reliable Twitter retrieval.

It should handle:

- authenticated session or cookie reuse;
- account timeline fetches;
- Twitter List timeline fetches;
- pagination and incremental polling;
- retry and cooldown behavior;
- basic tweet normalization.

It should not contain opportunity heuristics, Slack logic, or LLM prompting.

### 7.2 `TwitterSourceRegistry`

Responsibility: define and validate the monitored Twitter pool.

It should provide:

- source membership by trust tier;
- source kind validation for account versus List;
- watch priority metadata;
- a single source of truth for Twitter-specific configuration.

### 7.3 `SocialPreprocessor`

Responsibility: isolate discovery-lane noise before it contaminates the main pipeline.

It should perform four classes of work:

1. Noise suppression
   - drop daily chatter, memes, pure market commentary, and obviously irrelevant posts.
2. Opportunity trigger extraction
   - detect cues such as `grant`, `hackathon`, `bounty`, `builder program`, `RFP`, `apply`, `registration`, `deadline`, `prize pool`, `security disclosure`, and similar patterns.
3. Structural enrichment
   - inspect outbound links, author identity, quoted tweet context, and the presence of actionable details.
4. Candidate verdict
   - emit `drop`, `candidate`, or `strong_candidate`.

Only `candidate` and `strong_candidate` records continue into the main pipeline.

### 7.4 `TwitterSignalAdapter`

Responsibility: convert a tweet and its surrounding context into an input shape that the existing classifier can interpret correctly.

The adapter should combine:

- author handle;
- tweet text;
- quoted tweet text when present;
- outbound link URL and domain;
- outbound card title when available;
- source type information such as account or List origin.

This avoids passing under-contextualized tweet text directly into the classifier.

## 8. Scheduler Design

Twitter should run on a dedicated schedule rather than reusing `grant_hackathon` or `bounty` in [src/scheduler/jobs.py](../../../src/scheduler/jobs.py).

Recommended schedule:

- primary job: `social_watch`
- default polling interval: every 15 minutes

Priority guidance:

- high-priority official accounts may run every 10 minutes;
- discovery Lists may run every 20 to 30 minutes;
- all Twitter polling remains medium-frequency rather than near-real-time.

Rationale:

- social sources have different freshness expectations from blogs and RSS feeds;
- failures should be isolated from the main grant and bounty schedules;
- the scheduler should be able to tune official and discovery sources differently.

## 9. Incremental State and Health

Twitter ingestion requires explicit source state. Full rescans every cycle are the wrong operating model.

Each Twitter source should persist at least:

- `last_tweet_id`
- `last_fetched_at`
- `consecutive_failures`
- `cooldown_until`
- `auth_profile`

Health behavior should mirror the repository's source-health mindset but remain isolated to the social branch:

- repeated failures should trigger cooldown;
- authentication failures should degrade only the Twitter branch;
- login challenges or rate-limit responses should not mark unrelated non-Twitter sources as unhealthy.

## 10. Slack and Reporting Policy

Slack behavior must differ between official and discovery lanes.

### 10.1 Official social pushes

An official Twitter-derived item may generate a normal Slack card if it:

- survives classification;
- passes verification without fraud classification;
- produces a sufficiently structured opportunity object.

### 10.2 Discovery social pushes

A discovery Twitter-derived item should generate a Slack card only if at least one of the following is true:

1. it contains a direct link to an approved official domain and strongly matches an opportunity pattern;
2. two or more independent discovery sources mention the same opportunity within a recent window such as 6 to 12 hours;
3. classification confidence is high and at least one core actionable field such as deadline, amount, or application URL is extracted.

Discovery items that fail the push threshold should still be retained for:

- report-only visibility;
- later cross-reference;
- operator review;
- possible source-pool tuning.

This keeps discovery useful without turning Slack into a noisy tweet stream.

## 11. Verification Strategy

Twitter does not change the core verification model, but it changes how source trust should be interpreted.

### 11.1 Official sources

Official Twitter sources should be treated as higher-confidence origins. They may receive the same trust uplift already modeled through `source_tier` and `official` in [src/verifier/verifier.py](../../../src/verifier/verifier.py).

However, official origin must not imply that every tweet is itself an opportunity. The content still requires classification and downstream checks.

### 11.2 Discovery sources

Discovery Twitter sources start as low-trust origins. They become more credible only when supported by evidence such as:

- links to approved official domains;
- extraction of explicit opportunity details;
- corroboration across multiple independent sources.

This preserves the repository's existing zero-trust posture.

## 12. MCP Role

MCP-based Twitter tooling is useful, but it should not be part of the production ingestion critical path.

Recommended MCP use cases:

1. Analyst deep-dive on a candidate tweet or thread.
2. Batch summary of a monitored List over the last 12 to 24 hours.
3. Discovery research for identifying new candidate accounts to add to the source registry.

MCP should not be responsible for:

- scheduled production polling;
- source-of-record ingestion;
- durable cursor management;
- critical-path Slack delivery.

This keeps production reliability independent from an interactive AI client session.

## 13. Operational Risks

The main operational risks are:

- session invalidation or login challenge;
- rate-limiting on aggressive polling;
- noisy discovery accounts overwhelming the candidate pool;
- under-contextualized tweets producing false positives;
- drift between monitored sources and actual high-signal Web3 accounts.

Mitigations:

- medium-frequency polling rather than aggressive near-real-time loops;
- explicit cooldown behavior;
- source registry review and pruning;
- a strict preprocessor barrier for discovery sources;
- keeping official and discovery ingestion modes separate.

## 14. Acceptance Criteria

The design is successful if implementation yields all of the following:

1. Twitter coverage is restored without depending on RSSHub.
2. Official Twitter accounts can produce candidate opportunities within 10 to 30 minutes of publication.
3. Discovery Twitter inputs do not spam Slack directly.
4. The existing main opportunity pipeline remains the single downstream path for classification, verification, scoring, and reporting.
5. Source health and event quality can be compared separately for official and discovery Twitter sources.

## 15. Phased Rollout

Recommended rollout order:

1. Implement Twikit-backed official account ingestion only.
2. Validate cursoring, health tracking, and direct main-pipeline integration.
3. Add the social schedule and isolate failures from other source schedules.
4. Introduce discovery accounts behind the preprocessor.
5. Add Twitter Lists only after account-level discovery behavior is stable.
6. Add MCP-assisted analyst workflows as a separate optional capability.

This sequence reduces the risk of mixing retrieval risk and noise-control risk in the same release.

## 16. Decision Summary

This design recommends a Twikit-based, two-lane Twitter listening system:

- official accounts use direct ingestion into the current pipeline;
- discovery accounts and Lists use a preprocessing gate before entering the current pipeline;
- `social_watch` runs independently from the existing grant and bounty schedules;
- MCP remains an analyst sidecar rather than a production dependency.

This is the smallest architecture that restores Twitter coverage, respects the repository's current trust model, and avoids turning the social branch into a separate platform too early.
