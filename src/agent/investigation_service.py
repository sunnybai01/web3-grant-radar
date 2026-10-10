"""Single-event investigation agent MVP.

This service intentionally keeps the control loop small and bounded.
It reuses the existing event model and verifier as deterministic tools,
while persisting mission state and per-step trajectories for auditability.
"""
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.dedup.vector_store import VectorStore
from src.db.models import AgentTrajectory
from src.db.models import Event
from src.db.queries import (
    add_agent_trajectory,
    create_agent_mission,
    finish_agent_mission,
)
from src.verifier.verifier import verify_opportunity


def _mission_snapshot(mission) -> dict[str, Any]:
    return {
        "id": mission.id,
        "goal": mission.goal,
        "event_id": mission.event_id,
        "status": mission.status,
        "mission_type": mission.mission_type,
        "max_steps": mission.max_steps,
    }


def _serialize_trajectory_rows(rows: list[AgentTrajectory]) -> list[dict[str, Any]]:
    return [
        {
            "step_index": row.step_index,
            "action": row.action,
            "thought": row.thought or "",
            "action_input": row.action_input or {},
            "observation": row.observation or {},
        }
        for row in rows
    ]


def _mission_trajectory(db: Session, mission_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(AgentTrajectory)
        .filter(AgentTrajectory.mission_id == mission_id)
        .order_by(AgentTrajectory.step_index.asc())
        .all()
    )
    return _serialize_trajectory_rows(rows)


def _load_event(db: Session, event_id: int) -> Event | None:
    return db.query(Event).filter(Event.id == event_id).first()


def _recommended_action(verdict: str) -> str:
    normalized = (verdict or "").lower()
    if normalized == "verified":
        return "promote"
    if normalized == "degraded":
        return "review"
    return "reject"


def _build_vector_store() -> VectorStore:
    return VectorStore()


def _fetch_supporting_page_evidence(event: Event) -> dict[str, Any] | None:
    url = event.application_url or event.source_url or ""
    if not url:
        return None

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "Web3GrantRadar-Investigator/1.0"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
    except Exception:
        return None

    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:
        return None

    page_title = ""
    if soup.title and soup.title.get_text(strip=True):
        page_title = soup.title.get_text(strip=True)[:200]
    else:
        heading = soup.find(["h1", "h2"])
        if heading:
            page_title = heading.get_text(separator=" ", strip=True)[:200]

    body = soup.body or soup
    for tag in body.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    excerpt = body.get_text(separator=" ", strip=True)
    excerpt = " ".join(excerpt.split())[:280]
    if not page_title and not excerpt:
        return None

    return {
        "url": str(response.url),
        "title": page_title,
        "excerpt": excerpt,
    }


def _retrieve_similar_events(db: Session, event: Event, *, limit: int = 3) -> list[dict[str, Any]]:
    query_text = f"{event.title or ''} {event.description or ''}".strip()
    if not query_text:
        return []

    try:
        similar = _build_vector_store().search_similar(query_text, n_results=limit + 1)
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    for doc_id, distance, _meta in similar:
        try:
            similar_event_id = int(str(doc_id).replace("event_", ""))
        except ValueError:
            continue

        if similar_event_id == event.id:
            continue

        similar_event = db.query(Event).filter(Event.id == similar_event_id).first()
        if similar_event is None:
            continue

        items.append(
            {
                "event_id": similar_event.id,
                "title": similar_event.title,
                "ecosystem": similar_event.ecosystem,
                "similarity": round(1.0 - float(distance), 2),
            }
        )
        if len(items) >= limit:
            break

    return items


def investigate_event(db: Session, event_id: int, *, max_steps: int = 5) -> dict[str, Any]:
    """Investigate one existing event with a bounded, auditable loop."""
    mission = create_agent_mission(
        db,
        goal=f"investigate_event:{event_id}",
        event_id=event_id,
        max_steps=max_steps,
    )

    state: dict[str, Any] = {
        "event": None,
        "verification": None,
        "similar_events": [],
        "supporting_evidence": None,
    }
    step_index = 0

    event = _load_event(db, event_id)
    if event is None:
        add_agent_trajectory(
            db,
            mission_id=mission.id,
            step_index=step_index,
            action="load_event",
            thought="Load the requested event before choosing tools.",
            action_input={"event_id": event_id},
            observation={"error": "event_not_found"},
        )
        mission = finish_agent_mission(
            db,
            mission.id,
            status="failed",
            error_message="event_not_found",
        )
        return {
            "status": "failed",
            "event_id": event_id,
            "mission": _mission_snapshot(mission),
            "conclusion": None,
            "trajectory": _mission_trajectory(db, mission.id),
            "error": "event_not_found",
        }

    state["event"] = event
    add_agent_trajectory(
        db,
        mission_id=mission.id,
        step_index=step_index,
        action="load_event",
        thought="Load the requested event before choosing tools.",
        action_input={"event_id": event_id},
        observation={
            "title": event.title,
            "event_type": event.event_type,
            "ecosystem": event.ecosystem,
        },
    )

    step_index += 1
    similar_events = _retrieve_similar_events(db, event)
    state["similar_events"] = similar_events
    add_agent_trajectory(
        db,
        mission_id=mission.id,
        step_index=step_index,
        action="retrieve_similar_events",
        thought="Look up related historical opportunities before finalizing confidence.",
        action_input={"event_id": event.id, "limit": 3},
        observation={
            "similar_events_count": len(similar_events),
            "similar_events": similar_events,
        },
    )

    step_index += 1
    supporting_evidence = _fetch_supporting_page_evidence(event)
    state["supporting_evidence"] = supporting_evidence
    add_agent_trajectory(
        db,
        mission_id=mission.id,
        step_index=step_index,
        action="fetch_supporting_evidence",
        thought="Fetch the landing page once to capture a concrete title and excerpt.",
        action_input={"url": event.application_url or event.source_url or ""},
        observation=supporting_evidence or {"status": "not_available"},
    )

    step_index += 1
    verification = verify_opportunity(
        event_type=(event.event_type or "").upper(),
        source_url=event.source_url or "",
        application_url=event.application_url or "",
        source_name=event.source_platform or "",
        metadata=(event.verification_log or {}).get("source_context") or {},
    )
    state["verification"] = verification
    add_agent_trajectory(
        db,
        mission_id=mission.id,
        step_index=step_index,
        action="verify_event",
        thought="Use the deterministic verifier before producing a conclusion.",
        action_input={
            "event_type": event.event_type,
            "source_url": event.source_url,
            "application_url": event.application_url,
        },
        observation={
            "verdict": verification.get("verdict", "unknown"),
            "is_verified": bool(verification.get("is_verified")),
        },
    )

    step_index += 1
    verdict = str(verification.get("verdict") or "unknown").lower()
    conclusion = {
        "event_id": event.id,
        "title": event.title,
        "verdict": verdict,
        "recommended_action": _recommended_action(verdict),
        "summary": f"Verification verdict for event {event.id}: {verdict}.",
        "similar_events": state["similar_events"],
        "supporting_evidence": state["supporting_evidence"],
    }
    add_agent_trajectory(
        db,
        mission_id=mission.id,
        step_index=step_index,
        action="finalize_conclusion",
        thought="Convert the gathered evidence into a bounded final recommendation.",
        action_input={"verdict": verdict},
        observation=conclusion,
    )

    mission = finish_agent_mission(
        db,
        mission.id,
        status="completed",
        conclusion=conclusion,
    )
    return {
        "status": "completed",
        "event_id": event.id,
        "mission": _mission_snapshot(mission),
        "conclusion": conclusion,
        "trajectory": _mission_trajectory(db, mission.id),
        "error": "",
    }