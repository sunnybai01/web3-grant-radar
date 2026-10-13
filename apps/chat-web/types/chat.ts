export type AnalysisTargetInput = {
  event_id?: number;
  source_name?: string;
  from?: string;
  to?: string;
  limit?: number;
};

export type SelectTargetsRequest = {
  mode?: "mixed";
  event_id?: number;
  source_name?: string;
  from?: string;
  to?: string;
  limit?: number;
};

export type SelectTargetsResponse = {
  target_event_ids: number[];
  no_data?: boolean;
};

export type VerificationEvidenceItem = {
  category?: string;
  source?: string;
  detail?: string;
  impact?: string;
  weight?: number;
};

export type VerifyResponse = {
  score: number;
  level?: string;
  verdict: string;
  evidence?: VerificationEvidenceItem[];
  unknowns?: string[];
  conflicts?: string[];
};

export type OptionItem = {
  tier: string;
  summary: string;
  assumptions: string[];
};

export type ProposeOptionsRequest = {
  verified_facts: Record<string, string | number | boolean | undefined>;
};

export type ProposeOptionsResponse = {
  options: OptionItem[];
};

export type MixedModeResult = {
  selected: SelectTargetsResponse;
  verification: VerifyResponse;
  options: ProposeOptionsResponse;
};

export type InvestigateRequest = {
  event_id: number;
};

export type InvestigationMission = {
  id: number;
  goal: string;
  event_id: number;
  status: string;
  mission_type: string;
  max_steps: number;
};

export type InvestigationSimilarEvent = {
  event_id: number;
  title: string;
  ecosystem: string | null;
  similarity: number;
};

export type InvestigationSupportingEvidence = {
  url: string;
  title: string;
  excerpt: string;
};

export type InvestigationConclusion = {
  event_id: number;
  title: string;
  verdict: string;
  recommended_action: string;
  summary: string;
  similar_events: InvestigationSimilarEvent[];
  supporting_evidence: InvestigationSupportingEvidence | null;
};

export type InvestigationTrajectoryStep = {
  step_index: number;
  action: string;
  thought: string;
  action_input: Record<string, unknown>;
  observation: Record<string, unknown>;
};

export type InvestigationResponse = {
  status: string;
  event_id: number;
  mission: InvestigationMission;
  conclusion: InvestigationConclusion | null;
  trajectory: InvestigationTrajectoryStep[];
  error: string;
};

export type TriageStatus = "new" | "shortlisted" | "dismissed";
export type TriageTab = TriageStatus | "all";
export type OpportunitySort = "score" | "deadline" | "newest" | "reward";
export type SourceTrust = "official" | "discovery";

export type OpportunityScores = {
  roi: number | null;
  reputation: number | null;
  timeliness: number | null;
  strategy: number | null;
};

export type DashboardOpportunityItem = {
  id: number;
  score: number | null;
  scores: OpportunityScores;
  type: string;
  title: string;
  summary: string;
  ecosystem: string | null;
  amount: string | null;
  /** Rough USD reading of `amount`; null when it could not be read. */
  amount_usd: number | null;
  /** ISO-8601, or null when no deadline was stated. */
  deadline: string | null;
  /** With no deadline: true when the programme accepts applications on a rolling basis. */
  rolling: boolean;
  first_seen: string | null;
  heat: number;
  source_count: number;
  verified: boolean;
  verification_verdict: string;
  source_trust: SourceTrust | string;
  /** The application page, or "" when none was found. */
  apply_url: string;
  /** Where the opportunity was found (tweet, article, programme page). */
  source_url: string;
  triage_status: TriageStatus;
};

export type DashboardOpportunitySource = {
  name: string;
  type: string;
  url: string;
  fetched_at: string | null;
};

export type DashboardOpportunityDetail = DashboardOpportunityItem & {
  description: string;
  sources: DashboardOpportunitySource[];
};

/** Whole-board stats; they ignore the list filters. */
export type DashboardOpportunityMetrics = {
  to_review: number;
  shortlisted: number;
  closing_soon: number;
  verified_percent: number;
  verified_count: number;
  unchecked_count: number;
  total: number;
};

export type DashboardOpportunityCounts = Record<TriageTab, number>;

export type DashboardOpportunitiesResponse = {
  metrics: DashboardOpportunityMetrics;
  counts: DashboardOpportunityCounts;
  ecosystems: string[];
  next_scan_at: string | null;
  items: DashboardOpportunityItem[];
};

export type OpportunityFilters = {
  status: TriageTab;
  type: "all" | "grant" | "hackathon";
  trust: "all" | SourceTrust;
  ecosystem: string;
  q: string;
  sort: OpportunitySort;
  closingSoon: boolean;
};

export type DeleteOpportunityResponse = {
  status: string;
  event_id: number;
  deleted: boolean;
};

export type DashboardSourceHealthItem = {
  source: string;
  status: string;
  last_success: string;
  last_fetch: string;
  last_success_at: string | null;
  last_fetch_at: string | null;
  failures: number;
  last_error: string;
};

export type DashboardSourceHealthSummary = {
  total_sources: number;
  healthy: number;
  degraded: number;
  down: number;
};

export type DashboardSourceHealthResponse = {
  summary: DashboardSourceHealthSummary;
  items: DashboardSourceHealthItem[];
};

export type DashboardScheduleLogItem = {
  id: number;
  job: string;
  status: string;
  started: string;
  started_at: string | null;
  fetched: number;
  new: number;
  deduped: number;
  classified: number;
  verified: number;
  error: string;
};

export type DashboardScheduleLogSummary = {
  total_runs: number;
  success: number;
  failed: number;
  running: number;
};

export type DashboardScheduleLogsResponse = {
  summary: DashboardScheduleLogSummary;
  items: DashboardScheduleLogItem[];
};

export type ManualScanScheduleResult = {
  schedule: string;
  status: string;
  fetched: number;
  new: number;
  deduped: number;
  classified: number;
  verified: number;
  fraud: number;
  pushed: number;
  error: string;
};

export type ManualScanStatusResponse = {
  job_id: string | null;
  status: string;
  triggered: boolean;
  started_at: string;
  finished_at: string;
  current_stage: string;
  schedules: ManualScanScheduleResult[];
  error: string;
};

export type DailySummaryTriggerResponse = {
  status: string;
  summary_date: string;
  slack_ts: string;
  error: string;
};

export type TavilyUnlockResponse = {
  status: string;
  unlocked_count: number;
  message: string;
};

export type DedupResetResponse = {
  status: string;
  vectors_cleared: boolean;
  signals_cleared: number;
  message: string;
  error: string;
};
