#!/usr/bin/env python3
"""
End-to-End Pipeline Test Script (Full HTIL Workflow)

Tests the complete ASX ADK Gemini pipeline including HTIL workflow:
1. Starts required agents (6 agents: coordinator, scraper, analyzer, stock, evaluation, trading)
2. Waits for agents to be ready
3. Triggers the coordinator pipeline
4. Monitors progress (including HTIL approval workflow)
5. Verifies database records
6. Cleans up agents

Note: Trading agent is ENABLED. If BUY/SPECULATIVE BUY signal is detected,
the trading agent will create a pending approval. You can approve via the web UI at:
http://localhost:8888/approvals

Usage:
    python scripts/test_pipeline_e2e.py --asx-code BHP --limit 2
    python scripts/test_pipeline_e2e.py --asx-code CBA --limit 3
"""

import argparse
import asyncio
import httpx
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import get_settings
from utils.logging import get_logger
from models.database import get_db_session
from models.orm_models import Company, Announcement, Analysis, Evaluation, TradingDecision

logger = get_logger()
settings = get_settings()

# Agent configurations (All 6 A2A agents - trading now enabled for HTIL workflow)
AGENTS = {
    "coordinator": {"port": settings.coordinator_agent_port, "module": "agents.coordinator.main"},
    "scraper": {"port": settings.scraper_agent_port, "module": "agents.scraper.main"},
    "analyzer": {"port": settings.analyzer_agent_port, "module": "agents.analyzer.main"},
    "stock": {"port": settings.stock_agent_port, "module": "agents.stock.main"},
    "evaluation": {"port": settings.evaluation_agent_port, "module": "agents.evaluation.main"},
    "trading": {"port": settings.trading_agent_port, "module": "agents.trading.main"},  # ENABLED for HTIL workflow
}

class AgentManager:
    """Manages agent lifecycle: start, health check, stop."""

    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}

    def start_agent(self, name: str, config: Dict[str, Any]) -> bool:
        """Start an agent as a subprocess."""
        try:
            logger.info(f"🚀 Starting {name} agent on port {config['port']}...")
            process = subprocess.Popen(
                [sys.executable, "-m", config["module"]],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.processes[name] = process
            logger.info(f"✅ {name} agent started (PID: {process.pid})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to start {name} agent: {e}")
            return False

    async def check_agent_health(self, name: str, port: int, max_retries: int = 30) -> bool:
        """Check if agent is ready by polling /.well-known/agent-card.json"""
        url = f"http://localhost:{port}/.well-known/agent-card.json"

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        logger.info(f"✅ {name} agent is ready (port {port})")
                        return True
            except (httpx.ConnectError, httpx.TimeoutException):
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    logger.debug(f"⏳ Waiting for {name} agent... (attempt {attempt + 1}/{max_retries})")
                else:
                    logger.error(f"❌ {name} agent failed to start after {max_retries} attempts")
                    return False
        return False

    def stop_all_agents(self):
        """Stop all running agents."""
        logger.info("🛑 Stopping all agents...")
        for name, process in self.processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                logger.info(f"✅ {name} agent stopped")
            except subprocess.TimeoutExpired:
                process.kill()
                logger.warning(f"⚠️  {name} agent killed (didn't terminate gracefully)")
            except Exception as e:
                logger.error(f"❌ Error stopping {name} agent: {e}")


async def trigger_pipeline(asx_code: str, limit: int = 5, price_sensitive: bool = True) -> Dict[str, Any]:
    """Trigger the coordinator agent to run the pipeline."""
    logger.info(f"\n{'='*80}")
    logger.info(f"🚀 TRIGGERING PIPELINE: {asx_code}, limit={limit}, price_sensitive={price_sensitive}")
    logger.info(f"{'='*80}\n")

    coordinator_url = f"http://localhost:{settings.coordinator_agent_port}"

    # Build prompt for coordinator
    prompt = f"Run the announcement processing pipeline for ASX code {asx_code} with limit {limit} and price_sensitive_only={price_sensitive}."

    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": f"test_pipeline_{int(time.time())}",
                "role": "user",
                "parts": [{"text": prompt}]
            }
        },
        "id": "test_e2e_1"
    }

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:  # 10 minute timeout
            # Send task
            logger.info(f"📤 Sending pipeline request to coordinator...")
            response = await client.post(coordinator_url, json=payload)
            response.raise_for_status()
            result = response.json()

            task_id = result.get("result", {}).get("id")
            if not task_id:
                logger.error(f"❌ No task_id received: {result}")
                return {"error": "No task_id received"}

            logger.info(f"📋 Task ID: {task_id}")

            # Poll for completion
            poll_count = 0
            while True:
                await asyncio.sleep(5)  # Poll every 5 seconds
                poll_count += 1

                poll_payload = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": task_id},
                    "id": f"poll_{poll_count}"
                }

                response = await client.post(coordinator_url, json=poll_payload)
                response.raise_for_status()
                poll_result = response.json()

                task_data = poll_result.get("result", {})
                task_status = task_data.get("status", {})
                state = task_status.get("state", "unknown")

                logger.info(f"⏳ Pipeline status: {state.upper()} (poll #{poll_count})")

                if state == "completed":
                    logger.info(f"✅ Pipeline completed!")

                    # Extract results from history
                    history = task_data.get("history", [])
                    for hist_item in reversed(history):
                        if hist_item.get("role") == "agent":
                            parts = hist_item.get("parts", [])
                            for part in parts:
                                if "data" in part:
                                    data = part["data"]
                                    metadata = part.get("metadata", {})
                                    if metadata.get("adk_type") == "function_response":
                                        response_data = data.get("response", {})
                                        if "result" in response_data:
                                            return response_data["result"]

                    # Fallback: return last message
                    message = task_status.get("message", {})
                    parts = message.get("parts", [])
                    if parts and "text" in parts[0]:
                        return {"text_result": parts[0]["text"]}

                    return {"status": "completed", "note": "No structured result found"}

                if state == "failed":
                    error_msg = task_status.get("message", {})
                    logger.error(f"❌ Pipeline failed: {error_msg}")
                    return {"error": str(error_msg)}

                # Check for pending approval (trading agent)
                if "approval" in str(task_status).lower() or "pending" in str(task_status).lower():
                    logger.warning(f"⏸️  Pipeline waiting for human approval...")
                    logger.info(f"   Check trading agent logs for approval prompt")

    except Exception as e:
        logger.error(f"❌ Error triggering pipeline: {e}", exc_info=True)
        return {"error": str(e)}


def verify_database_records(asx_code: str) -> bool:
    """Verify that database records were created correctly."""
    # Ensure uppercase for consistency with database storage
    asx_code = asx_code.upper()

    logger.info(f"\n{'='*80}")
    logger.info(f"🔍 VERIFYING DATABASE RECORDS FOR {asx_code}")
    logger.info(f"{'='*80}\n")

    success = True

    with get_db_session() as db:
        # Check company
        company = db.query(Company).filter(Company.asx_code == asx_code).first()
        if company:
            logger.info(f"✅ Company found: {company.company_name} ({company.asx_code})")
        else:
            logger.error(f"❌ Company not found for {asx_code}")
            success = False

        if not company:
            return False

        # Check announcements
        announcements = db.query(Announcement).filter(
            Announcement.asx_code == asx_code
        ).all()
        logger.info(f"📋 Announcements: {len(announcements)} found")
        for ann in announcements[:3]:  # Show first 3
            logger.info(f"   - {ann.title[:60]}... ({ann.announcement_date.date() if ann.announcement_date else 'N/A'})")

        # Check analyses
        if announcements:
            analyses = db.query(Analysis).filter(
                Analysis.announcement_id.in_([a.id for a in announcements])
            ).all()
            logger.info(f"🔬 Analyses: {len(analyses)} found")
            for analysis in analyses[:3]:
                logger.info(f"   - Sentiment: {analysis.sentiment}, Summary: {analysis.summary[:50]}...")

            # Check evaluations
            evaluations = db.query(Evaluation).filter(
                Evaluation.announcement_id.in_([a.id for a in announcements])
            ).all()
            logger.info(f"⭐ Evaluations: {len(evaluations)} found")
            for evaluation in evaluations:
                rec = evaluation.recommendation or "N/A"
                score = evaluation.overall_score or 0
                logger.info(f"   - Recommendation: {rec}, Overall Score: {score}/5")

            # Check trading decisions (join through announcement to get asx_code)
            trading_decisions = db.query(TradingDecision).join(
                Announcement, TradingDecision.announcement_id == Announcement.id
            ).filter(
                Announcement.asx_code == asx_code
            ).all()
            logger.info(f"💰 Trading Decisions: {len(trading_decisions)} found")
            for decision in trading_decisions:
                status = "EXECUTED" if decision.executed else ("APPROVED" if decision.human_approved else "PENDING")
                logger.info(f"   - Decision: {decision.decision}, Status: {status}")

    logger.info(f"\n{'='*80}")
    logger.info(f"{'✅ DATABASE VERIFICATION PASSED' if success else '❌ DATABASE VERIFICATION FAILED'}")
    logger.info(f"{'='*80}\n")

    return success


def print_summary(result: Dict[str, Any]):
    """Print a summary of the pipeline results."""
    logger.info(f"\n{'='*80}")
    logger.info(f"📊 PIPELINE EXECUTION SUMMARY")
    logger.info(f"{'='*80}\n")

    if "error" in result:
        logger.error(f"❌ Pipeline failed with error: {result['error']}")
        return

    announcements_processed = result.get("announcements_processed", 0)
    logger.info(f"📋 Announcements processed: {announcements_processed}")

    analyses = result.get("analyses", [])
    logger.info(f"🔬 Analyses generated: {len(analyses)}")

    evaluations = result.get("evaluations", [])
    logger.info(f"⭐ Evaluations created: {len(evaluations)}")
    for i, evaluation in enumerate(evaluations, 1):
        rec = evaluation.get("recommendation", "N/A")
        logger.info(f"   {i}. Recommendation: {rec}")

    trading_signals = result.get("trading_signals", [])
    logger.info(f"💰 Trading signals: {len(trading_signals)}")
    for i, signal in enumerate(trading_signals, 1):
        status = signal.get("status", "N/A")
        logger.info(f"   {i}. Status: {status}")
        if status == "PENDING_APPROVAL":
            ticket_id = signal.get("ticket_id", "")
            approval_url = signal.get("approval_url", "http://localhost:8888/approvals")
            logger.warning(f"      ⏸️  Trade pending approval!")
            logger.info(f"      🎫 Ticket: {ticket_id}")
            logger.info(f"      🌐 Approval UI: {approval_url}")

    errors = result.get("errors", [])
    if errors:
        logger.warning(f"⚠️  Errors encountered: {len(errors)}")
        for error in errors:
            logger.warning(f"   - {error}")

    logger.info(f"\n{'='*80}\n")


async def main():
    """Main test execution flow."""
    parser = argparse.ArgumentParser(description="End-to-End Pipeline Test")
    parser.add_argument("--asx-code", default="BHP", help="ASX code to test (default: BHP)")
    parser.add_argument("--limit", type=int, default=5, help="Number of announcements to process (default: 5)")
    parser.add_argument("--no-price-sensitive", action="store_true", help="Include all announcements (not just price-sensitive)")
    parser.add_argument("--skip-agent-start", action="store_true", help="Skip starting agents (assume they're already running)")
    parser.add_argument("--skip-verification", action="store_true", help="Skip database verification")
    args = parser.parse_args()

    # Ensure ASX code is uppercase for consistency
    args.asx_code = args.asx_code.upper()

    price_sensitive = not args.no_price_sensitive

    logger.info(f"\n{'#'*80}")
    logger.info(f"# ASX ADK GEMINI - END-TO-END PIPELINE TEST")
    logger.info(f"# Testing: {args.asx_code}, Limit: {args.limit}, Price Sensitive: {price_sensitive}")
    logger.info(f"{'#'*80}\n")

    agent_manager = AgentManager()

    try:
        # Step 1: Start all agents
        if not args.skip_agent_start:
            logger.info("📦 STEP 1: STARTING AGENTS\n")
            for name, config in AGENTS.items():
                agent_manager.start_agent(name, config)

            # Wait for all agents to be ready
            logger.info("\n⏳ STEP 2: WAITING FOR AGENTS TO BE READY\n")
            all_ready = True
            for name, config in AGENTS.items():
                if not await agent_manager.check_agent_health(name, config["port"]):
                    all_ready = False
                    break

            if not all_ready:
                logger.error("❌ Not all agents started successfully. Aborting test.")
                return 1
        else:
            logger.info("⏭️  Skipping agent startup (--skip-agent-start flag set)\n")

        # Step 2: Trigger pipeline
        logger.info(f"\n{'='*80}")
        logger.info(f"🚀 STEP 3: TRIGGERING PIPELINE")
        logger.info(f"{'='*80}\n")

        result = await trigger_pipeline(args.asx_code, args.limit, price_sensitive)

        # Step 3: Print summary
        print_summary(result)

        # Step 4: Verify database
        if not args.skip_verification:
            verify_database_records(args.asx_code)
        else:
            logger.info("⏭️  Skipping database verification (--skip-verification flag set)\n")

        logger.info("✅ End-to-end test completed!")
        return 0

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Test interrupted by user")
        return 130

    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        return 1

    finally:
        # Cleanup: Stop all agents
        if not args.skip_agent_start:
            logger.info(f"\n{'='*80}")
            logger.info(f"🧹 CLEANUP: STOPPING AGENTS")
            logger.info(f"{'='*80}\n")
            agent_manager.stop_all_agents()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
