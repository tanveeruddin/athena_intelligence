"""
Skills for the Coordinator Agent (Orchestrator).
"""
import asyncio
import httpx
import uuid
from typing import Dict, Any, List, Optional

from models.schemas import RunPipelineInput, RunPipelineOutput, ScraperInput
from models.database import get_db_session
from models.orm_models import Company, Announcement
from utils.config import get_settings
from utils.logging import get_logger
from utils.db_logger import log_to_db
# Trading agent is now a remote A2A service (not imported directly)
# Delegation to trading_agent happens via coordinator's sub_agents

logger = get_logger()
settings = get_settings()

async def run_announcement_pipeline(input_data: RunPipelineInput) -> RunPipelineOutput:
    """
    Executes the complete announcement processing pipeline by orchestrating other agents.
    """
    # Use task_id from input if provided (from chat UI), otherwise generate new one
    task_id = input_data.task_id or str(uuid.uuid4())

    # Debug logging to track task_id flow
    logger.info(f"🔍 Pipeline input task_id: {input_data.task_id}")
    logger.info(f"🔍 Using task_id: {task_id}")

    log_to_db(task_id, "coordinator", f"🚀 Starting full announcement processing pipeline with input: {input_data}")

    # 1. Scrape new announcements for the specified ASX code
    scraper_input = ScraperInput(
        asx_code=input_data.asx_code,
        price_sensitive_only=input_data.price_sensitive_only,
        limit=input_data.limit,
        task_id=task_id  # Pass task_id to scraper for logging
    )
    log_to_db(task_id, "coordinator", f"📞 Calling scraper agent for {input_data.asx_code}")
    scraped_data = await _call_agent_with_retry("scraper", "scrape_asx_announcements", scraper_input.dict())
    
    announcements = scraped_data.get("announcements", [])
    if not announcements:
        log_to_db(task_id, "coordinator", "No new announcements to process.")
        return RunPipelineOutput(announcements_processed=0, analyses=[], stock_data=[], timeline_comparisons=[], evaluations=[], trading_signals=[], errors=[])

    log_to_db(task_id, "coordinator", f"Scraped {len(announcements)} new announcements.")

    # 2. Process each announcement in parallel
    tasks = [_process_single_announcement(ann, input_data.enable_evaluation, input_data.watchlist_codes, input_data.limit, task_id) for ann in announcements]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 3. Aggregate results
    output = RunPipelineOutput(announcements_processed=0, analyses=[], stock_data=[], timeline_comparisons=[], evaluations=[], trading_signals=[], errors=[])
    for res in results:
        if isinstance(res, Exception):
            log_to_db(task_id, "coordinator", f"Error processing an announcement: {res}")
            output.errors.append({"error": str(res)})
        else:
            output.announcements_processed += 1
            output.analyses.append(res.get("analysis", {}))
            output.stock_data.append(res.get("stock", {}))
            output.timeline_comparisons.append(res.get("timeline", {}))
            output.evaluations.append(res.get("evaluation", {}))
            if "trading" in res:
                output.trading_signals.append(res.get("trading", {}))

    log_to_db(task_id, "coordinator", f"✅ Pipeline complete: {output.announcements_processed} processed, {len(output.errors)} errors.")
    return output

async def _process_single_announcement(announcement: Dict[str, Any], enable_evaluation: bool, watchlist: Optional[List[str]], limit: Optional[int] = 5, task_id: str = None) -> Dict[str, Any]:
    """Orchestrates the processing of a single announcement by various agents."""
    from datetime import datetime

    asx_code = announcement["asx_code"]
    log_to_db(task_id, "coordinator", f"📋 Processing announcement for {asx_code}: {announcement.get('title', 'Unknown')[:60]}...")

    # Get announcement_id and company_id from database (scraper already created the records)
    announcement_id = announcement.get("announcement_id")
    if not announcement_id:
        log_to_db(task_id, "coordinator", f"No announcement_id in announcement data: {announcement}")
        raise ValueError("Announcement data missing announcement_id - scraper should have created it")

    with get_db_session() as db:
        # Get company_id from announcement record
        ann_record = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not ann_record:
            log_to_db(task_id, "coordinator", f"Announcement not found in database: {announcement_id}")
            raise ValueError(f"Announcement {announcement_id} not found - scraper should have created it")

        company_id = ann_record.company_id
        log_to_db(task_id, "coordinator", f"Found announcement {announcement_id} for company {company_id}")

    # Analyzer and Stock agents can be called in parallel
    log_to_db(task_id, "coordinator", f"📄 Calling analyzer agent for announcement {announcement_id}...")
    # Scraper already downloaded PDF and created markdown, so analyzer just needs announcement_id
    analyzer_input = {"announcement_id": announcement_id, "task_id": task_id}
    analysis_task = _call_agent_with_retry("analyzer", "process_and_analyze_announcement", analyzer_input)

    log_to_db(task_id, "coordinator", f"📈 Calling stock agent for {asx_code}...")
    stock_input = {"asx_code": asx_code, "task_id": task_id}
    stock_task = _call_agent_with_retry("stock", "get_stock_data", stock_input)

    analysis_result, stock_result = await asyncio.gather(analysis_task, stock_task, return_exceptions=True)

    log_to_db(task_id, "coordinator", f"✅ Analyzer and stock agents completed for {asx_code}")

    results = {}
    if isinstance(analysis_result, Exception):
        raise analysis_result
    results["analysis"] = analysis_result

    if isinstance(stock_result, Exception):
        log_to_db(task_id, "coordinator", f"Stock data fetch failed for {asx_code}: {stock_result}")
        results["stock"] = {"error": str(stock_result)}
    else:
        results["stock"] = stock_result

    # Memory agent - SKIPPED (per requirements)
    # memory_input = {
    #     "company_id": company_id,
    #     "announcement_id": announcement_id,
    #     "analysis_data": analysis_result["analysis"]
    # }
    # timeline_result = await _call_agent_with_retry("memory", "store_episodic_memory", memory_input)
    # results["timeline"] = timeline_result
    results["timeline"] = {}  # Placeholder

    log_to_db(task_id, "coordinator", f"📊 Calling evaluation agent for {asx_code}...")
    # Evaluation - Now generates BUY/HOLD/SELL recommendations (not just quality scores)
    # Get last X analyses for this company from database (user-specified, default 5)
    historical_analyses = _get_historical_analyses(company_id, limit=limit or 5)

    eval_input = {
        "announcement_id": announcement_id,
        "current_analysis": analysis_result["analysis"],
        "historical_analyses": historical_analyses,
        "stock_data": stock_result,
        "asx_code": asx_code,
        "task_id": task_id
    }
    evaluation_result = await _call_agent_with_retry("evaluation", "generate_investment_recommendation", eval_input)
    results["evaluation"] = evaluation_result

    log_to_db(task_id, "coordinator", f"💰 Evaluation complete: {evaluation_result.get('recommendation', 'UNKNOWN')}")

    # Trading - Call trading agent via A2A when BUY signal detected
    recommendation = evaluation_result.get("recommendation", "HOLD")
    if recommendation in ["BUY", "SPECULATIVE BUY"]:
        log_to_db(task_id, "coordinator", f"🚨 {recommendation} signal detected for {asx_code}. Calling trading agent...")

        # Prepare trading agent input
        trading_input = {
            "asx_code": asx_code,
            "company_id": company_id,
            "recommendation": recommendation,
            "price": stock_result.get("price", 0.0),
            "analysis_summary": analysis_result.get("summary", "")[:200],  # Truncate to 200 chars
            "sentiment": analysis_result.get("sentiment", "NEUTRAL"),
            "confidence_score": evaluation_result.get("confidence_score", 0.5),
            "reasoning": evaluation_result.get("recommendation_reasoning", "")[:300],  # Truncate
            "announcement_id": announcement_id,
            "task_id": task_id
        }

        try:
            # Call trading agent's execute_trade function via A2A
            log_to_db(task_id, "coordinator", f"   📞 Calling trading agent execute_trade...")
            trading_response = await _call_agent_with_retry("trading", "execute_trade", trading_input)

            # Trading agent returns {"status": "pending", "ticket_id": "trade-xxx", ...}
            if trading_response.get("status") == "pending":
                ticket_id = trading_response.get("ticket_id")
                log_to_db(task_id, "coordinator", f"   ⏳ Trade pending human approval")
                log_to_db(task_id, "coordinator", f"   🎫 Ticket ID: {ticket_id}")
                log_to_db(task_id, "coordinator", f"   🌐 Approval UI: http://localhost:8888/approvals")

                results["trading"] = {
                    "status": "PENDING_APPROVAL",
                    "ticket_id": ticket_id,
                    "decision_id": trading_response.get("decision_id"),
                    "asx_code": asx_code,
                    "recommendation": recommendation,
                    "price": stock_result.get("price"),
                    "message": f"Trade decision created. Awaiting human approval at http://localhost:8888/approvals",
                    "approval_url": f"http://localhost:8888/approvals?ticket={ticket_id}"
                }
            else:
                # Unexpected response (not pending)
                log_to_db(task_id, "coordinator", f"   ⚠️  Unexpected trading response: {trading_response}")
                results["trading"] = trading_response

        except Exception as e:
            log_to_db(task_id, "coordinator", f"   ❌ Trading agent call failed: {e}")
            results["trading"] = {"status": "ERROR", "error": str(e)}

    else:
        log_to_db(task_id, "coordinator", f"⏸️  No BUY signal for {asx_code}. Recommendation: {recommendation}. Skipping trading.")
        results["trading"] = {"status": "SKIPPED", "reason": f"Recommendation was {recommendation}, not BUY"}

    return results


async def _call_agent(agent_name: str, skill_name: str, skill_input: Dict[str, Any]) -> Dict[str, Any]:
    """Helper function to call another agent's skill via A2A protocol."""
    import uuid
    agent_url = settings.get_agent_url(agent_name)

    async with httpx.AsyncClient(timeout=settings.a2a_timeout_seconds) as client:
        # 1. Send the task using A2A protocol with JSON-RPC wrapper
        message_id = str(uuid.uuid4())

        # Build text prompt for the LLM agent to invoke the skill
        prompt_parts = [f"{k}={v}" for k, v in skill_input.items()]
        prompt = f"Use the {skill_name} tool with parameters: {', '.join(prompt_parts)}"

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

        response = await client.post(agent_url, json=payload)
        response.raise_for_status()
        result = response.json()

        # Extract task_id from A2A response
        task_id = result.get("result", {}).get("id")
        if not task_id:
            raise RuntimeError(f"No task_id received from {agent_name}: {result}")

        # 2. Poll for the result using A2A protocol
        while True:
            await asyncio.sleep(2)

            poll_payload = {
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "params": {"id": task_id},
                "id": str(uuid.uuid4())
            }

            response = await client.post(agent_url, json=poll_payload)
            response.raise_for_status()
            poll_result = response.json()

            task_data = poll_result.get("result", {})
            task_status = task_data.get("status", {})
            state = task_status.get("state", "unknown")

            if state == "completed":
                # Extract output from A2A response - need to get the actual function response, not text
                # Look through task history for the function_response
                history = poll_result.get("result", {}).get("history", [])

                # DEBUG: Log response structure
                logger.info(f"🔍 DEBUG [{agent_name}.{skill_name}]: History items count: {len(history)}")

                for idx, hist_item in enumerate(reversed(history)):  # Check from most recent
                    role = hist_item.get("role", "UNKNOWN")
                    logger.debug(f"🔍 DEBUG: History item {idx}: role={role}")

                    if role == "agent":
                        parts = hist_item.get("parts", [])
                        logger.info(f"🔍 DEBUG [{agent_name}.{skill_name}]: Found agent message with {len(parts)} parts")

                        for part_idx, part in enumerate(parts):
                            part_keys = list(part.keys())
                            logger.debug(f"🔍 DEBUG: Part {part_idx}: keys={part_keys}")

                            # Check if this part contains function response data
                            if "data" in part:
                                data = part["data"]
                                # ADK function responses have metadata with adk_type
                                metadata = part.get("metadata", {})
                                adk_type = metadata.get("adk_type", "NOT_SET")

                                logger.info(f"🔍 DEBUG [{agent_name}.{skill_name}]: Found data part - adk_type={adk_type}")
                                logger.debug(f"🔍 DEBUG: Metadata keys: {list(metadata.keys())}")
                                logger.debug(f"🔍 DEBUG: Data keys: {list(data.keys())}")

                                if adk_type == "function_response":
                                    response_data = data.get("response", {})
                                    logger.info(f"🔍 DEBUG [{agent_name}.{skill_name}]: response_data keys: {list(response_data.keys())}")

                                    # Case 1: Pydantic BaseModel returns (e.g., AnalyzerOutput) - nested under "result"
                                    if "result" in response_data:
                                        logger.info(f"✅ Extracted function response from {agent_name}.{skill_name} (Pydantic BaseModel)")
                                        return response_data["result"]

                                    # Case 2: Plain dict returns (e.g., evaluation) - response_data IS the result
                                    elif response_data:
                                        logger.info(f"✅ Extracted function response from {agent_name}.{skill_name} (plain dict)")
                                        return response_data

                                    # Case 3: Check if result is directly in data (fallback)
                                    elif "result" in data:
                                        logger.info(f"✅ Found result in data (not response). Returning: {data['result']}")
                                        return data["result"]
                                    else:
                                        logger.warning(f"⚠️ function_response found but structure unclear. Response keys: {list(response_data.keys())}")
                                        logger.warning(f"⚠️ Full response_data: {response_data}")

                # Fallback to old behavior if no function response found
                logger.warning(f"⚠️ No function_response found for {agent_name}.{skill_name}, using fallback")

                message = task_status.get("message", {})
                parts = message.get("parts", [])
                logger.info(f"🔍 DEBUG: Fallback - message parts count: {len(parts)}")

                if parts and len(parts) > 0:
                    first_part = parts[0]
                    first_part_keys = list(first_part.keys())
                    logger.debug(f"🔍 DEBUG: Fallback first_part keys: {first_part_keys}")

                    if "text" in first_part:
                        text_preview = first_part['text'][:200]
                        logger.warning(f"⚠️ Returning fallback text (first 200 chars): {text_preview}")
                        return {"result": first_part["text"]}
                    else:
                        logger.warning(f"⚠️ Returning fallback first_part: {first_part}")
                        return first_part

                logger.error(f"❌ No data found in response for {agent_name}.{skill_name}")
                return {}

            if state == "failed":
                error_msg = task_status.get("message", {})
                raise RuntimeError(f"Agent '{agent_name}' skill '{skill_name}' failed: {error_msg}")


async def _call_agent_with_retry(
    agent_name: str,
    skill_name: str,
    skill_input: Dict[str, Any],
    max_retries: int = 3,
    base_delay: float = 12.0
) -> Dict[str, Any]:
    """
    Helper function to call another agent's skill via A2A protocol with retry logic.

    This wraps _call_agent with exponential backoff retry for rate limit errors.

    Args:
        agent_name: Name of the agent to call (e.g., "scraper", "analyzer")
        skill_name: Name of the skill to invoke on the agent
        skill_input: Dictionary of parameters to pass to the skill
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 12.0)

    Returns:
        Dictionary containing the agent's response

    Raises:
        RuntimeError: If max retries exceeded or non-rate-limit error occurs

    Example:
        >>> result = await _call_agent_with_retry(
        ...     "analyzer",
        ...     "process_announcement",
        ...     {"announcement_id": "123"}
        ... )
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            # Call the original agent function
            result = await _call_agent(agent_name, skill_name, skill_input)

            # Success! Return immediately
            if attempt > 0:
                logger.info(f"✅ Agent call succeeded on attempt {attempt + 1}/{max_retries}")
            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # Check if this is a rate limit error
            is_rate_limit = any([
                "429" in str(e),
                "resource_exhausted" in error_str,
                "quota" in error_str,
                "rate limit" in error_str
            ])

            if not is_rate_limit:
                # Not a rate limit error - raise immediately (don't retry)
                logger.error(f"❌ Non-rate-limit error calling {agent_name}.{skill_name}: {e}")
                raise

            # Rate limit error - check if we should retry
            if attempt < max_retries - 1:
                # Calculate exponential backoff delay
                delay = base_delay * (2 ** attempt)

                logger.warning(
                    f"⏱️  Rate limit hit calling {agent_name}.{skill_name}. "
                    f"Retrying in {delay:.0f}s... (attempt {attempt + 1}/{max_retries})"
                )

                # Wait before retrying
                await asyncio.sleep(delay)
            else:
                # Max retries exceeded
                logger.error(
                    f"❌ Max retries ({max_retries}) exceeded for {agent_name}.{skill_name}. "
                    f"Rate limit errors persist."
                )
                raise RuntimeError(
                    f"Max retries ({max_retries}) exceeded calling {agent_name}.{skill_name}. "
                    f"Last error: {last_error}"
                ) from last_error

    # Should never reach here, but just in case
    raise RuntimeError(f"Unexpected state in retry loop for {agent_name}.{skill_name}") from last_error


def _get_historical_analyses(company_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieves the last X analysis records for a company from the database.

    Args:
        company_id: The company ID to query
        limit: Maximum number of historical analyses to retrieve (default: 5)

    Returns:
        List of analysis dictionaries with summary, sentiment, key_insights, etc.
    """
    from models.orm_models import Analysis, Announcement

    with get_db_session() as db:
        # Get announcements for this company, ordered by date (most recent first)
        announcements = db.query(Announcement).filter(
            Announcement.company_id == company_id
        ).order_by(Announcement.announcement_date.desc()).limit(limit).all()

        analyses = []
        for ann in announcements:
            # Get analysis for this announcement
            analysis = db.query(Analysis).filter(
                Analysis.announcement_id == ann.id
            ).first()

            if analysis:
                analyses.append({
                    "announcement_id": str(analysis.announcement_id),
                    "announcement_date": ann.announcement_date.isoformat() if ann.announcement_date else None,
                    "announcement_title": ann.title,
                    "summary": analysis.summary,
                    "sentiment": analysis.sentiment,
                    "key_insights": analysis.key_insights,
                    "management_promises": analysis.management_promises,
                    "financial_impact": analysis.financial_impact
                })

        logger.info(f"Retrieved {len(analyses)} historical analyses for company {company_id}")
        return analyses

