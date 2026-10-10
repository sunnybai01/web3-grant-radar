from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str


class SelectTargetsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["mixed"] = "mixed"
    event_id: int | None = None
    source_name: str | None = None
    from_: datetime | None = Field(default=None, alias="from")
    to: datetime | None = None
    limit: int = 20


class SelectTargetsResponse(BaseModel):
    target_event_ids: list[int]
    no_data: bool = False


class EvidenceItem(BaseModel):
    category: str
    detail: str
    source: str
    weight: int
    impact: str


class VerifyResponse(BaseModel):
    score: int
    level: str
    verdict: str
    evidence: list[EvidenceItem]
    unknowns: list[str]
    conflicts: list[str]


class VerifyRequest(BaseModel):
    target_event_ids: list[int]


class InvestigateRequest(BaseModel):
    event_id: int


class InvestigationMission(BaseModel):
    id: int
    goal: str
    event_id: int
    status: str
    mission_type: str
    max_steps: int


class SimilarEventItem(BaseModel):
    event_id: int
    title: str
    ecosystem: str | None = None
    similarity: float


class SupportingEvidenceItem(BaseModel):
    url: str
    title: str
    excerpt: str


class InvestigationConclusion(BaseModel):
    event_id: int
    title: str
    verdict: str
    recommended_action: str
    summary: str
    similar_events: list[SimilarEventItem] = []
    supporting_evidence: SupportingEvidenceItem | None = None


class InvestigationTrajectoryStep(BaseModel):
    step_index: int
    action: str
    thought: str = ""
    action_input: dict = {}
    observation: dict = {}


class InvestigateResponse(BaseModel):
    status: str
    event_id: int
    mission: InvestigationMission
    conclusion: InvestigationConclusion | None = None
    trajectory: list[InvestigationTrajectoryStep] = []
    error: str = ""


class ProposeOptionsRequest(BaseModel):
    verified_facts: dict


class ProposedOption(BaseModel):
    tier: str
    summary: str
    assumptions: list[str]


class ProposeOptionsResponse(BaseModel):
    options: list[ProposedOption]


class DashboardOpportunityItem(BaseModel):
    id: int
    score: float | None = None
    type: str
    title: str
    ecosystem: str | None = None
    amount: str | None = None
    deadline: str
    heat: int
    verified: bool
    source_trust: str
    verification_verdict: str
    apply_url: str
    is_dismissed: bool = False


class DashboardOpportunityMetrics(BaseModel):
    total_shown: int
    avg_score: float
    verified_percent: int
    # Coverage split behind verified_percent. Without these the dashboard can only
    # show "0% verified" and cannot say that nothing was checked at all.
    verified_count: int = 0
    unchecked_count: int = 0
    grants: int
    hackathons: int
    official: int
    discovery: int


class DashboardOpportunitiesResponse(BaseModel):
    metrics: DashboardOpportunityMetrics
    items: list[DashboardOpportunityItem]


class DeleteOpportunityResponse(BaseModel):
    status: str
    event_id: int
    deleted: bool


class DismissEventResponse(BaseModel):
    status: str
    event_id: int
    is_dismissed: bool


class DashboardSourceHealthItem(BaseModel):
    source: str
    status: str
    last_success: str
    last_fetch: str
    failures: int
    last_error: str


class DashboardSourceHealthSummary(BaseModel):
    total_sources: int
    healthy: int
    degraded: int
    down: int


class DashboardSourceHealthResponse(BaseModel):
    summary: DashboardSourceHealthSummary
    items: list[DashboardSourceHealthItem]


class DashboardScheduleLogItem(BaseModel):
    id: int
    job: str
    status: str
    started: str
    fetched: int
    new: int
    deduped: int
    classified: int
    verified: int
    error: str


class DashboardScheduleLogSummary(BaseModel):
    total_runs: int
    success: int
    failed: int
    running: int


class DashboardScheduleLogsResponse(BaseModel):
    summary: DashboardScheduleLogSummary
    items: list[DashboardScheduleLogItem]


class DashboardInvestigationItem(BaseModel):
    mission_id: int
    event_id: int
    status: str
    started: str
    finished: str
    title: str
    verdict: str
    recommended_action: str
    similar_count: int
    has_supporting_evidence: bool
    error: str


class DashboardInvestigationsSummary(BaseModel):
    total_runs: int
    completed: int
    failed: int
    running: int


class DashboardInvestigationsResponse(BaseModel):
    summary: DashboardInvestigationsSummary
    items: list[DashboardInvestigationItem]


class DailySummaryTriggerResponse(BaseModel):
    status: str
    summary_date: str
    slack_ts: str = ""
    error: str = ""


class ManualScanScheduleResult(BaseModel):
    schedule: str
    status: str
    fetched: int = 0
    new: int = 0
    deduped: int = 0
    classified: int = 0
    verified: int = 0
    fraud: int = 0
    pushed: int = 0
    error: str = ""


class ManualScanStatusResponse(BaseModel):
    job_id: str | None = None
    status: str
    triggered: bool = False
    started_at: str = ""
    finished_at: str = ""
    current_stage: str = ""
    schedules: list[ManualScanScheduleResult] = []
    # The service reports why a scan failed; without this field the response
    # model dropped it and the UI could only show a bare "failed".
    error: str = ""


class TavilyUnlockResponse(BaseModel):
    status: str
    unlocked_count: int
    message: str = ""
    error: str = ""


class DedupResetResponse(BaseModel):
    status: str
    vectors_cleared: bool = False
    signals_cleared: int = 0
    message: str = ""
    error: str = ""
