"""Streamlit Web Dashboard — browse and filter opportunities."""
import sys
from pathlib import Path

# Add project root to path when running streamlit directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

from sqlalchemy import desc
from src.db.database import SessionLocal, init_db
from src.db.models import Event, SourceHealth, ScheduleLog
from src.chat_api import dashboard_service

init_db()

st.set_page_config(page_title="Web3 Grant Radar", page_icon="🔍", layout="wide")

st.title("🔍 Web3 Grant Radar — Opportunity Dashboard")
st.caption(f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

# --- Sidebar filters ---
st.sidebar.header("Filters")
event_type_filter = st.sidebar.multiselect(
    "Type", ["grant", "hackathon"], default=["grant", "hackathon"]
)
ecosystem_filter = st.sidebar.text_input("Ecosystem (e.g., sui, ethereum)", "")
min_score = st.sidebar.slider("Min Score", 0.0, 10.0, 5.0, 0.5)
days = st.sidebar.slider("Last N days", 1, 30, 14)

# --- Main area ---
tab1, tab2, tab3, tab4 = st.tabs(["📋 Opportunities", "📊 Source Health", "📜 Schedule Logs", "🧭 Investigations"])

with tab1:
    st.header("Active Opportunities")

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        q = db.query(Event).filter(
            Event.created_at >= cutoff,
            Event.status.in_(["new", "pushed"]),
        )

        if event_type_filter:
            q = q.filter(Event.event_type.in_(event_type_filter))
        if ecosystem_filter:
            q = q.filter(Event.ecosystem.ilike(f"%{ecosystem_filter}%"))
        q = q.filter(Event.final_score >= min_score)
        q = q.order_by(desc(Event.final_score))

        events = q.limit(200).all()

        if not events:
            st.info("No opportunities match your filters.")
        else:
            rows = []
            for e in events:
                rows.append({
                    "Score": f"{e.final_score:.1f}" if e.final_score else "-",
                    "Type": e.event_type.upper(),
                    "Title": e.title[:120] if e.title else "",
                    "Ecosystem": e.ecosystem or "-",
                    "Amount": e.amount or "-",
                    "Deadline": e.deadline.strftime("%Y-%m-%d") if e.deadline else "Rolling",
                    "Heat": e.heat_count or 1,
                    "Verified": "✅" if e.is_verified else "⚠️",
                    "Apply": e.application_url or e.source_url or "",
                })

            df = pd.DataFrame(rows)
            st.dataframe(
                df,
                column_config={
                    "Apply": st.column_config.LinkColumn("Apply", display_text="🔗"),
                    "Score": st.column_config.TextColumn("Score"),
                },
                hide_index=True,
                use_container_width=True,
            )

            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Shown", len(events))
            col2.metric("Avg Score", f"{sum(e.final_score or 0 for e in events) / max(len(events), 1):.1f}")
            col3.metric("Verified %", f"{sum(1 for e in events if e.is_verified) / max(len(events), 1) * 100:.0f}%")
            col4.metric("Grants/Hacks",
                        f"{sum(1 for e in events if e.event_type=='grant')}/"
                        f"{sum(1 for e in events if e.event_type=='hackathon')}")
    finally:
        db.close()

with tab2:
    st.header("Source Health")
    db = SessionLocal()
    try:
        sources = db.query(SourceHealth).all()
        if not sources:
            st.info("No source health data yet.")
        else:
            rows = []
            for s in sources:
                rows.append({
                    "Source": s.source_name,
                    "Status": s.status,
                    "Last Success": s.last_success_at.strftime("%Y-%m-%d %H:%M") if s.last_success_at else "Never",
                    "Failures": s.consecutive_failures,
                    "Last Error": (s.last_error or "")[:100],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
    finally:
        db.close()

with tab3:
    st.header("Schedule Logs")
    db = SessionLocal()
    try:
        logs = db.query(ScheduleLog).order_by(desc(ScheduleLog.started_at)).limit(50).all()
        if not logs:
            st.info("No schedule logs yet.")
        else:
            rows = []
            for l in logs:
                rows.append({
                    "Job": l.job_name,
                    "Status": l.status,
                    "Started": l.started_at.strftime("%m-%d %H:%M") if l.started_at else "",
                    "Fetched": l.items_fetched,
                    "New": l.items_new,
                    "Deduped": l.items_deduped,
                    "Verified": l.items_verified,
                    "Error": (l.error_message or "")[:80],
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
    finally:
        db.close()

with tab4:
    st.header("Agent Investigations")
    result = dashboard_service.list_investigations(limit=50)
    summary = result.get("summary", {})
    items = result.get("items", [])

    if not items:
        st.info("No investigation runs yet.")
    else:
        df = pd.DataFrame(
            [
                {
                    "Mission": item["mission_id"],
                    "Event": item["event_id"],
                    "Status": item["status"],
                    "Started": item["started"],
                    "Finished": item["finished"] or "-",
                    "Title": item["title"][:120] if item["title"] else "",
                    "Verdict": item["verdict"],
                    "Action": item["recommended_action"],
                    "Similar": item["similar_count"],
                    "Supporting": "Yes" if item["has_supporting_evidence"] else "No",
                    "Error": item["error"],
                }
                for item in items
            ]
        )
        st.dataframe(df, hide_index=True, use_container_width=True)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Runs", summary.get("total_runs", 0))
        col2.metric("Completed", summary.get("completed", 0))
        col3.metric("Failed", summary.get("failed", 0))
        col4.metric("Running", summary.get("running", 0))

# Auto-refresh every 5 minutes
st.caption("Auto-refreshes every 5 minutes")
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True
