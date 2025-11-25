#!/usr/bin/env python3
"""
Trade Approval Service - FastAPI Web UI for Human-in-the-Loop Trade Approval

This service provides a web interface for humans to approve/reject pending trades.
It queries the database for pending decisions and calls the trading agent's
approve_trade function via A2A protocol.

Usage:
    python approval_service.py

Access:
    http://localhost:8888/approvals - Web UI for approvals
    http://localhost:8888/api/pending - API to list pending trades
    http://localhost:8888/api/approve - API to approve/reject trades
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import from models and utils
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models.database import get_db_session
from models.orm_models import TradingDecision
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="ASX Trading Approval Service",
    description="Human-in-the-Loop approval for paper trading decisions",
    version="1.0.0"
)

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PendingTrade(BaseModel):
    """Pending trade decision for approval"""
    id: str
    ticket_id: str
    asx_code: str
    decision: str
    decision_type: str
    price_at_decision: Optional[float]
    recommendation_score: Optional[float]
    reasoning: str
    created_at: str

class ApprovalRequest(BaseModel):
    """Approval/rejection request"""
    ticket_id: str
    approved: bool
    notes: Optional[str] = None

class ApprovalResponse(BaseModel):
    """Approval response"""
    status: str
    message: str
    trade_details: Optional[Dict[str, Any]] = None

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/api/pending", response_model=List[PendingTrade])
async def get_pending_trades():
    """
    Get all pending trade decisions awaiting approval.

    Returns:
        List of pending trades with details
    """
    logger.info("📋 API: Fetching pending trades")

    with get_db_session() as db:
        pending = db.query(TradingDecision).filter(
            TradingDecision.status == "PENDING"
        ).order_by(TradingDecision.created_at.desc()).all()

        trades = [
            PendingTrade(
                id=str(d.id),
                ticket_id=d.ticket_id or "",
                asx_code=d.asx_code,
                decision=d.decision,
                decision_type=d.decision_type,
                price_at_decision=d.price_at_decision,
                recommendation_score=d.recommendation_score,
                reasoning=d.reasoning or "No reasoning provided",
                created_at=d.created_at.isoformat() if d.created_at else ""
            )
            for d in pending
        ]

        logger.info(f"✅ Found {len(trades)} pending trades")
        return trades


@app.post("/api/approve", response_model=ApprovalResponse)
async def approve_trade(request: ApprovalRequest):
    """
    Approve or reject a pending trade.

    This calls the trading agent's approve_trade function via A2A protocol.

    Args:
        request: Approval request with ticket_id, approved flag, and optional notes

    Returns:
        Approval response with execution status
    """
    logger.info(f"{'✅' if request.approved else '❌'} API: Processing approval for ticket {request.ticket_id}")
    logger.info(f"   Approved: {request.approved}")
    logger.info(f"   Notes: {request.notes or 'None'}")

    try:
        # Retrieve the task_id from the trading decision
        task_id = None
        with get_db_session() as db:
            decision = db.query(TradingDecision).filter(
                TradingDecision.ticket_id == request.ticket_id
            ).first()
            if decision and decision.task_id:
                task_id = decision.task_id
                logger.info(f"   Found task_id: {task_id}")
            else:
                logger.warning(f"   No task_id found for ticket {request.ticket_id}")

        # Call trading agent's approve_trade function via A2A
        trading_agent_url = settings.get_agent_url("trading")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Build A2A message to call approve_trade
            import uuid
            message_id = str(uuid.uuid4())

            # Build prompt for the agent to call approve_trade
            prompt = f"""Use the approve_trade tool with the following parameters:
- ticket_id: {request.ticket_id}
- approved: {request.approved}
- approved_by: human_via_web_ui
- notes: {request.notes or 'No notes provided'}
- task_id: {task_id}

Execute the approve_trade function now."""

            payload = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": message_id,
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                },
                "id": str(uuid.uuid4())
            }

            logger.info(f"   📞 Calling trading agent approve_trade via A2A...")
            response = await client.post(trading_agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            # Extract task_id
            task_id = result.get("result", {}).get("id")
            if not task_id:
                raise RuntimeError(f"No task_id received from trading agent: {result}")

            # Poll for result
            logger.info(f"   ⏳ Polling for result (task_id: {task_id[:8]}...)")
            for _ in range(30):  # Poll for up to 30 seconds
                await asyncio.sleep(1)

                poll_payload = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                    "id": str(uuid.uuid4())
                }

                poll_response = await client.post(trading_agent_url, json=poll_payload)
                poll_response.raise_for_status()
                poll_result = poll_response.json()

                task_data = poll_result.get("result", {})
                task_status = task_data.get("status", {})
                state = task_status.get("state", "unknown")

                if state == "completed":
                    logger.info(f"   ✅ Trading agent completed approval")

                    # Extract the approve_trade response from history
                    history = task_data.get("history", [])
                    for hist_item in reversed(history):
                        if hist_item.get("role") == "agent":
                            parts = hist_item.get("parts", [])
                            for part in parts:
                                if "data" in part and part.get("metadata", {}).get("adk_type") == "function_response":
                                    trade_response = part["data"].get("response", {})
                                    logger.info(f"   📊 Trade execution: {trade_response.get('status', 'UNKNOWN')}")

                                    return ApprovalResponse(
                                        status="success",
                                        message=trade_response.get("message", "Trade processed successfully"),
                                        trade_details=trade_response
                                    )

                    # If we didn't find the response, return a generic success
                    return ApprovalResponse(
                        status="success",
                        message="Approval processed successfully",
                        trade_details=None
                    )

                elif state == "failed":
                    error = task_status.get("error", "Unknown error")
                    logger.error(f"   ❌ Trading agent failed: {error}")
                    raise RuntimeError(f"Trading agent failed: {error}")

            # Timeout
            logger.warning(f"   ⏱️  Timeout waiting for trading agent response")
            return ApprovalResponse(
                status="pending",
                message="Approval submitted, but response timed out. Check trade history.",
                trade_details=None
            )

    except Exception as e:
        logger.error(f"   ❌ Approval failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
async def root():
    """Redirect to approvals page"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="refresh" content="0; url=/approvals" />
    </head>
    <body>
        <p>Redirecting to <a href="/approvals">approval interface</a>...</p>
    </body>
    </html>
    """


@app.get("/approvals", response_class=HTMLResponse)
async def approvals_ui(request: Request):
    """
    Web UI for approving/rejecting pending trades.

    Returns:
        HTML page with approval interface
    """
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Trade Approvals - ASX Trading System</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }

            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
            }

            .header {
                text-align: center;
                color: white;
                margin-bottom: 30px;
            }

            .header h1 {
                font-size: 2.5em;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
            }

            .header p {
                font-size: 1.1em;
                opacity: 0.9;
            }

            .refresh-btn {
                display: block;
                margin: 20px auto;
                padding: 12px 30px;
                background: white;
                color: #667eea;
                border: none;
                border-radius: 25px;
                font-size: 1em;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                transition: transform 0.2s, box-shadow 0.2s;
            }

            .refresh-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 12px rgba(0,0,0,0.15);
            }

            .refresh-btn:active {
                transform: translateY(0);
            }

            #loading {
                text-align: center;
                color: white;
                font-size: 1.2em;
                padding: 40px;
            }

            #pending-trades {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
                gap: 20px;
            }

            .trade-card {
                background: white;
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                transition: transform 0.3s, box-shadow 0.3s;
            }

            .trade-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.3);
            }

            .trade-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f0f0f0;
            }

            .stock-symbol {
                font-size: 1.8em;
                font-weight: bold;
                color: #667eea;
            }

            .decision-badge {
                padding: 6px 15px;
                border-radius: 20px;
                font-size: 0.9em;
                font-weight: 600;
                text-transform: uppercase;
            }

            .decision-badge.buy {
                background: #10b981;
                color: white;
            }

            .decision-badge.sell {
                background: #ef4444;
                color: white;
            }

            .decision-badge.hold {
                background: #f59e0b;
                color: white;
            }

            .trade-details {
                margin-bottom: 20px;
            }

            .detail-row {
                display: flex;
                justify-content: space-between;
                padding: 10px 0;
                border-bottom: 1px solid #f0f0f0;
            }

            .detail-label {
                color: #666;
                font-weight: 500;
            }

            .detail-value {
                color: #333;
                font-weight: 600;
            }

            .reasoning {
                background: #f9fafb;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
                color: #555;
                font-size: 0.95em;
                line-height: 1.6;
                max-height: 120px;
                overflow-y: auto;
            }

            .notes-input {
                width: 100%;
                padding: 12px;
                border: 2px solid #e5e7eb;
                border-radius: 8px;
                font-size: 0.95em;
                margin-bottom: 15px;
                transition: border-color 0.3s;
            }

            .notes-input:focus {
                outline: none;
                border-color: #667eea;
            }

            .action-buttons {
                display: flex;
                gap: 10px;
            }

            .btn {
                flex: 1;
                padding: 14px 20px;
                border: none;
                border-radius: 8px;
                font-size: 1em;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .btn-approve {
                background: #10b981;
                color: white;
            }

            .btn-approve:hover {
                background: #059669;
                transform: scale(1.02);
            }

            .btn-reject {
                background: #ef4444;
                color: white;
            }

            .btn-reject:hover {
                background: #dc2626;
                transform: scale(1.02);
            }

            .btn:active {
                transform: scale(0.98);
            }

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .no-trades {
                text-align: center;
                color: white;
                font-size: 1.3em;
                padding: 60px 20px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }

            .no-trades-icon {
                font-size: 4em;
                margin-bottom: 20px;
            }

            @keyframes spin {
                to { transform: rotate(360deg); }
            }

            .spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid rgba(255,255,255,0.3);
                border-radius: 50%;
                border-top-color: white;
                animation: spin 1s linear infinite;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Trade Approval Dashboard</h1>
                <p>Human-in-the-Loop Trading Decisions</p>
            </div>

            <button class="refresh-btn" onclick="loadPendingTrades()">
                <span id="refresh-icon">🔄</span> Refresh Pending Trades
            </button>

            <div id="loading">
                <div class="spinner"></div>
                <p>Loading pending trades...</p>
            </div>

            <div id="pending-trades" style="display: none;"></div>
        </div>

        <script>
            async function loadPendingTrades() {
                const loading = document.getElementById('loading');
                const tradesContainer = document.getElementById('pending-trades');
                const refreshIcon = document.getElementById('refresh-icon');

                loading.style.display = 'block';
                tradesContainer.style.display = 'none';
                refreshIcon.classList.add('spinner');

                try {
                    const response = await fetch('/api/pending');
                    const trades = await response.json();

                    tradesContainer.innerHTML = '';

                    if (trades.length === 0) {
                        tradesContainer.innerHTML = `
                            <div class="no-trades">
                                <div class="no-trades-icon">✅</div>
                                <p>All caught up! No pending trades to approve.</p>
                            </div>
                        `;
                    } else {
                        trades.forEach(trade => {
                            const card = createTradeCard(trade);
                            tradesContainer.appendChild(card);
                        });
                    }

                    loading.style.display = 'none';
                    tradesContainer.style.display = 'grid';
                } catch (error) {
                    loading.innerHTML = `<p style="color: #ef4444;">❌ Error loading trades: ${error.message}</p>`;
                } finally {
                    refreshIcon.classList.remove('spinner');
                }
            }

            function createTradeCard(trade) {
                const card = document.createElement('div');
                card.className = 'trade-card';
                card.id = `trade-${trade.ticket_id}`;

                const decisionClass = trade.decision.toLowerCase();
                const price = trade.price_at_decision ? `$${trade.price_at_decision.toFixed(2)}` : 'N/A';
                const confidence = trade.recommendation_score ? `${(trade.recommendation_score * 100).toFixed(0)}%` : 'N/A';
                const createdAt = new Date(trade.created_at).toLocaleString();

                card.innerHTML = `
                    <div class="trade-header">
                        <div class="stock-symbol">${trade.asx_code}</div>
                        <div class="decision-badge ${decisionClass}">${trade.decision_type}</div>
                    </div>

                    <div class="trade-details">
                        <div class="detail-row">
                            <span class="detail-label">Price</span>
                            <span class="detail-value">${price}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Confidence</span>
                            <span class="detail-value">${confidence}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Created</span>
                            <span class="detail-value">${createdAt}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Ticket</span>
                            <span class="detail-value">${trade.ticket_id}</span>
                        </div>
                    </div>

                    <div class="reasoning">
                        <strong>Reasoning:</strong><br>
                        ${trade.reasoning || 'No reasoning provided'}
                    </div>

                    <input type="text"
                           class="notes-input"
                           id="notes-${trade.ticket_id}"
                           placeholder="Optional notes (reason for approval/rejection)...">

                    <div class="action-buttons">
                        <button class="btn btn-approve" onclick="approveTrade('${trade.ticket_id}', true)">
                            ✅ Approve
                        </button>
                        <button class="btn btn-reject" onclick="approveTrade('${trade.ticket_id}', false)">
                            ❌ Reject
                        </button>
                    </div>
                `;

                return card;
            }

            async function approveTrade(ticketId, approved) {
                const card = document.getElementById(`trade-${ticketId}`);
                const buttons = card.querySelectorAll('.btn');
                const notesInput = document.getElementById(`notes-${ticketId}`);
                const notes = notesInput.value.trim();

                // Disable buttons
                buttons.forEach(btn => btn.disabled = true);

                try {
                    const response = await fetch('/api/approve', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            ticket_id: ticketId,
                            approved: approved,
                            notes: notes || null
                        })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${await response.text()}`);
                    }

                    const result = await response.json();

                    // Show success message
                    card.style.background = approved ? '#d1fae5' : '#fee2e2';
                    card.innerHTML = `
                        <div style="text-align: center; padding: 40px;">
                            <div style="font-size: 3em; margin-bottom: 15px;">
                                ${approved ? '✅' : '❌'}
                            </div>
                            <h3 style="color: ${approved ? '#10b981' : '#ef4444'}; margin-bottom: 10px;">
                                Trade ${approved ? 'Approved' : 'Rejected'}
                            </h3>
                            <p style="color: #666;">${result.message}</p>
                        </div>
                    `;

                    // Reload trades after 2 seconds
                    setTimeout(loadPendingTrades, 2000);
                } catch (error) {
                    alert(`Error: ${error.message}`);
                    buttons.forEach(btn => btn.disabled = false);
                }
            }

            // Load trades on page load
            loadPendingTrades();

            // Auto-refresh every 30 seconds
            setInterval(loadPendingTrades, 30000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info("🌐 Starting Trade Approval Service")
    logger.info("=" * 60)
    logger.info(f"   URL: http://localhost:8888")
    logger.info(f"   Web UI: http://localhost:8888/approvals")
    logger.info(f"   API Docs: http://localhost:8888/docs")
    logger.info("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
