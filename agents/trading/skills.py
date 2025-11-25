# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Skills for Trading Agent.

Implements human-in-the-loop approval workflow.
"""
import uuid
from typing import Any, Optional
from datetime import datetime

from models.database import get_db_session
from models.orm_models import TradingDecision
from utils.config import get_settings
from utils.logging import get_logger
from utils.db_logger import log_to_db

logger = get_logger()
settings = get_settings()


def execute_trade(
    asx_code: str,
    company_id: str,
    recommendation: str,
    price: float,
    analysis_summary: str,
    sentiment: str,
    confidence_score: float,
    reasoning: str,
    announcement_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute a trade with human approval (creates pending decision).

    This function implements the Human-in-the-Loop workflow:
    1. Creates a pending trading decision in the database
    2. Returns {"status": "pending", "ticket_id": "..."} immediately
    3. Human approves/rejects via the approval UI
    4. Approval service calls approve_trade to execute if approved

    Args:
        asx_code: Stock ticker (e.g., "BHP")
        company_id: Company database ID
        recommendation: Investment recommendation (BUY/HOLD/SELL/SPECULATIVE BUY/AVOID)
        price: Current stock price
        analysis_summary: Brief analysis summary
        sentiment: Sentiment (BULLISH/BEARISH/NEUTRAL)
        confidence_score: Confidence level (0-1)
        reasoning: Recommendation reasoning
        announcement_id: Announcement ID (optional)
        task_id: The ID for the current request, used for logging.

    Returns:
        dict with status, ticket_id, and trade details
    """
    log_to_db(task_id, "trading", f"💰 execute_trade called for {asx_code} (recommendation: {recommendation})")
    logger.info(f"💰 execute_trade called for {asx_code} (recommendation: {recommendation})")
    log_to_db(task_id, "trading", f"   Price: ${price}, Confidence: {confidence_score:.0%}")
    logger.info(f"   Price: ${price}, Confidence: {confidence_score:.0%}")

    # Normalize recommendation to simple decision (BUY/SELL/HOLD)
    simple_decision = recommendation.replace("SPECULATIVE ", "").replace("AVOID", "SELL")

    # Create decision record in database (PENDING status)
    ticket_id = f"trade-{uuid.uuid4().hex[:12]}"

    with get_db_session() as db:
        decision = TradingDecision(
            company_id=company_id,
            announcement_id=announcement_id,
            asx_code=asx_code,
            decision=simple_decision,  # BUY/SELL/HOLD
            decision_type=recommendation,  # Full recommendation
            status="PENDING",
            price_at_decision=price,
            recommendation_score=confidence_score,
            reasoning=reasoning,
            ticket_id=ticket_id,
            task_id=task_id,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        decision_id = str(decision.id)
        log_to_db(task_id, "trading", f"✅ Created trading decision {decision_id} with status PENDING")
        logger.info(f"✅ Created trading decision {decision_id} with status PENDING")
        log_to_db(task_id, "trading", f"   Ticket ID: {ticket_id}")
        logger.info(f"   Ticket ID: {ticket_id}")

    # Return pending response immediately
    # This signals to the root agent that human approval is needed
    return {
        "status": "pending",
        "ticket_id": ticket_id,
        "decision_id": decision_id,
        "asx_code": asx_code,
        "recommendation": recommendation,
        "price": price,
        "confidence_score": confidence_score,
        "message": f"Trade decision created for {asx_code}. Awaiting human approval (Ticket: {ticket_id})",
    }


def get_trade_history(limit: int = 10) -> dict[str, Any]:
    """
    Retrieve recent trading decisions.

    Args:
        limit: Maximum number of decisions to return (default: 10)

    Returns:
        dict with count and list of trading decisions
    """
    logger.info(f"📜 Fetching last {limit} trading decisions")

    with get_db_session() as db:
        decisions = (
            db.query(TradingDecision)
            .order_by(TradingDecision.created_at.desc())
            .limit(limit)
            .all()
        )

        decision_list = [
            {
                "id": str(d.id),
                "ticket_id": d.ticket_id,
                "asx_code": d.asx_code,
                "decision": d.decision,
                "decision_type": d.decision_type,
                "status": d.status,
                "price": d.price_at_decision,
                "execution_price": d.execution_price,
                "quantity": d.quantity,
                "approved_by": d.approved_by,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "approved_at": d.approved_at.isoformat() if d.approved_at else None,
                "executed_at": d.executed_at.isoformat() if d.executed_at else None,
            }
            for d in decisions
        ]

        logger.info(f"✅ Found {len(decision_list)} trading decisions")
        return {"count": len(decision_list), "decisions": decision_list}


def approve_trade(
    ticket_id: str,
    approved: bool,
    approved_by: str = "human",
    notes: Optional[str] = None,
    task_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Approve or reject a pending trade decision.

    This function is called by the root agent after getting human approval.
    It executes the paper trade if approved and updates the database.

    Args:
        ticket_id: Ticket ID of the pending decision
        approved: True to approve, False to reject
        approved_by: Who approved (default: "human")
        notes: Optional approval notes
        task_id: The ID for the current request, used for logging.

    Returns:
        dict with execution status and details
    """
    log_to_db(task_id, "trading", f"{'✅' if approved else '❌'} approve_trade called for ticket {ticket_id}")
    logger.info(f"{'✅' if approved else '❌'} approve_trade called for ticket {ticket_id}")
    log_to_db(task_id, "trading", f"   Approved: {approved}, By: {approved_by}")
    logger.info(f"   Approved: {approved}, By: {approved_by}")

    with get_db_session() as db:
        # Find the pending decision
        decision = db.query(TradingDecision).filter(
            TradingDecision.ticket_id == ticket_id,
            TradingDecision.status == "PENDING"
        ).first()

        if not decision:
            log_to_db(task_id, "trading", f"❌ No pending decision found for ticket {ticket_id}")
            logger.error(f"❌ No pending decision found for ticket {ticket_id}")
            return {
                "status": "error",
                "message": f"No pending decision found for ticket {ticket_id}"
            }

        # Update decision with approval
        decision.status = "APPROVED" if approved else "REJECTED"
        decision.approved_by = approved_by
        decision.approved_at = datetime.utcnow()
        decision.human_feedback = notes

        if approved:
            # Execute paper trade
            decision.executed = True
            decision.executed_at = datetime.utcnow()
            decision.execution_price = decision.price_at_decision
            decision.quantity = 100  # Paper trade quantity (fixed for now)
            decision.trade_amount = decision.price_at_decision * 100 if decision.price_at_decision else 10000

            db.commit()
            db.refresh(decision)

            log_to_db(task_id, "trading", f"💸 Paper trade EXECUTED:")
            logger.info(f"💸 Paper trade EXECUTED:")
            log_to_db(task_id, "trading", f"   Stock: {decision.asx_code}")
            logger.info(f"   Stock: {decision.asx_code}")
            log_to_db(task_id, "trading", f"   Quantity: {decision.quantity} shares")
            logger.info(f"   Quantity: {decision.quantity} shares")
            log_to_db(task_id, "trading", f"   Price: ${decision.execution_price}")
            logger.info(f"   Price: ${decision.execution_price}")
            log_to_db(task_id, "trading", f"   Total: ${decision.trade_amount}")
            logger.info(f"   Total: ${decision.trade_amount}")

            return {
                "status": "executed",
                "ticket_id": ticket_id,
                "decision_id": str(decision.id),
                "asx_code": decision.asx_code,
                "quantity": decision.quantity,
                "execution_price": decision.execution_price,
                "trade_amount": decision.trade_amount,
                "message": f"Paper trade executed: {decision.quantity} shares of {decision.asx_code} @ ${decision.execution_price}"
            }
        else:
            # Rejected
            db.commit()
            db.refresh(decision)

            log_to_db(task_id, "trading", f"🚫 Trade REJECTED for {decision.asx_code}")
            logger.info(f"🚫 Trade REJECTED for {decision.asx_code}")
            log_to_db(task_id, "trading", f"   Reason: {notes or 'No reason provided'}")
            logger.info(f"   Reason: {notes or 'No reason provided'}")

            return {
                "status": "rejected",
                "ticket_id": ticket_id,
                "decision_id": str(decision.id),
                "asx_code": decision.asx_code,
                "message": f"Trade rejected for {decision.asx_code}. Reason: {notes or 'No reason provided'}"
            }
