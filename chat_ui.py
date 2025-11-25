#!/usr/bin/env python3
"""
ASX Investment Assistant - Chat UI with Trade Approvals

Streamlit-based chat interface for the ASX multi-agent investment system.

Features:
- Tab 1: Chat with coordinator agent (natural language requests)
- Tab 2: Approve/reject pending trades (integrated with approval_service.py)
- Real-time progress tracking by monitoring database

Usage:
    # Start all agents first (including approval_service.py):
    python main.py --all
    python approval_service.py

    # Then start the chat UI:
    streamlit run chat_ui.py

Access:
    http://localhost:8501
"""
import asyncio
import time
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import streamlit as st

from models.database import get_db_session
from models.orm_models import Announcement, Analysis, StockData, Evaluation, TradingDecision, LogMessage
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="ASX Investment Assistant",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_asx_code(user_message: str) -> Optional[str]:
    """
    Extract ASX code from user message.

    Examples:
    - "Analyze BHP limit 5" -> "BHP"
    - "Check CBA announcements" -> "CBA"

    Returns:
        ASX code or None if not found
    """
    # Common ASX codes (3-4 uppercase letters)
    match = re.search(r'\b([A-Z]{3,4})\b', user_message)
    if match:
        return match.group(1)
    return None


async def send_coordinator_request_fire_and_forget(user_message: str, task_id: str):
    """
    Send request to coordinator agent via A2A (fire-and-forget).

    We don't wait for the response since the pipeline takes 60-120s to complete.
    Instead, we just trigger the pipeline and monitor the database for results.

    Args:
        user_message: Natural language request from user
        task_id: The unique ID for this request.
    """
    # A2A endpoint for coordinator agent (at root path)
    coordinator_url = settings.get_agent_url("coordinator")

    async with httpx.AsyncClient(timeout=300.0) as client:
        message_id = str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": message_id,
                    "role": "user",
                    "parts": [
                        {"text": user_message},
                        {"data": {"task_id": task_id}}
                    ]
                }
            },
            "id": str(uuid.uuid4())
        }

        logger.info(f"📤 Sending to coordinator (fire-and-forget): {user_message[:100]}...")
        logger.info(f"   URL: {coordinator_url}")

        # Send request but don't wait for response (pipeline takes too long)
        # The coordinator will process in background, we'll monitor the database
        try:
            # Start the request but don't wait for full response
            response = await client.post(coordinator_url, json=payload)
            logger.info(f"✅ Request sent to coordinator (status: {response.status_code})")
        except httpx.ReadTimeout:
            # Expected - pipeline takes longer than timeout
            logger.info(f"✅ Request sent (timed out as expected - pipeline running in background)")
        except Exception as e:
            logger.warning(f"⚠️ Request may have failed: {e}")


def get_pipeline_results(asx_code: str, start_time: datetime, limit: int = 10, task_id: str = None) -> Dict:
    """
    Get current pipeline results from database.

    NOTE: We show ALL recent announcements for the company, not just new ones.
    This is because existing announcements may be reprocessed (cached analysis returned).

    Args:
        asx_code: ASX ticker code
        start_time: When the request started (used for stock data timing only)
        limit: Max announcements to show (default 10)
        task_id: The ID for the current request.

    Returns:
        Dictionary with all results found so far
    """
    results = {
        "announcements": [],
        "analyses": [],
        "stock_data": None,
        "evaluations": [],
        "trades": []
    }

    with get_db_session() as db:
        # Get ALL recent announcements for this company (not just new ones)
        # This ensures we show results even if announcements were cached
        announcements = db.query(Announcement).filter(
            Announcement.asx_code == asx_code
        ).order_by(Announcement.created_at.desc()).limit(limit).all()

        logger.info(f"📊 DB Query: Found {len(announcements)} announcements for {asx_code}")
        results["announcements"] = announcements

        if announcements:
            announcement_ids = [a.id for a in announcements]

            # Get analyses
            analyses = db.query(Analysis).filter(
                Analysis.announcement_id.in_(announcement_ids)
            ).all()
            logger.info(f"📊 DB Query: Found {len(analyses)} analyses")
            results["analyses"] = analyses

            # Get evaluations
            evaluations = db.query(Evaluation).filter(
                Evaluation.announcement_id.in_(announcement_ids)
            ).all()
            logger.info(f"📊 DB Query: Found {len(evaluations)} evaluations")
            results["evaluations"] = evaluations

            # Get trades
            trades = db.query(TradingDecision).filter(
                TradingDecision.announcement_id.in_(announcement_ids)
            ).all()
            logger.info(f"📊 DB Query: Found {len(trades)} trades")
            results["trades"] = trades

        # Get stock data (most recent) - need to join through company
        if announcements:
            company_id = announcements[0].company_id
            stock_data = db.query(StockData).filter(
                StockData.company_id == company_id
            ).order_by(StockData.fetched_at.desc()).first()
            logger.info(f"📊 DB Query: Stock data: {stock_data is not None}")
            results["stock_data"] = stock_data
        else:
            logger.info(f"📊 DB Query: No announcements, skipping stock data")
            results["stock_data"] = None

    return results

def get_log_messages(task_id: str) -> List[LogMessage]:
    """Get all log messages for a given task_id from the database."""
    with get_db_session() as db:
        logs = db.query(LogMessage).filter(LogMessage.task_id == task_id).order_by(LogMessage.created_at.asc()).all()
        return logs

def is_pipeline_complete(results: Dict) -> bool:
    """Check if pipeline has completed processing."""
    if not results["announcements"]:
        return False

    num_announcements = len(results["announcements"])
    num_analyses = len(results["analyses"])
    num_evaluations = len(results["evaluations"])

    # Pipeline complete if we have evaluations for all announcements
    if num_evaluations >= num_announcements:
        # Check if any BUY recommendations need trades
        buy_recs = [e for e in results["evaluations"] if e.recommendation in ["BUY", "SPECULATIVE BUY"]]
        if buy_recs:
            # Should have trades created
            return len(results["trades"]) >= len(buy_recs)
        else:
            # No BUY recommendations, so complete
            return True

    return False


def display_results(results: Dict, asx_code: str):
    """Display pipeline results in Streamlit."""

    # Scraper results
    if results["announcements"]:
        with st.expander(f"📋 **Scraper Agent**: Found {len(results['announcements'])} announcement(s)", expanded=True):
            for ann in results["announcements"]:
                st.write(f"**{ann.title}**")
                st.caption(f"Date: {ann.announcement_date.strftime('%Y-%m-%d') if ann.announcement_date else 'N/A'} | "
                          f"Price Sensitive: {'Yes' if ann.is_price_sensitive else 'No'}")

    # Analyzer results
    if results["analyses"]:
        with st.expander(f"📄 **Analyzer Agent**: Analyzed {len(results['analyses'])} PDF(s)", expanded=True):
            for analysis in results["analyses"]:
                st.write(f"**Analysis #{analysis.id}**")
                st.write(f"- **Sentiment**: {analysis.sentiment}")
                st.write(f"- **Summary**: {analysis.summary[:200]}...")
                if analysis.key_insights:
                    st.write(f"- **Key Insights**: {', '.join(analysis.key_insights[:2])}")

    # Stock data
    if results["stock_data"]:
        with st.expander(f"📈 **Stock Agent**: Market data for {asx_code}", expanded=True):
            col1, col2, col3 = st.columns(3)
            stock_data = results["stock_data"]
            with col1:
                price = stock_data.price_at_announcement
                st.metric("Price at Announcement", f"${price:.2f}" if price else "N/A")
            with col2:
                perf_1m = stock_data.performance_1m_pct
                st.metric("1M Performance", f"{perf_1m:+.1f}%" if perf_1m else "N/A")
            with col3:
                perf_3m = stock_data.performance_3m_pct
                st.metric("3M Performance", f"{perf_3m:+.1f}%" if perf_3m else "N/A")

    # Evaluations
    if results["evaluations"]:
        with st.expander(f"📊 **Evaluation Agent**: Generated {len(results['evaluations'])} recommendation(s)", expanded=True):
            for evaluation in results["evaluations"]:
                rec = evaluation.recommendation or "N/A"
                rec_color = {
                    "BUY": "🟢",
                    "SPECULATIVE BUY": "🟠",
                    "HOLD": "🟡",
                    "SELL": "🔴",
                    "AVOID": "⚫"
                }.get(rec, "⚪")

                st.write(f"**Evaluation #{evaluation.id}**")
                st.write(f"- **Recommendation**: {rec_color} **{rec}**")

                if evaluation.confidence_score:
                    st.write(f"- **Confidence**: {evaluation.confidence_score * 100:.0f}%")

                if evaluation.recommendation_reasoning:
                    st.write(f"- **Reasoning**: {evaluation.recommendation_reasoning[:200]}...")

    # Trading decisions
    if results["trades"]:
        with st.expander(f"💰 **Trading Agent**: {len(results['trades'])} trade decision(s)", expanded=True):
            for trade in results["trades"]:
                st.write(f"**Trade #{trade.id}**")
                st.write(f"- **Type**: {trade.decision_type}")
                st.write(f"- **Status**: {trade.status}")
                if trade.price_at_decision:
                    st.write(f"- **Price**: ${trade.price_at_decision:.2f}")

                if trade.status == "PENDING":
                    st.info("⏸️ **Approval Required**: Switch to **Approvals** tab")


def generate_summary(results: Dict, asx_code: str) -> str:
    """Generate text summary of results."""
    lines = [f"## 📊 Pipeline Results for {asx_code}\n"]

    if results["announcements"]:
        lines.append(f"✅ Processed {len(results['announcements'])} announcement(s)")

    if results["analyses"]:
        lines.append(f"✅ Generated {len(results['analyses'])} analysis/analyses")

    if results["evaluations"]:
        lines.append(f"✅ Created {len(results['evaluations'])} evaluation(s)")

        # Show final recommendation
        if results["evaluations"]:
            final_eval = results["evaluations"][-1]
            rec = final_eval.recommendation or "N/A"
            lines.append(f"\n### Final Recommendation: **{rec}**")

            if final_eval.confidence_score:
                lines.append(f"Confidence: {final_eval.confidence_score * 100:.0f}%")

    if results["trades"]:
        pending_trades = [t for t in results["trades"] if t.status == "PENDING"]
        if pending_trades:
            lines.append(f"\n⏸️ **{len(pending_trades)} trade(s) awaiting approval** - Check the **Approvals** tab")

    return "\n".join(lines)


async def get_pending_trades() -> List[Dict]:
    """
    Get pending trades from approval service.

    Returns:
        List of pending trade dictionaries
    """
    approval_url = "http://localhost:8888/api/pending"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(approval_url)
        response.raise_for_status()
        return response.json()


async def approve_trade(ticket_id: str, approved: bool, notes: Optional[str] = None) -> Dict:
    """
    Approve or reject a trade.

    Args:
        ticket_id: Trade ticket ID
        approved: True to approve, False to reject
        notes: Optional notes

    Returns:
        Response dictionary
    """
    approval_url = "http://localhost:8888/api/approve"

    payload = {
        "ticket_id": ticket_id,
        "approved": approved,
        "notes": notes
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(approval_url, json=payload)
        response.raise_for_status()
        return response.json()


# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.title("📈 ASX Assistant")
    st.markdown("---")

    st.subheader("🎯 How to Use")
    st.markdown("""
    **Chat Tab:**
    - Ask me to analyze companies
    - Example: "Analyze BHP limit 5"
    - Example: "Check price-sensitive announcements for CBA"

    **Approvals Tab:**
    - Review pending trade recommendations
    - Approve or reject trades
    - See all trade details
    """)

    st.markdown("---")

    st.subheader("🔧 System Status")

    # Check if services are running
    services = {
        "Coordinator": f"http://localhost:{settings.coordinator_agent_port}/.well-known/agent-card.json",
        "Approval Service": "http://localhost:8888/api/pending"
    }

    for service_name, url in services.items():
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    st.success(f"✅ {service_name}")
                else:
                    st.warning(f"⚠️ {service_name} (status: {response.status_code})")
        except httpx.TimeoutException:
            st.warning(f"⏱️ {service_name} (timeout - may be busy)")
        except Exception as e:
            st.error(f"❌ {service_name} ({type(e).__name__})")

    st.markdown("---")
    st.caption("Multi-Agent Investment System v0.2.0")


# ============================================================================
# MAIN UI - TABS
# ============================================================================

# Check for pending trades (for badge notification)
try:
    pending_count = len(asyncio.run(get_pending_trades()))
except:
    pending_count = 0

# Create tabs with notification badge
tab_labels = [
    "💬 Chat",
    f"✅ Approvals ({pending_count})" if pending_count > 0 else "✅ Approvals"
]

tab1, tab2 = st.tabs(tab_labels)

# ============================================================================
# TAB 1: CHAT INTERFACE
# ============================================================================

with tab1:
    st.header("💬 Chat with Investment Assistant")

    st.markdown("""
    Ask me to analyze ASX companies! I'll coordinate a team of specialized agents to:
    - 📋 Scrape price-sensitive announcements
    - 📄 Analyze PDFs with AI
    - 📈 Fetch stock performance data
    - 📊 Generate investment recommendations
    - 💰 Create trade proposals (subject to your approval)
    """)

    st.markdown("---")

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "processing" not in st.session_state:
        st.session_state.processing = False

    if "current_request" not in st.session_state:
        st.session_state.current_request = None

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    user_input = st.chat_input("Ask me to analyze a company (e.g., 'Analyze BHP limit 5')", disabled=st.session_state.processing)

    if user_input and not st.session_state.processing:
        # Add user message to chat
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Extract ASX code
        asx_code = extract_asx_code(user_input)

        if not asx_code:
            error_msg = "❌ Could not identify ASX code in your message. Please include a stock ticker (e.g., BHP, CBA, RIO)."
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            st.rerun()
        else:
            # Set processing state
            st.session_state.processing = True
            st.session_state.current_request = {
                "asx_code": asx_code,
                "start_time": datetime.now(),
                "task_id": str(uuid.uuid4())
            }
            st.rerun()

    # Handle active processing
    if st.session_state.processing and st.session_state.current_request:
        request_info = st.session_state.current_request
        asx_code = request_info["asx_code"]
        start_time = request_info["start_time"]
        task_id = request_info["task_id"]

        with st.chat_message("assistant"):
            # Send request if not already sent
            if request_info.get("sent", False) is False:
                with st.spinner("📤 Sending request to coordinator..."):
                    try:
                        # Get the last user message
                        last_user_msg = [m for m in st.session_state.messages if m["role"] == "user"][-1]["content"]

                        # Fire-and-forget: send request but don't wait for response
                        asyncio.run(send_coordinator_request_fire_and_forget(last_user_msg, task_id))

                        # Mark as sent
                        st.session_state.current_request["sent"] = True
                        st.success(f"✅ Request sent to coordinator! Monitoring pipeline progress...")
                        st.info("💡 The coordinator is processing your request. Results will appear below as each agent completes.")

                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()

                        # Show detailed error in UI
                        st.error(f"**Error**: {str(e)}")
                        st.code(error_details, language="python")

                        # Also check the logs
                        st.info("💡 **Tip**: Check the terminal running Streamlit for detailed logs")

                        error_msg = f"❌ Failed to send request: {str(e)}"
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
                        st.session_state.processing = False
                        st.session_state.current_request = None

                        logger.error(f"Chat UI error: {e}")
                        logger.error(error_details)

                        st.rerun()

            # Poll for results
            st.write(f"🔄 **Monitoring pipeline progress for {asx_code}**...")

            progress_bar = st.progress(0)
            status_text = st.empty()
            
            logs_expander = st.expander("📂 Agent Logs", expanded=True)
            with logs_expander:
                logs_container = st.container()

            debug_expander = st.expander("🔍 Debug Info", expanded=False)
            results_container = st.container()

            max_wait = 120  # 2 minutes
            poll_interval = 3  # Check every 3 seconds
            elapsed = 0

            while elapsed < max_wait:
                # Update progress
                progress = min(elapsed / max_wait, 0.95)
                progress_bar.progress(progress)
                status_text.text(f"⏱️ Elapsed: {elapsed}s / {max_wait}s")

                # Get current results and logs
                results = get_pipeline_results(asx_code, start_time, task_id=task_id)
                logs = get_log_messages(task_id)

                # Display logs
                with logs_container:
                    st.empty()
                    if logs:
                        for log in logs:
                            st.text(f"[{log.created_at.strftime('%H:%M:%S')}] [{log.agent_name}] {log.message}")
                    else:
                        st.text("No logs yet...")

                # Show debug info
                with debug_expander:
                    st.write(f"**Poll #{elapsed // poll_interval}** at {datetime.now().strftime('%H:%M:%S')}")
                    st.json({
                        "announcements": len(results["announcements"]),
                        "analyses": len(results["analyses"]),
                        "stock_data": results["stock_data"] is not None,
                        "evaluations": len(results["evaluations"]),
                        "trades": len(results["trades"])
                    })

                # Display results
                with results_container:
                    st.empty()  # Clear previous
                    display_results(results, asx_code)

                # Check if complete
                if is_pipeline_complete(results):
                    progress_bar.progress(1.0)
                    status_text.text("✅ Pipeline complete!")

                    # Generate summary
                    summary = generate_summary(results, asx_code)
                    st.markdown("---")
                    st.markdown(summary)

                    # Add to chat history
                    full_response = f"{summary}\n\n_Check expanders above for detailed results_"
                    st.session_state.messages.append({"role": "assistant", "content": full_response})

                    # Clear processing state
                    st.session_state.processing = False
                    st.session_state.current_request = None

                    time.sleep(1)
                    st.rerun()

                # Wait before next poll
                time.sleep(poll_interval)
                elapsed += poll_interval

            # Timeout
            if st.session_state.processing:
                status_text.text("⏱️ Timeout - showing partial results")
                summary = generate_summary(results, asx_code)
                st.warning("⏱️ Pipeline monitoring timed out. Showing partial results.")
                st.markdown(summary)

                timeout_msg = f"{summary}\n\n⚠️ Pipeline may still be running. Check the database or Approvals tab."
                st.session_state.messages.append({"role": "assistant", "content": timeout_msg})

                st.session_state.processing = False
                st.session_state.current_request = None
                st.rerun()

    # Clear chat button
    if st.session_state.messages and not st.session_state.processing:
        if st.button("🗑️ Clear Chat History"):
            st.session_state.messages = []
            st.rerun()


# ============================================================================
# TAB 2: APPROVALS INTERFACE
# ============================================================================

with tab2:
    st.header("✅ Pending Trade Approvals")

    st.markdown("""
    Review and approve/reject trade recommendations from the investment pipeline.
    """)

    st.markdown("---")

    # Refresh button
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Refresh", type="primary"):
            st.rerun()

    with col2:
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    st.markdown("---")

    # Load pending trades
    try:
        pending_trades = asyncio.run(get_pending_trades())

        if not pending_trades:
            st.info("✅ All caught up! No pending trades to approve.")
        else:
            st.success(f"📋 **{len(pending_trades)} pending trade(s)** awaiting your approval")

            # Display each trade as a card
            for trade in pending_trades:
                with st.container(border=True):
                    # Header
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.subheader(f"{trade['asx_code']} - {trade['decision_type']}")
                    with col2:
                        # Decision badge with color
                        decision_colors = {
                            "BUY": "🟢",
                            "SELL": "🔴",
                            "HOLD": "🟡",
                            "SPECULATIVE BUY": "🟠"
                        }
                        badge = decision_colors.get(trade['decision'], "⚪")
                        st.markdown(f"### {badge} {trade['decision']}")

                    # Trade details
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Price", f"${trade['price_at_decision']:.2f}" if trade['price_at_decision'] else "N/A")
                    with col2:
                        confidence = trade['recommendation_score'] * 100 if trade['recommendation_score'] else 0
                        st.metric("Confidence", f"{confidence:.0f}%")
                    with col3:
                        created = datetime.fromisoformat(trade['created_at'])
                        st.metric("Created", created.strftime("%H:%M:%S"))

                    # Reasoning
                    with st.expander("📝 View Reasoning", expanded=True):
                        st.markdown(trade['reasoning'] or "No reasoning provided")

                    # Ticket ID (small text)
                    st.caption(f"Ticket ID: `{trade['ticket_id']}`")

                    # Notes input
                    notes_key = f"notes_{trade['ticket_id']}"
                    notes = st.text_input(
                        "Optional notes:",
                        key=notes_key,
                        placeholder="Add your reason for approval/rejection..."
                    )

                    # Action buttons
                    col1, col2, col3 = st.columns([2, 2, 6])

                    with col1:
                        if st.button("✅ Approve", key=f"approve_{trade['ticket_id']}", type="primary", use_container_width=True):
                            with st.spinner("Processing approval..."):
                                try:
                                    result = asyncio.run(approve_trade(
                                        ticket_id=trade['ticket_id'],
                                        approved=True,
                                        notes=notes
                                    ))
                                    st.success(f"✅ {result['message']}")
                                    st.balloons()
                                    # Reload after 2 seconds
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")

                    with col2:
                        if st.button("❌ Reject", key=f"reject_{trade['ticket_id']}", use_container_width=True):
                            with st.spinner("Processing rejection..."):
                                try:
                                    result = asyncio.run(approve_trade(
                                        ticket_id=trade['ticket_id'],
                                        approved=False,
                                        notes=notes
                                    ))
                                    st.warning(f"❌ {result['message']}")
                                    # Reload after 2 seconds
                                    time.sleep(2)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ Error: {str(e)}")

                    st.markdown("---")

    except httpx.ConnectError:
        st.error("❌ **Approval Service Offline**")
        st.markdown("""
        The approval service is not running. Please start it:
        ```bash
        python approval_service.py
        ```
        """)
    except Exception as e:
        st.error(f"❌ Error loading pending trades: {str(e)}")


# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.caption("Built with Streamlit • Powered by Google ADK & Gemini 2.0 Flash")
