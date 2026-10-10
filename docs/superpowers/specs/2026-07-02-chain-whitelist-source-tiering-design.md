# Chain Whitelist And Source Tiering Design

## 1. Context

The current source system is configured as a flat list in [config/sources.yaml](../../../config/sources.yaml). Official feeds, website scrapers, RSSHub Twitter bridges, GitHub label searches, and Tavily discovery queries all enter the same pipeline at the same level.

This creates two problems:

- operational instability: several fetch methods are inherently fragile or rate-limited, especially RSSHub, broad GitHub search, and web discovery queries;
- weak trust separation: high-signal official opportunity sources are mixed with low-signal discovery sources, so downstream verification and scoring start from the same baseline even when source quality is very different.

The desired direction is to monitor Web3 opportunities primarily from chain ecosystems themselves: chain websites, foundation blogs, official grants and hackathon pages, governance forums, and a small set of official social accounts. Auxiliary discovery sources should remain available for recall, but should no longer dominate the main pipeline.

DefiLlama can provide the initial candidate universe through its public chains API, which returns chain-level metadata such as name, TVL, token symbol, and chain ID. That API is useful for seed generation, but it should not directly decide the production whitelist without an additional review layer.

## 2. Goal

Restructure source management around a whitelist of monitored chains and a tiered source model:

- define a curated Top 50 chain whitelist derived from DefiLlama, filtered to chains with meaningful ecosystem incentive activity;
- attach a standard official source set to each selected chain;
- downgrade GitHub, RSSHub, and Tavily to auxiliary discovery sources;
- use DefiLlama API results to refresh the candidate chain pool without automatically promoting every ranked chain into production monitoring;
- allow downstream verification, scoring, and reporting to distinguish officially confirmed opportunities from unconfirmed discovery candidates.

This design improves precision without removing controlled recall.

## 3. Scope

In scope:

- chain whitelist configuration model;
- source registry split between official and discovery sources;
- metadata additions required for trust-aware processing;
- pipeline behavior changes for official vs discovery sources;
- reporting and output behavior changes;
- migration path from the current flat source list.

Out of scope:

- full automatic source generation from DefiLlama;
- Discord real-time listener design changes;
- Copilot UI changes;
- immediate expansion to every ecosystem social platform.

## 4. DefiLlama Seed Strategy

The approved operating mode is a hybrid model:

- DefiLlama API is the upstream source of candidate chains;
- the system periodically refreshes a candidate list from DefiLlama;
- only reviewed and approved chains enter the production whitelist in `config/chains.yaml`.

This keeps the monitored universe current without letting TVL movements or noisy chain listings rewrite monitoring scope automatically.

### 4.1 API role

The DefiLlama chains API should be treated as a seed feed, not as the final registry of truth.

Useful fields from the API include:

- `name`
- `tvl`
- `chainId`
- `gecko_id`
- `tokenSymbol`

These fields are sufficient to:

- generate an initial ranked candidate set;
- map known chains back to a stable external reference;
- detect newly relevant ecosystems for operator review.

### 4.2 Sync policy

Recommended cadence:

- refresh candidate chains daily or weekly;
- compute a ranked candidate snapshot from DefiLlama;
- compare it against the approved local chain registry;
- surface additions, removals, and large ranking changes for review.

The sync must not directly mutate the approved whitelist without an explicit approval step.

### 4.3 Approval workflow

The workflow should separate discovery from activation:

1. Pull candidate chains from DefiLlama API.
2. Filter obvious non-target entries using policy rules.
3. Mark unmatched or changed candidates as `pending_review`.
4. Approve selected candidates into the production chain registry.
5. Attach official sources only after approval.

This preserves operator control while still reducing manual research cost.

## 5. Chain Selection Policy

The monitored chain universe starts from a large DefiLlama-based list with a target size around 50, but inclusion is not purely rank-based.

Chains are included when they satisfy the following policy:

- they are L1s or major L2s with active ecosystem development;
- they have a credible official surface for opportunity publication, such as a foundation, official blog, grants page, hackathon page, or governance forum;
- they plausibly publish opportunities relevant to builders, researchers, or bounty hunters.

Chains are excluded when they are high TVL but low opportunity signal, purely application-like, or lack identifiable official opportunity surfaces.

This produces a curated Top 50-style whitelist rather than a blind top-50 import.

## 6. Configuration Model

The source system should move from one flat file toward two layers of configuration.

### 6.1 Chain registry

Create a dedicated chain registry file, for example `config/chains.yaml`, with one record per monitored chain.

Suggested fields:

- `chain_id`: internal stable identifier, such as `ethereum`, `solana`, `sui`;
- `name`: display name;
- `defillama_slug`: optional mapping back to DefiLlama;
- `defillama_name`: exact upstream chain name when it differs from internal naming;
- `defillama_chain_id`: optional numeric chain ID from DefiLlama payload;
- `seed_tvl`: last observed TVL from the seed sync, used for ranking and review only;
- `category`: `l1` or `l2`;
- `priority`: numeric or categorical ranking for operational focus;
- `review_status`: `approved`, `pending_review`, or `rejected`;
- `review_notes`: optional operator rationale for approval or exclusion;
- `enabled`: whether the chain is currently in scope.

The chain registry becomes the authoritative list of monitored ecosystems.

### 6.2 Source registry

Replace the single undifferentiated source list with source records that explicitly identify their chain and trust tier.

Suggested fields added to each source:

- `chain`: links the source to a chain in the chain registry;
- `source_tier`: `official` or `discovery`;
- `signal_type`: `blog`, `grants`, `hackathon`, `governance`, `social`, `bounty`, or `discovery`;
- `official`: boolean convenience flag;
- `enabled`: unchanged operational switch.

The source registry may be split into:

- `config/sources.official.yaml`
- `config/sources.discovery.yaml`

or represented as one file with clear tier metadata. The split-file approach is preferred because it makes operator intent obvious and prevents accidental mixing.

## 7. Standard Official Source Set Per Chain

Each included chain should attempt to populate a standard set of official surfaces. The chosen default set is:

- official website or blog;
- foundation or ecosystem fund surface;
- grants page;
- hackathon page;
- governance forum;
- official X account.

Not every chain will have every surface. Missing surfaces are acceptable, but the chain should still have enough official presence to justify inclusion in the whitelist.

Priority order for collection:

1. RSS or Atom feeds from official blog or announcement surfaces.
2. Stable official webpages suitable for targeted scraping.
3. Governance forum RSS feeds where available.
4. Official social accounts, treated as official but lower confidence than a first-party site unless later corroborated.

## 8. Discovery Source Policy

GitHub search, RSSHub, and Tavily remain in the system, but no longer define the main monitoring surface.

Their role changes to auxiliary discovery only:

- they can surface candidate opportunities that may not yet be present in official feeds;
- they cannot, by themselves, justify high-confidence output;
- they should be processed after or separately from official sources;
- they should be explicitly labeled as discovery-origin records.

This preserves recall while reducing false confidence.

## 9. Pipeline Behavior Changes

The fetch stage should stop treating all enabled sources as operationally equivalent.

### 9.1 Fetch ordering

Preferred behavior:

- run `official` sources as the primary collection set;
- run `discovery` sources as a secondary collection set;
- maintain per-tier fetch health so instability in discovery sources does not appear equivalent to official source failures.

### 9.2 Record metadata

Each fetched item should carry forward:

- `chain`
- `source_tier`
- `signal_type`
- `official`

These fields must survive through deduplication, classification, verification, scoring, and reporting.

### 9.3 Classification and candidate state

Discovery-origin records that look relevant but lack confirmation should be allowed into a candidate state rather than being treated as fully verified opportunities.

Suggested states:

- `official_confirmed`
- `discovered_unconfirmed`
- `rejected_noise`
- `rejected_fraud`

## 10. Verification And Scoring Policy

The trust improvement depends on downstream logic using the new source-tier metadata.

### 10.1 Origin trust

Verification should assign a higher initial origin-trust value to official first-party sources:

- chain website, foundation blog, grants page, hackathon page, governance forum;
- official social accounts only slightly lower than first-party websites.

Discovery sources start from a lower origin-trust baseline.

### 10.2 Cross-confirmation rule

A discovery-origin record should not receive a high-confidence verdict unless it is corroborated by at least one official source, or another equally strong official signal.

Examples:

- a tweet from RSSHub mentioning a grant is only high-confidence once matched to an official grants page, blog post, or governance announcement;
- a GitHub issue labeled `bounty` may remain a valid candidate, but should not be elevated to top-trust unless corroborated by an official program surface.

### 10.3 Score ceiling

Unconfirmed discovery-origin records should have a ceiling that prevents them from appearing as top-confidence opportunities.

This can be implemented as either:

- a hard score cap; or
- a verdict cap that prevents `trusted` status without official corroboration.

### 10.4 Reporting semantics

Final outputs should separate:

- officially confirmed opportunities;
- discovered but unconfirmed candidates.

This distinction should appear in generated reports and Slack output.

## 11. Operational Guidance

### 11.1 Reliability priorities

Preferred fetch methods by stability:

1. official RSS or Atom feeds;
2. stable official webpages with targeted scraping;
3. governance RSS feeds;
4. official social accounts via bridge or other adapter;
5. discovery search sources.

### 11.2 Failure interpretation

Source-health monitoring should distinguish between:

- `official source degraded`: higher operational priority;
- `discovery source degraded`: lower priority unless recall is suffering materially.

### 11.3 Maintenance model

Operators should maintain sources chain-by-chain, not source-type-by-source-type.

This means the maintenance question becomes:

- “What are the official opportunity surfaces for Sui?”

instead of:

- “What RSS feeds do we have globally?”

That framing better matches how Web3 opportunities are actually published.

## 12. Migration Plan

The migration should be incremental.

Phase 1:

- introduce chain and tier metadata into the existing source config;
- add a DefiLlama seed importer that writes candidate chain snapshots for review;
- mark current official sources and discovery sources;
- keep runtime behavior mostly unchanged.

Phase 2:

- add a dedicated chain registry;
- formalize `pending_review` versus `approved` chain states;
- split official and discovery source definitions;
- update fetch orchestration to run official sources first and record per-tier health.

Phase 3:

- update verification and scoring to use source-tier metadata;
- add report separation for confirmed vs unconfirmed opportunities.

Phase 4:

- prune or replace weak discovery sources that do not contribute useful candidates;
- expand chain-by-chain official coverage within the curated whitelist.

## 13. Acceptance Criteria

The redesign is successful when:

- monitored ecosystems are represented explicitly as a curated chain whitelist;
- DefiLlama API is used as a repeatable seed source for candidate chains;
- no chain is auto-enabled for production monitoring without approval;
- every source is attached to a chain and tagged as `official` or `discovery`;
- official sources are the main monitoring path;
- GitHub, RSSHub, and Tavily are retained only as auxiliary discovery inputs;
- verification and scoring distinguish official confirmation from unconfirmed discovery;
- final outputs clearly separate confirmed opportunities from candidates.
