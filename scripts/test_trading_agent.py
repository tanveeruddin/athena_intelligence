"""
Test script for Trading Agent with Human-in-the-Loop Approval.

This script demonstrates:
1. Creating trading decisions (via pipeline)
2. Checking pending approvals
3. Approving/rejecting decisions manually
4. How the ADK resumability pattern works

Usage:
  # List pending approvals
  python scripts/test_trading_agent.py --list-pending

  # Approve a specific decision
  python scripts/test_trading_agent.py --approve <decision_id>

  # Reject a specific decision
  python scripts/test_trading_agent.py --reject <decision_id> --notes "Reason for rejection"
"""

import asyncio
import sys
import httpx
import json
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import get_settings
from utils.logging import get_logger
from models.database import get_db_session
from models.orm_models import TradingDecision

logger = get_logger()
settings = get_settings()


async def list_pending_approvals():
    """
    Lists all trading decisions awaiting human approval.
    """
    print(f"\n{'='*80}")
    print(f"📋 PENDING TRADING APPROVALS")
    print(f"{'='*80}\n")

    # Check database directly first
    with get_db_session() as db:
        pending = db.query(TradingDecision).filter(TradingDecision.status == "PENDING").all()

        if not pending:
            print("✅ No pending approvals found.")
            print("\n💡 TIP: Run the pipeline with trading enabled to create trading decisions:")
            print("   python scripts/test_pipeline_e2e.py --asx-code WES --limit 1")
            return []

        print(f"Found {len(pending)} pending approval(s) in database:\n")

        for i, decision in enumerate(pending, 1):
            print(f"{i}. Decision ID: {decision.id}")
            print(f"   ASX Code: {decision.asx_code}")
            print(f"   Decision Type: {decision.decision_type}")
            print(f"   Price: ${decision.price_at_decision}")
            print(f"   Confidence: {decision.recommendation_score:.0%}")
            print(f"   Reasoning: {decision.reasoning[:100]}...")
            print(f"   Created: {decision.created_at}")
            print()

        return pending

    # Also test via A2A protocol
    agent_url = settings.get_agent_url("trading")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Test if agent is running
            try:
                health_response = await client.get(f"{agent_url.replace('/a2a', '')}/health")
                if health_response.status_code != 200:
                    print("⚠️  Trading agent is not running. Start it with:")
                    print("   python -m agents.trading.agent")
                    return pending
            except:
                print("⚠️  Trading agent is not running. Start it with:")
                print("   python -m agents.trading.agent")
                return pending

            # Call get_pending_approvals via A2A
            prompt = "Use the get_pending_approvals_skill tool with limit 20"

            payload = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": str(uuid.uuid4()),
                        "role": "user",
                        "parts": [{"text": prompt}]
                    }
                },
                "id": str(uuid.uuid4())
            }

            response = await client.post(agent_url, json=payload)
            response.raise_for_status()
            result = response.json()

            task_id = result.get("result", {}).get("id")
            if not task_id:
                return pending

            # Poll for completion
            for _ in range(10):
                await asyncio.sleep(2)

                poll_payload = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                    "id": str(uuid.uuid4())
                }

                response = await client.post(agent_url, json=poll_payload)
                poll_result = response.json()

                state = poll_result.get("result", {}).get("status", {}).get("state", "unknown")

                if state == "completed":
                    print("\n✅ Trading agent confirmed pending approvals via A2A protocol")
                    break
                elif state == "failed":
                    print("\n❌ Trading agent query failed")
                    break

    except Exception as e:
        print(f"\n⚠️  Could not query trading agent via A2A: {e}")

    return pending


async def approve_decision(decision_id: str, notes: str = None):
    """
    Approves a trading decision manually.

    Note: This is the fallback manual approval method.
    The primary approval mechanism is via ADK's context.request_approval()
    which pauses execution and waits for human response through the ADK interface.
    """
    print(f"\n{'='*80}")
    print(f"✅ APPROVING TRADING DECISION")
    print(f"{'='*80}\n")

    print(f"Decision ID: {decision_id}")
    print(f"Approval Notes: {notes or 'None'}\n")

    # Update database directly
    with get_db_session() as db:
        decision = db.query(TradingDecision).filter(TradingDecision.id == decision_id).first()

        if not decision:
            print(f"❌ Error: Decision {decision_id} not found in database.")
            return

        if decision.status != "PENDING":
            print(f"⚠️  Warning: Decision status is '{decision.status}', not PENDING")
            print(f"   This decision may have already been processed.")
            return

        print(f"📊 Decision Details:")
        print(f"   ASX Code: {decision.asx_code}")
        print(f"   Type: {decision.decision_type}")
        print(f"   Price: ${decision.price_at_decision}")
        print(f"   Reasoning: {decision.reasoning[:200]}...\n")

        # Update status
        from datetime import datetime
        decision.status = "APPROVED"
        decision.human_approved = True
        decision.human_decision = "APPROVED"
        decision.human_feedback = notes or "Manual approval via test script"
        decision.approved_at = datetime.utcnow()
        decision.approved_by = "manual_test_script"

        # Execute paper trade
        decision.executed = True
        decision.executed_at = datetime.utcnow()
        decision.execution_price = decision.price_at_decision
        decision.quantity = 100
        decision.trade_amount = decision.price_at_decision * 100 if decision.price_at_decision else 10000

        db.commit()

        print(f"✅ Decision APPROVED successfully!")
        print(f"💸 Paper trade executed:")
        print(f"   Quantity: {decision.quantity} shares")
        print(f"   Price: ${decision.execution_price}")
        print(f"   Total: ${decision.trade_amount:.2f}")


async def reject_decision(decision_id: str, notes: str = None):
    """
    Rejects a trading decision manually.
    """
    print(f"\n{'='*80}")
    print(f"❌ REJECTING TRADING DECISION")
    print(f"{'='*80}\n")

    print(f"Decision ID: {decision_id}")
    print(f"Rejection Notes: {notes or 'None'}\n")

    # Update database directly
    with get_db_session() as db:
        decision = db.query(TradingDecision).filter(TradingDecision.id == decision_id).first()

        if not decision:
            print(f"❌ Error: Decision {decision_id} not found in database.")
            return

        if decision.status != "PENDING":
            print(f"⚠️  Warning: Decision status is '{decision.status}', not PENDING")
            return

        print(f"📊 Decision Details:")
        print(f"   ASX Code: {decision.asx_code}")
        print(f"   Type: {decision.decision_type}")
        print(f"   Price: ${decision.price_at_decision}\n")

        # Update status
        from datetime import datetime
        decision.status = "REJECTED"
        decision.human_approved = False
        decision.human_decision = "REJECTED"
        decision.human_feedback = notes or "Manual rejection via test script"
        decision.approved_at = datetime.utcnow()
        decision.approved_by = "manual_test_script"

        db.commit()

        print(f"✅ Decision REJECTED successfully!")
        print(f"🚫 No trade was executed.")


def print_help():
    """Prints help information about human approval process."""
    print(f"\n{'='*80}")
    print(f"📚 HUMAN APPROVAL PROCESS - HOW IT WORKS")
    print(f"{'='*80}\n")

    print("The trading agent uses ADK's resumability pattern for human-in-the-loop approval.\n")

    print("🔄 WORKFLOW:")
    print("1. Pipeline runs and creates a trading decision (status: PENDING)")
    print("2. Trading agent calls context.request_approval() and PAUSES")
    print("3. Human receives approval request via ADK interface")
    print("4. Human approves or rejects")
    print("5. Agent RESUMES and executes trade if approved\n")

    print("✅ HOW TO APPROVE (2 methods):\n")

    print("METHOD 1: ADK Resumable Approval (Primary)")
    print("   When the pipeline runs with trading enabled, the agent will pause")
    print("   and wait for approval. The ADK framework handles this automatically.")
    print("   You'll see an approval request in the agent logs.\n")

    print("METHOD 2: Manual Approval (Fallback)")
    print("   Use this script to manually approve/reject pending decisions:")
    print()
    print("   # List pending approvals")
    print("   python scripts/test_trading_agent.py --list-pending")
    print()
    print("   # Approve a decision")
    print("   python scripts/test_trading_agent.py --approve <decision_id>")
    print()
    print("   # Reject a decision")
    print("   python scripts/test_trading_agent.py --reject <decision_id> --notes 'Reason'\n")

    print("📊 CHECKING STATUS:")
    print("   All decisions are stored in the database (data/asx_scraper.db)")
    print("   Status values: PENDING, APPROVED, REJECTED\n")

    print("💡 TESTING:")
    print("   1. Enable trading in coordinator (uncomment trading section)")
    print("   2. Run pipeline: python scripts/test_pipeline_e2e.py --asx-code WES --limit 1")
    print("   3. Check for pending approvals: python scripts/test_trading_agent.py --list-pending")
    print("   4. Approve manually: python scripts/test_trading_agent.py --approve <id>\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Trading Agent and Human Approval Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show help and explanation
  python scripts/test_trading_agent.py --help-approval

  # List all pending approvals
  python scripts/test_trading_agent.py --list-pending

  # Approve a specific decision
  python scripts/test_trading_agent.py --approve abc123-def456

  # Reject a decision with notes
  python scripts/test_trading_agent.py --reject abc123-def456 --notes "Too risky"
        """
    )

    parser.add_argument("--list-pending", action="store_true", help="List all pending approvals")
    parser.add_argument("--approve", type=str, help="Approve a specific decision by ID")
    parser.add_argument("--reject", type=str, help="Reject a specific decision by ID")
    parser.add_argument("--notes", type=str, help="Add notes to approval/rejection")
    parser.add_argument("--help-approval", action="store_true", help="Show detailed approval process documentation")

    args = parser.parse_args()

    try:
        if args.help_approval:
            print_help()
        elif args.list_pending:
            asyncio.run(list_pending_approvals())
        elif args.approve:
            asyncio.run(approve_decision(args.approve, args.notes))
        elif args.reject:
            asyncio.run(reject_decision(args.reject, args.notes))
        else:
            # Default: list pending approvals
            asyncio.run(list_pending_approvals())
            print("\n💡 Use --help to see all options")
            print("   Use --help-approval to understand the approval process")

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
