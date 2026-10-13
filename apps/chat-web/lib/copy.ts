/**
 * Every user-facing string in one place. Buttons are verb-first sentence case;
 * explanatory text says what happens and what it costs.
 */
export const copy = {
  brand: "Web3 Grant Radar",
  nav: { triage: "Triage", operations: "Operations" },

  scan: {
    run: "Run scan",
    starting: "Starting scan",
    running: (stage: string) => `Scanning · ${stage}`,
    lastRun: (when: string, newCount: number) => `Last scan ${when} · ${newCount} new`,
    neverRun: "No scan yet",
    started: "Scan started",
    finished: (newCount: number) => `Scan finished · ${newCount} new`,
    failed: "Scan failed",
    review: "Review",
  },

  triage: {
    eyebrow: "Daily triage",
    title: "Opportunities",
    description: "Review what the radar found. Shortlist what the team should pursue; dismiss the rest.",
    stats: {
      toReview: "To review",
      shortlisted: "Shortlisted",
      closingSoon: "Closing ≤ 7d",
      verified: "Verified",
    },
    tabs: { new: "New", shortlisted: "Shortlisted", dismissed: "Dismissed", all: "All" },
    listLabel: "Opportunity status",
    searchPlaceholder: "Search title or chain",
    filters: {
      type: "Type",
      source: "Source",
      chain: "Chain",
      sort: "Sort",
      all: "All",
      grant: "Grant",
      hackathon: "Hackathon",
      official: "Official",
      discovery: "Discovery",
      score: "Score",
      deadline: "Deadline",
      newest: "Newest",
      reward: "Reward",
      closingSoon: "Closing ≤ 7d",
      clear: "Clear filters",
    },
    newArrivals: (count: number) =>
      `${count} new ${count === 1 ? "opportunity" : "opportunities"} since you opened this list`,
    showNew: "Show",
    shortcuts: {
      move: "move",
      shortlist: "shortlist",
      dismiss: "dismiss",
      undo: "undo",
      open: "open",
      search: "search",
    },
    empty: {
      newCaughtUp: "You're all caught up.",
      nextScan: (time: string) => `Next scheduled scan at ${time}.`,
      shortlisted: "Nothing shortlisted yet. Press S on an opportunity to keep it here.",
      dismissed: "Nothing dismissed.",
      filtered: "Nothing matches these filters.",
    },
    loadError: "Couldn't load opportunities",
    retry: "Retry",
    selectPrompt: "Select an opportunity to see its details.",
  },

  detail: {
    firstSeen: (date: string) => `first seen ${date}`,
    officialSource: "Official source",
    discoverySource: "Discovery source",
    facts: {
      amount: "Amount",
      deadline: "Deadline",
      score: "Score",
      verification: "Verification",
      seenIn: "Seen in",
      heat: "Heat",
    },
    seenIn: (count: number) => `${count} ${count === 1 ? "source" : "sources"}`,
    heat: (count: number) => `×${count} ${count === 1 ? "mention" : "mentions"}`,
    actions: {
      shortlist: "Shortlist",
      shortlisted: "Shortlisted",
      dismiss: "Dismiss",
      openApply: "Open apply page",
      openSource: "Open source",
      moveToNew: "Move back to New",
      more: "More actions",
      delete: "Delete…",
    },
    tabs: { overview: "Overview", verification: "Verification", copilot: "Ask Copilot" },
    overview: {
      summary: "Summary",
      noDescription: "No description was extracted for this opportunity.",
      scores: "Score breakdown",
      roi: "ROI",
      reputation: "Reputation",
      timeliness: "Timeliness",
      strategy: "Strategy",
      sources: "Sources",
      noSources: "No source records were kept for this opportunity.",
    },
    loadError: "Couldn't load this opportunity",
  },

  toasts: {
    shortlisted: (title: string) => `Shortlisted “${title}”`,
    dismissed: (title: string) => `Dismissed “${title}”`,
    movedToNew: (title: string) => `Moved “${title}” back to New`,
    undo: "Undo",
    undone: "Undone",
    triageFailed: "Couldn't save that decision. Nothing was changed.",
    deleted: (title: string) => `Deleted “${title}”`,
    deleteFailed: "Couldn't delete the opportunity.",
  },

  deleteDialog: {
    title: "Delete this opportunity?",
    body:
      "It is removed from the database together with its dedup traces, so a later scan can surface it again as new. Dismiss it instead if you only want it out of the way.",
    confirm: "Delete opportunity",
    cancel: "Cancel",
  },

  verification: {
    intro:
      "Checks the opportunity against the database and the web: trust score, evidence, open questions, similar past events and ways to take part.",
    run: "Run verification",
    rerun: "Run again",
    running: "Verifying this opportunity…",
    failed: "Verification failed",
    confidence: "Confidence",
    level: "Level",
    verdict: "Verdict",
    evidence: "Key evidence",
    noEvidence: "No evidence items were returned.",
    unknowns: "Unknowns",
    noUnknowns: "No open questions reported.",
    conflicts: "Conflicts",
    noConflicts: "No conflicting facts detected.",
    paths: "Ways to take part",
    investigation: "Investigation",
    investigationFailed: "Investigation failed",
    recommended: "Recommended action",
    similar: "Similar past events",
    noSimilar: "No near-duplicates in history.",
    similarity: (value: number) => `similarity ${value.toFixed(2)}`,
    evidencePage: "Supporting page",
    noEvidencePage: "No supporting page was captured.",
    steps: "Investigation steps",
    stepInput: "Input",
    stepObservation: "Observation",
    noSteps: "No steps were recorded.",
  },

  copilot: {
    asking: (id: number) => `Asking about #${id}`,
    title: "Grant Radar Copilot",
    initial:
      "Ask about this opportunity: whether it is worth the team's time, how it compares with the others on the list, or what to build for it.",
    placeholder: "Why is this worth prioritizing this week?",
  },

  operations: {
    eyebrow: "Operations",
    title: "Pipeline health",
    description: "Everything that only matters when something breaks: scans, sources, runs and maintenance.",
    scan: {
      title: "Manual scan",
      description: "Runs the grant & hackathon pipeline now instead of waiting for the next scheduled run.",
      idle: "No manual scan has run since the API started.",
      elapsed: (duration: string) => `running for ${duration}`,
      steps: { queued: "Queued", running: "Running", done: "Done" },
      counts: "Last result",
    },
    sources: {
      title: "Sources",
      description: (count: number) => `${count} tracked`,
      problems: "Problems",
      all: "All",
      noProblems: "Every source fetched successfully on its last run.",
      empty: "No source health records yet.",
      columns: { source: "Source", status: "Status", lastSuccess: "Last success", failures: "Failures", lastError: "Last error" },
      loadError: "Couldn't load source health",
    },
    runs: {
      title: "Recent runs",
      columns: { job: "Job", status: "Status", started: "Started", flow: "Fetched → new → verified", error: "Error" },
      empty: "No scheduler runs recorded yet.",
      loadError: "Couldn't load recent runs",
    },
    maintenance: {
      title: "Maintenance",
      summary: {
        title: "Send today's summary to Slack",
        description: "Posts the daily digest now. The scheduled 23:55 run still happens.",
        action: "Send summary",
        done: "Daily summary sent to Slack",
        failed: "Couldn't send the daily summary",
      },
      tavily: {
        title: "Unlock Tavily sources",
        description: "Lets sources already searched today run again before midnight. Uses Tavily credits.",
        action: "Unlock",
        failed: "Couldn't unlock Tavily sources",
      },
      dedup: {
        title: "Reset dedup index",
        description: "Clears the semantic dedup vectors. The next scans may post items the team has already seen.",
        action: "Reset…",
        confirmTitle: "Reset the dedup index?",
        confirmBody:
          "This clears every semantic dedup vector. Until the index is rebuilt, scans can treat known opportunities as new and post them to Slack again.",
        confirm: "Reset index",
        failed: "Couldn't reset the dedup index",
      },
    },
  },

  landing: {
    nav: { how: "How it works", console: "The console", open: "Open the radar" },

    hero: {
      title: "Which Web3 grants are worth chasing this week?",
      highlight: "worth chasing",
      lede:
        "Grant Radar reads ecosystem blogs, project sites, search results and X twice a day. Every candidate is deduplicated, classified, verified and scored before it reaches Slack and the team's triage board.",
      cta: "Open the radar",
    },

    /** The hero diagram: one illustrative opportunity on its way through. */
    flow: {
      sourcesLabel: "sources",
      sources: ["rss", "web", "tavily", "x", "listings"],
      pipelineLabel: "radar pipeline",
      stages: ["dedup", "classify", "verify", "score"],
      card: {
        type: "Grant",
        title: "Stellar Community Fund",
        chain: "stellar",
        reward: "up to $150K",
        deadline: "closes in 12d",
        verified: "Verified",
        score: "8.4",
      },
      verdict: "shortlist",
      verdictNote: "the team decides in the console",
      delivered: "✓ posted to Slack",
    },

    sources: ["Ecosystem RSS", "Project websites", "Tavily search", "X / Twitter", "ETHGlobal", "Superteam Earn", "Devpost"],

    how: {
      label: "How it works",
      title: "From a noisy feed to a short list.",
      description:
        "Four stages run on every scan: twice a day at 09:00 and 21:00 (Asia/Shanghai), or whenever someone presses Run scan.",
      stages: [
        {
          num: "01",
          title: "Discover",
          description:
            "RSS feeds, project sites, Tavily search, X and the structured listings of ETHGlobal, Superteam Earn and Devpost are fetched in parallel.",
          sample: [
            { text: "fetch ", tone: "key" },
            { text: "rss · web · tavily · x · listings", tone: "value" },
          ],
        },
        {
          num: "02",
          title: "Deduplicate",
          description:
            "Canonical URLs drop exact repeats. Semantic embeddings catch the same programme announced in five places and raise its heat instead.",
          sample: [
            { text: "L1 ", tone: "key" },
            { text: "url", tone: "value" },
            { text: " · L2 ", tone: "key" },
            { text: "semantic → heat ×5", tone: "value" },
          ],
        },
        {
          num: "03",
          title: "Classify & verify",
          description:
            "An LLM separates grants and hackathons from noise. Zero-trust checks anchor the origin, re-fetch the apply page and screen it for phishing.",
          sample: [
            { text: "origin ", tone: "key" },
            { text: "✓", tone: "verdict" },
            { text: " reachable ", tone: "key" },
            { text: "✓", tone: "verdict" },
            { text: " phishing ", tone: "key" },
            { text: "clear", tone: "verdict" },
          ],
        },
        {
          num: "04",
          title: "Score & deliver",
          description:
            "ROI, reputation, timeliness and strategic fit add up to one score. New opportunities go to Slack and onto the triage board.",
          sample: [
            { text: "roi ", tone: "key" },
            { text: "9.0", tone: "value" },
            { text: " · fit ", tone: "key" },
            { text: "7.5", tone: "value" },
            { text: " · score ", tone: "key" },
            { text: "8.4", tone: "verdict" },
          ],
        },
      ],
    },

    console: {
      label: "The console",
      title: "Triage together, in one place.",
      description:
        "Each opportunity is New, Shortlisted or Dismissed, and the decision is shared by the whole team. The view lives in the URL, so a link opens exactly what you saw.",
      features: [
        {
          title: "Keyboard triage",
          description:
            "Move with J and K, shortlist with S, dismiss with D, undo with Z. Opportunities past their deadline leave the list on their own.",
          keys: ["J", "K", "S", "D", "Z"],
        },
        {
          title: "Verification on demand",
          description:
            "Trust score, key evidence, open questions, similar past events and the ways to take part, for any opportunity, when you ask for it.",
          sample: [
            { text: "confidence ", tone: "key" },
            { text: "high", tone: "verdict" },
            { text: " · evidence ", tone: "key" },
            { text: "4", tone: "value" },
            { text: " · unknowns ", tone: "key" },
            { text: "1", tone: "value" },
          ],
        },
        {
          title: "Ask Copilot",
          description:
            "A read-only assistant that answers from the database: is this worth our week, how does it compare, what should we build for it.",
          sample: [{ text: "“How does this compare with the other Stellar grants?”", tone: "value" }],
        },
      ],
    },

    closing: {
      label: "Ready to triage?",
      title: "Today's opportunities are scored and waiting.",
      primary: "Open the radar",
      secondary: "Pipeline health",
    },

    footer: {
      blurb: "Daily triage of Web3 grants and hackathons — deduplicated, verified and scored.",
      columns: [
        {
          title: "Overview",
          links: [
            { label: "How it works", href: "#how" },
            { label: "The console", href: "#console" },
          ],
        },
        {
          title: "Console",
          links: [
            { label: "Triage", href: "/triage" },
            { label: "Operations", href: "/operations" },
          ],
        },
      ],
      schedule: "Scans daily at 09:00 and 21:00 · Asia/Shanghai",
      copyright: "© 2026 Web3 Grant Radar",
    },
  },
} as const;
