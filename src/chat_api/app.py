from fastapi import Depends, FastAPI, HTTPException, Query

from .auth import verify_internal_key

from .schemas import (
    DailySummaryTriggerResponse,
    DashboardInvestigationsResponse,
    DashboardOpportunitiesResponse,
    DashboardOpportunityDetail,
    DashboardOpportunityItem,
    DashboardScheduleLogsResponse,
    DashboardSourceHealthResponse,
    DedupResetResponse,
    DeleteOpportunityResponse,
    HealthResponse,
    InvestigateRequest,
    InvestigateResponse,
    ManualScanStatusResponse,
    ProposeOptionsRequest,
    ProposeOptionsResponse,
    SelectTargetsRequest,
    SelectTargetsResponse,
    TavilyUnlockResponse,
    TriageRequest,
    VerifyRequest,
    VerifyResponse,
)

app = FastAPI(title="Web3 Grant Radar API", version="v1")


@app.get("/api/v1/chat/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get(
    "/api/v1/dashboard/opportunities",
    response_model=DashboardOpportunitiesResponse,
    dependencies=[Depends(verify_internal_key)],
)
def dashboard_opportunities(
    status: str = Query(default="new", pattern="^(new|shortlisted|dismissed|all)$"),
    event_types: list[str] = Query(default=["grant", "hackathon"]),
    ecosystem: str = "",
    source_trust: str = Query(default="all", pattern="^(all|official|discovery)$"),
    q: str = "",
    sort: str = Query(default="score", pattern="^(score|deadline|newest)$"),
    closing_within_days: int = Query(default=0, ge=0, le=365),
) -> DashboardOpportunitiesResponse:
    from . import dashboard_service

    result = dashboard_service.list_opportunities(
        {
            "status": status,
            "event_types": event_types,
            "ecosystem": ecosystem,
            "source_trust": source_trust,
            "q": q,
            "sort": sort,
            "closing_within_days": closing_within_days,
        }
    )
    return DashboardOpportunitiesResponse(**result)


@app.get(
    "/api/v1/dashboard/opportunities/{event_id}",
    response_model=DashboardOpportunityDetail,
    dependencies=[Depends(verify_internal_key)],
)
def dashboard_opportunity_detail(event_id: int) -> DashboardOpportunityDetail:
    from . import dashboard_service

    try:
        result = dashboard_service.get_opportunity(event_id)
    except ValueError as exc:
        if str(exc) == "event_not_found":
            raise HTTPException(status_code=404, detail="event_not_found") from exc
        raise
    return DashboardOpportunityDetail(**result)


@app.delete(
    "/api/v1/dashboard/opportunities/{event_id}",
    response_model=DeleteOpportunityResponse,
    dependencies=[Depends(verify_internal_key)],
)
def delete_dashboard_opportunity(event_id: int) -> DeleteOpportunityResponse:
    from . import dashboard_service

    try:
        result = dashboard_service.delete_opportunity(event_id)
    except ValueError as exc:
        if str(exc) == "event_not_found":
            raise HTTPException(status_code=404, detail="event_not_found") from exc
        raise

    return DeleteOpportunityResponse(**result)


@app.put(
    "/api/v1/dashboard/opportunities/{event_id}/triage",
    response_model=DashboardOpportunityItem,
    dependencies=[Depends(verify_internal_key)],
)
def triage_dashboard_opportunity(event_id: int, payload: TriageRequest) -> DashboardOpportunityItem:
    from . import dashboard_service

    try:
        result = dashboard_service.triage_opportunity(event_id, payload.status)
    except ValueError as exc:
        if str(exc) == "event_not_found":
            raise HTTPException(status_code=404, detail="event_not_found") from exc
        raise
    return DashboardOpportunityItem(**result)


@app.get(
    "/api/v1/dashboard/source-health",
    response_model=DashboardSourceHealthResponse,
    dependencies=[Depends(verify_internal_key)],
)
def dashboard_source_health() -> DashboardSourceHealthResponse:
    from . import dashboard_service

    result = dashboard_service.list_source_health()
    return DashboardSourceHealthResponse(**result)


@app.get(
    "/api/v1/dashboard/schedule-logs",
    response_model=DashboardScheduleLogsResponse,
    dependencies=[Depends(verify_internal_key)],
)
def dashboard_schedule_logs(limit: int = 50) -> DashboardScheduleLogsResponse:
    from . import dashboard_service

    result = dashboard_service.list_schedule_logs(limit=limit)
    return DashboardScheduleLogsResponse(**result)


@app.get(
    "/api/v1/dashboard/investigations",
    response_model=DashboardInvestigationsResponse,
    dependencies=[Depends(verify_internal_key)],
)
def dashboard_investigations(limit: int = 50) -> DashboardInvestigationsResponse:
    from . import dashboard_service

    result = dashboard_service.list_investigations(limit=limit)
    return DashboardInvestigationsResponse(**result)


@app.get(
    "/api/v1/dashboard/manual-scan",
    response_model=ManualScanStatusResponse,
    dependencies=[Depends(verify_internal_key)],
)
def manual_scan_status() -> ManualScanStatusResponse:
    from . import manual_scan_service

    result = manual_scan_service.get_manual_scan_status()
    return ManualScanStatusResponse(**result)


@app.post(
    "/api/v1/dashboard/manual-scan",
    response_model=ManualScanStatusResponse,
    dependencies=[Depends(verify_internal_key)],
)
def trigger_manual_scan() -> ManualScanStatusResponse:
    from . import manual_scan_service
    from src.main import run_pipeline

    result = manual_scan_service.trigger_manual_scan(run_pipeline)
    return ManualScanStatusResponse(**result)


@app.post(
    "/api/v1/dashboard/daily-summary",
    response_model=DailySummaryTriggerResponse,
    dependencies=[Depends(verify_internal_key)],
)
def trigger_daily_summary() -> DailySummaryTriggerResponse:
    from . import daily_summary_api_service

    result = daily_summary_api_service.trigger_daily_summary()
    return DailySummaryTriggerResponse(**result)


@app.post(
    "/api/v1/chat/select-targets",
    response_model=SelectTargetsResponse,
    dependencies=[Depends(verify_internal_key)],
)
def select_targets(payload: SelectTargetsRequest) -> SelectTargetsResponse:
    from . import selection_service

    params = payload.model_dump(by_alias=True)
    ids = selection_service.select_target_event_ids(params)
    return SelectTargetsResponse(target_event_ids=ids, no_data=len(ids) == 0)


@app.post(
    "/api/v1/chat/verify",
    response_model=VerifyResponse,
    dependencies=[Depends(verify_internal_key)],
)
def verify(payload: VerifyRequest) -> VerifyResponse:
    from . import verify_service

    result = verify_service.verify_targets(payload.target_event_ids)
    return VerifyResponse(**result)


@app.post(
    "/api/v1/chat/investigate",
    response_model=InvestigateResponse,
    dependencies=[Depends(verify_internal_key)],
)
def investigate(payload: InvestigateRequest) -> InvestigateResponse:
    from . import investigation_api_service

    result = investigation_api_service.investigate_event_by_id(payload.event_id)
    return InvestigateResponse(**result)


@app.post(
    "/api/v1/chat/propose-options",
    response_model=ProposeOptionsResponse,
    dependencies=[Depends(verify_internal_key)],
)
def propose_options_endpoint(payload: ProposeOptionsRequest) -> ProposeOptionsResponse:
    from . import proposal_service

    result = proposal_service.propose_options(payload.verified_facts)
    return ProposeOptionsResponse(**result)


@app.post(
    "/api/v1/admin/tavily-unlock",
    response_model=TavilyUnlockResponse,
    dependencies=[Depends(verify_internal_key)],
)
def tavily_unlock() -> TavilyUnlockResponse:
    """Manually unlock all Tavily cooldowns, resetting last_success_at to NULL."""
    from src.db.queries import unlock_tavily_cooldown
    from src.db.database import SessionLocal

    with SessionLocal() as db:
        count = unlock_tavily_cooldown(db)
        db.commit()

    return TavilyUnlockResponse(
        status="ok",
        unlocked_count=count,
        message=f"Unlocked {count} tavily source(s). They will fetch on next scheduler tick.",
    )


@app.post(
    "/api/v1/admin/reset-dedup",
    response_model=DedupResetResponse,
    dependencies=[Depends(verify_internal_key)],
)
def reset_dedup(full: bool = Query(False, description="If true, truncate ALL raw_signals instead of just orphans")) -> DedupResetResponse:
    """Reset deduplication state (ChromaDB vectors + raw_signals) for a clean rescan.

    - Default (full=false): Clears all ChromaDB vectors and purges only
      raw_signals that have no linked events (orphans).
    - Full (full=true): Clears all ChromaDB vectors AND truncates the
      entire raw_signals table. Use this for a complete fresh rescan.
    """
    from src.chat_api.dedup_reset_service import reset_all_dedup_state

    result = reset_all_dedup_state(full=full)

    error = result.get("vector_error") or result.get("signal_error") or ""
    return DedupResetResponse(
        status="ok" if not error else "partial",
        vectors_cleared=result["vectors_cleared"],
        signals_cleared=result["signals_cleared"],
        message=f"Vectors cleared: {result['vectors_cleared']}, signals cleared: {result['signals_cleared']}",
        error=error,
    )
