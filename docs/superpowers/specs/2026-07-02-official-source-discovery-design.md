# Official Source Discovery Design

## 1. Context

The chain whitelist now includes approved ecosystems such as Base, Arbitrum, Polygon, and Avalanche in [config/chains.yaml](../../../config/chains.yaml). These chains are currently expanded into dynamic DefiLlama-derived discovery sources, but they still lack a strong official source layer in [config/sources.yaml](../../../config/sources.yaml).

The user preference for the next step is accuracy over coverage. That means the system should add only high-confidence official sources, even if some chains end up with fewer sources than others.

Research across the official surfaces for Base, Arbitrum, Polygon, and Avalanche shows that the chains do not expose a uniform set of pages:

- some provide dedicated grants or builder program pages;
- some expose builder and hackathon activity through official blogs or event hubs;
- bug bounty programs are often official but live on static policy pages or third-party platforms such as Immunefi, HackerOne, or Cantina.

This creates an important distinction between pages that are official and pages that are suitable as recurring event sources.

## 2. Goal

Define the phase-one official source admission policy and first candidate set for four chains:

- `base`
- `arbitrum`
- `polygon`
- `avalanche`

The design should produce a repeatable way to:

- discover official source candidates from known chain domains;
- separate dynamic event surfaces from static informational pages;
- admit only the sources that are operationally stable and semantically useful for the current fetch pipeline;
- avoid forcing every chain to have grant, hackathon, and bounty sources when the official web surface does not support that cleanly.

## 3. Scope

In scope:

- official source discovery policy for Base, Arbitrum, Polygon, and Avalanche;
- admission rules for `rss` and `web_scraper` candidates;
- first candidate source shortlist for grants, hackathons, and bounty-related pages;
- classification of static bounty policy pages that should not be treated like ordinary recurring feeds.

Out of scope:

- implementation of the final `sources.yaml` edits;
- changes to fetcher code;
- UI changes;
- discovery for the remaining approved chains.

## 4. Key Design Decision

Official source discovery must distinguish between two different surface types.

### 4.1 Event-producing sources

These are sources that can realistically generate recurring new opportunity records over time.

Examples:

- official blog feeds;
- official grants program index pages with changing active programs;
- official hackathon or builder-events listing pages;
- governance or forum feeds when they regularly announce funding or builder programs.

These are valid candidates for periodic scanning in the current pipeline.

### 4.2 Static policy sources

These are official pages, but they mostly describe an evergreen program rather than emitting a stream of new events.

Examples:

- Immunefi bounty program pages;
- HackerOne program policy pages;
- vulnerability disclosure documentation pages;
- one-time program explainers without a changing listing surface.

These pages are valuable as trust anchors, but they are poor recurring event sources. They should not be treated the same as blog feeds or live grants listings.

## 5. Admission Rules

Phase one should admit a source only if all of the following are true:

1. The page belongs to an official domain, official documentation surface, or an official third-party program page explicitly linked from official docs.
2. The page is stable enough for periodic polling.
3. The page has a reasonable chance of surfacing new opportunity records over time.
4. The page fits one of the existing fetcher types without major new code.
5. The page is specifically relevant to grant, hackathon, builder program, funding, or bounty opportunity discovery.

A page should be rejected for phase one if any of the following are true:

- it is a dead or access-restricted page;
- it is a generic homepage with no opportunity signal;
- it is static policy documentation that is unlikely to change often enough to justify periodic scanning;
- it requires a new fetch strategy that the repository does not yet support.

## 6. Chain Findings

### 6.1 Base

Confirmed official surfaces:

- `https://blog.base.dev/rss` via the Paragraph-backed Base Engineering Blog;
- `https://paragraph.com/@grants.base.eth/calling-based-builders` as the Base Grants publication and builder grant explainer;
- `https://www.base.org/ecosystem-fund` as the Base Ecosystem Fund surface;
- `https://docs.base.org/base-chain/security/report-vulnerability` as the official vulnerability reporting and bug bounty entry page.

Assessment:

- Base has a strong official grant and builder support surface.
- The engineering blog is a valid recurring source.
- The grants publication is official enough to treat as a phase-one source.
- The bug bounty page is official but behaves like a static policy page, not a recurring event feed.

Phase-one recommendation:

- admit `blog.base.dev/rss` as an official recurring source;
- admit the Base Grants publication as an official recurring grant source if the page or publication feed is stable;
- do not admit the vulnerability reporting page as a recurring source yet.

### 6.2 Arbitrum

Confirmed official surfaces:

- `https://arbitrum.foundation/grants` as an active grants index with multiple programs;
- `https://blog.arbitrum.foundation/` as the official Foundation blog;
- `https://forum.arbitrum.foundation/` as the governance/forum surface;
- `https://immunefi.com/bounty/arbitrum/` linked from official docs as the live bug bounty program.

Assessment:

- Arbitrum has the strongest official source structure among the four chains.
- The grants page is a high-value dynamic source.
- The Foundation blog frequently announces buildathons, founder houses, mentorship cohorts, and bounty challenges.
- The forum is official, but the current evidence only proves broad governance availability, not a clean grant-specific feed path.
- The Immunefi program is official but effectively static as a periodic source.

Phase-one recommendation:

- admit `arbitrum.foundation/grants` as an official grants source;
- admit `blog.arbitrum.foundation` as an official recurring source for hackathons and builder programs;
- defer the forum until an RSS-compatible or reliably scrapable grant-relevant path is identified;
- do not treat the Immunefi page as a recurring source.

### 6.3 Polygon

Confirmed official surfaces:

- `https://polygon.technology/blog` as the official Polygon blog surface;
- `https://docs.polygon.technology/` as the official docs surface;
- `https://immunefi.com/bug-bounty/polygon/information/` as the official bug bounty program page;
- `https://docs.polygon.technology/tools/security/disclosure` is referenced by docs as the security and disclosure surface.

Assessment:

- Polygon exposes a solid official blog, but current evidence does not yet show a clear official grants page or dedicated hackathon hub comparable to Arbitrum or Avalanche.
- The docs are heavily product-oriented and developer-oriented, not obviously opportunity-oriented.
- The bug bounty page is official but static.

Phase-one recommendation:

- admit the Polygon blog surface as the only clear phase-one recurring official source;
- defer grants and hackathon source admission until a stronger official opportunity listing is confirmed;
- do not admit the bug bounty page as a recurring source.

### 6.4 Avalanche

Confirmed official surfaces:

- `https://build.avax.network/grants` as the Builder Hub grants page;
- `https://build.avax.network/hackathons` as the Builder Hub event and hackathon listing;
- `https://www.avax.network/about/blog` as the official Avalanche blog;
- `https://immunefi.com/bug-bounty/avalanche/information/` as the official bug bounty program linked from official build surfaces.

Assessment:

- Avalanche has a well-structured builder hub with dedicated grants and hackathon pages.
- Both grants and hackathons appear suitable for periodic scraping.
- The official blog also contains grant and builder-program announcements.
- The Immunefi bug bounty page is official but mostly static.

Phase-one recommendation:

- admit `build.avax.network/grants` as an official grants source;
- admit `build.avax.network/hackathons` as an official hackathon source;
- admit `www.avax.network/about/blog` as a broader official builder-news source if needed;
- do not treat the Immunefi page as a recurring source.

## 7. Initial Candidate Shortlist

The phase-one shortlist should stay intentionally small.

Recommended recurring official candidates:

- Base
  - `blog.base.dev/rss`
  - Base Grants publication feed or stable grant landing surface
- Arbitrum
  - `arbitrum.foundation/grants`
  - `blog.arbitrum.foundation`
- Polygon
  - `polygon.technology/blog`
- Avalanche
  - `build.avax.network/grants`
  - `build.avax.network/hackathons`
  - `www.avax.network/about/blog`

Recommended official-but-static references, not recurring sources:

- Base vulnerability reporting / HackerOne / Cantina page
- Arbitrum Immunefi page
- Polygon Immunefi page
- Avalanche Immunefi page

## 8. Source Modeling Guidance

Phase one should avoid pretending that every opportunity type has the same source shape.

Recommended modeling:

- grants: prefer dedicated grants indexes and official grant publications;
- hackathons: prefer builder event hubs and official program blogs;
- bounties: prefer dynamic challenge announcements when they exist, not evergreen policy pages.

This means some chains will not receive a bounty source in phase one, even though they do have an official bounty program. That is acceptable and preferable to creating noisy, low-yield scans.

## 9. Phase-One Implementation Plan

Once implementation begins, the change should proceed in this order:

1. Add the smallest validated official source subset for the four chains to `config/sources.yaml`.
2. Keep all newly added sources disabled by default until a runtime validation pass is complete.
3. Run a focused fetch validation against only the newly added official sources.
4. Enable only the sources that return stable content and meaningful opportunity signals.
5. Leave static bounty policy pages out of recurring scanning unless a separate static-program catalog is introduced later.

## 10. Open Follow-Up

Two follow-ups are likely after phase one:

- add a dedicated static-program catalog for evergreen security bounty programs;
- build a semi-automated official domain discovery process for the next approved chains.

Both are useful, but neither is required before the first official source rollout.
