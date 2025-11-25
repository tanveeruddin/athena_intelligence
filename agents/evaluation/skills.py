"""
Skills for the Evaluation Agent (LLM-as-a-Judge).
"""
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime

import google.generativeai as genai
from sqlalchemy import func

from models.database import get_db_session
from models.orm_models import Evaluation
from models.schemas import (
    EvaluateAnalysisInput, EvaluateAnalysisOutput,
    GetAggregateScoresInput, GetAggregateScoresOutput,
)
from utils.config import get_settings
from utils.logging import get_logger
from utils.prompts import get_evaluation_prompt, EVALUATION_SYSTEM_PROMPT, format_json_response
from utils.db_logger import log_to_db

logger = get_logger()
settings = get_settings()

# Gemini Model for evaluation
try:
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        gemini_model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            generation_config={"temperature": 0.1}
        )
    else:
        gemini_model = None
        logger.warning("GEMINI_API_KEY not set, evaluation skills will not function.")
except Exception as e:
    gemini_model = None
    logger.error(f"Failed to initialize Gemini model for evaluation skills: {e}")

async def evaluate_analysis(input_data: EvaluateAnalysisInput) -> EvaluateAnalysisOutput:
    """Evaluates the quality of an announcement analysis using an LLM."""
    task_id = input_data.task_id
    if not gemini_model:
        raise RuntimeError("Gemini model not initialized.")
    if not settings.enable_evaluation:
        log_to_db(task_id, "evaluation", "Evaluation is disabled in settings.")
        logger.warning("Evaluation is disabled in settings.")
        raise RuntimeError("Evaluation is disabled.")

    log_to_db(task_id, "evaluation", f"Evaluating analysis for announcement {input_data.announcement_id}")
    logger.info(f"Evaluating analysis for announcement {input_data.announcement_id}")

    prompt = get_evaluation_prompt(
        original_content=input_data.original_content,
        generated_summary=input_data.analysis_data.summary,
        generated_sentiment=input_data.analysis_data.sentiment,
        generated_insights=input_data.analysis_data.key_insights
    )

    start_time = time.time()
    full_prompt = f"{EVALUATION_SYSTEM_PROMPT}\n\n{prompt}"
    response = await gemini_model.generate_content_async(full_prompt)
    processing_time_ms = int((time.time() - start_time) * 1000)

    parsed_response = _parse_evaluation_response(response.text, task_id)
    tokens_used = (len(full_prompt) + len(response.text)) // 4

    await _create_evaluation_record(input_data.announcement_id, parsed_response, processing_time_ms, tokens_used, task_id)

    return EvaluateAnalysisOutput(
        **parsed_response,
        processing_time_ms=processing_time_ms,
        tokens_used=tokens_used
    )

async def get_aggregate_scores(input_data: GetAggregateScoresInput) -> GetAggregateScoresOutput:
    """Calculates and returns aggregate quality scores from all evaluations."""
    logger.info("Calculating aggregate evaluation scores.")
    with get_db_session() as db:
        query = db.query(
            func.count(Evaluation.id),
            func.avg(Evaluation.summary_score),
            func.avg(Evaluation.sentiment_score),
            func.avg(Evaluation.insights_score),
            func.avg(Evaluation.overall_score),
            func.min(Evaluation.overall_score),
            func.max(Evaluation.overall_score)
        )
        if input_data.min_date:
            query = query.filter(Evaluation.evaluated_at >= input_data.min_date)
        
        results = query.one()

    count, avg_summary, avg_sentiment, avg_insights, avg_overall, min_overall, max_overall = results
    
    return GetAggregateScoresOutput(
        count=count or 0,
        avg_summary_score=round(avg_summary, 2) if avg_summary else None,
        avg_sentiment_score=round(avg_sentiment, 2) if avg_sentiment else None,
        avg_insights_score=round(avg_insights, 2) if avg_insights else None,
        avg_overall_score=round(avg_overall, 2) if avg_overall else None,
        min_overall_score=min_overall,
        max_overall_score=max_overall
    )

def _parse_evaluation_response(response_text: str, task_id: str) -> Dict[str, Any]:
    """Parses and validates the evaluation response from the LLM."""
    try:
        data = json.loads(format_json_response(response_text))
        for field in ["summary_score", "sentiment_score", "insights_score", "overall_score"]:
            if field in data and isinstance(data[field], (int, float)):
                data[field] = max(1.0, min(5.0, float(data[field])))
            else:
                 data[field] = 3.0 # Default score
        
        if "overall_score" not in data:
             scores = [data[f] for f in ["summary_score", "sentiment_score", "insights_score"]]
             data["overall_score"] = round(sum(scores) / len(scores), 2) if scores else 3.0

        for fb_field in ["summary_feedback", "sentiment_feedback", "insights_feedback", "overall_feedback"]:
            if fb_field not in data:
                data[fb_field] = "No feedback provided."

        return data
    except (json.JSONDecodeError, ValueError) as e:
        log_to_db(task_id, "evaluation", f"Failed to parse evaluation response: {e}")
        logger.error(f"Failed to parse evaluation response: {e}")
        return {
            "summary_score": 1.0, "summary_feedback": "Error parsing response.",
            "sentiment_score": 1.0, "sentiment_feedback": "Error parsing response.",
            "insights_score": 1.0, "insights_feedback": "Error parsing response.",
            "overall_score": 1.0, "overall_feedback": "Failed to parse evaluation from LLM."
        }

async def _create_evaluation_record(announcement_id: str, eval_data: Dict, time_ms: int, tokens: int, task_id: str):
    """Saves an evaluation record to the database."""
    with get_db_session() as db:
        evaluation = Evaluation(
            announcement_id=announcement_id,
            processing_time_ms=time_ms,
            tokens_used=tokens,
            **eval_data
        )
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)
        log_to_db(task_id, "evaluation", f"Created evaluation record {evaluation.id} for announcement {announcement_id}")
        logger.info(f"Created evaluation record {evaluation.id} for announcement {announcement_id}")


async def generate_investment_recommendation(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates investment recommendations (BUY/HOLD/SELL/SPECULATIVE BUY/AVOID) based on:
    - Current announcement analysis
    - Historical analyses (last X announcements)
    - Stock price and performance data

    This combines LLM-as-a-Judge quality scoring with investment analysis.

    Args:
        input_data: Dictionary containing:
            - announcement_id: Current announcement ID
            - current_analysis: Current analysis data (summary, sentiment, insights)
            - historical_analyses: List of past analyses (default last 5)
            - stock_data: Current stock price, market cap, performance metrics
            - asx_code: Company ASX code
            - task_id: The ID for the current request, used for logging.

    Returns:
        Dictionary with quality scores + recommendation + reasoning + confidence
    """
    import uuid
    # Get task_id with fallback to prevent None (defensive programming)
    task_id = input_data.get("task_id") or str(uuid.uuid4())
    if not gemini_model:
        raise RuntimeError("Gemini model not initialized.")

    announcement_id = input_data["announcement_id"]
    current_analysis = input_data["current_analysis"]
    historical_analyses = input_data.get("historical_analyses", [])
    stock_data = input_data.get("stock_data", {})
    asx_code = input_data.get("asx_code", "UNKNOWN")

    log_to_db(task_id, "evaluation", f"Generating investment recommendation for {asx_code} (announcement {announcement_id})")
    logger.info(f"Generating investment recommendation for {asx_code} (announcement {announcement_id})")
    log_to_db(task_id, "evaluation", f"  - Historical context: {len(historical_analyses)} past analyses")
    logger.info(f"  - Historical context: {len(historical_analyses)} past analyses")
    log_to_db(task_id, "evaluation", f"  - Stock price: ${stock_data.get('price', 'N/A')}")
    logger.info(f"  - Stock price: ${stock_data.get('price', 'N/A')}")

    # Build comprehensive prompt
    prompt = _build_investment_recommendation_prompt(
        asx_code=asx_code,
        current_analysis=current_analysis,
        historical_analyses=historical_analyses,
        stock_data=stock_data
    )

    # Call Gemini
    start_time = time.time()
    response = await gemini_model.generate_content_async(prompt)
    processing_time_ms = int((time.time() - start_time) * 1000)

    # Parse response (with optional forced recommendation for testing)
    parsed_response = _parse_investment_recommendation_response(
        response.text,
        force_recommendation=settings.force_recommendation_for_testing,
        task_id=task_id
    )
    tokens_used = (len(prompt) + len(response.text)) // 4

    log_to_db(task_id, "evaluation", f"  - Recommendation: {parsed_response.get('recommendation', 'UNKNOWN')}")
    logger.info(f"  - Recommendation: {parsed_response.get('recommendation', 'UNKNOWN')}")
    log_to_db(task_id, "evaluation", f"  - Confidence: {parsed_response.get('confidence_score', 0):.2f}")
    logger.info(f"  - Confidence: {parsed_response.get('confidence_score', 0):.2f}")

    # Save to database
    await _create_evaluation_record(
        announcement_id=announcement_id,
        eval_data=parsed_response,
        time_ms=processing_time_ms,
        tokens=tokens_used,
        task_id=task_id
    )

    return {
        **parsed_response,
        "processing_time_ms": processing_time_ms,
        "tokens_used": tokens_used
    }


def _build_investment_recommendation_prompt(
    asx_code: str,
    current_analysis: Dict[str, Any],
    historical_analyses: list,
    stock_data: Dict[str, Any]
) -> str:
    """Builds the LLM prompt for investment recommendation."""

    # Format historical context
    historical_context = ""
    if historical_analyses:
        historical_context = "\n### Historical Context (Past Announcements):\n"
        for i, hist in enumerate(historical_analyses[:5], 1):  # Limit to 5
            hist_date = hist.get("announcement_date", "Unknown")
            hist_title = hist.get("announcement_title", "Unknown")
            hist_summary = hist.get("summary", "N/A")
            hist_sentiment = hist.get("sentiment", "NEUTRAL")
            historical_context += f"\n**{i}. {hist_date}** - {hist_title[:80]}\n"
            historical_context += f"   Sentiment: {hist_sentiment}\n"
            historical_context += f"   Summary: {hist_summary[:200]}...\n"
    else:
        historical_context = "\n### Historical Context:\nNo previous announcements available.\n"

    # Format stock data
    market_cap = stock_data.get('market_cap')
    market_cap_str = f"${market_cap:,.0f}" if market_cap else "N/A"

    stock_info = f"""
### Stock Performance ({asx_code}):
- Current Price: ${stock_data.get('price', 'N/A')}
- Market Cap: {market_cap_str}
- 1-Month Performance: {stock_data.get('performance_1m_pct', 'N/A')}%
- 3-Month Performance: {stock_data.get('performance_3m_pct', 'N/A')}%
- 6-Month Performance: {stock_data.get('performance_6m_pct', 'N/A')}%
"""

    # Format current analysis
    current_info = f"""
### Current Announcement Analysis:
- Summary: {current_analysis.get('summary', 'N/A')}
- Sentiment: {current_analysis.get('sentiment', 'NEUTRAL')}
- Key Insights: {', '.join(current_analysis.get('key_insights', []))}
- Management Promises: {', '.join(current_analysis.get('management_promises', []))}
- Financial Impact: {current_analysis.get('financial_impact', 'Unknown')}
"""

    prompt = f"""You are an expert investment analyst evaluating ASX company announcements.

{current_info}
{historical_context}
{stock_info}

## Your Task:

**1. Quality Scoring (1-5 scale):**
Rate the CURRENT announcement analysis on:
- summary_score: How well does the summary capture key points?
- sentiment_score: Is the sentiment assessment accurate?
- insights_score: Are the insights valuable and well-reasoned?
- overall_score: Overall quality of the analysis

**2. Investment Recommendation:**
Based on ALL information above, provide one of these recommendations:
- **BUY**: Strong positive indicators, good value, clear growth trajectory
- **SPECULATIVE BUY**: Positive but with risks, suitable for risk-tolerant investors
- **HOLD**: Neutral/mixed signals, maintain current position
- **SELL**: Declining fundamentals or better opportunities elsewhere
- **AVOID**: Significant red flags or concerns

**3. Analysis Questions:**
Consider these in your reasoning:
- Is financial performance improving vs. historical trends?
- Are management promises being kept (based on historical context)?
- What strategic shifts are evident from recent announcements?
- How is the market reacting (stock performance)?
- What are the key risks and opportunities?

## Output Format (JSON):
{{
  "summary_score": <1-5>,
  "summary_feedback": "<brief feedback>",
  "sentiment_score": <1-5>,
  "sentiment_feedback": "<brief feedback>",
  "insights_score": <1-5>,
  "insights_feedback": "<brief feedback>",
  "overall_score": <1-5>,
  "overall_feedback": "<brief feedback>",
  "recommendation": "<BUY|SPECULATIVE BUY|HOLD|SELL|AVOID>",
  "recommendation_reasoning": "<2-3 sentences explaining the recommendation, referencing trends, promises, performance>",
  "confidence_score": <0.0-1.0>
}}

**Important:**
- Be objective and data-driven
- Reference specific trends from historical context
- Consider both fundamentals and technical indicators
- Confidence score should reflect certainty (0.0=low, 1.0=high)

Provide your evaluation as valid JSON:"""

    return prompt


def _parse_investment_recommendation_response(response_text: str, force_recommendation: Optional[str] = None, task_id: str = None) -> Dict[str, Any]:
    """
    Parses the investment recommendation response from Gemini.

    Args:
        response_text: Raw JSON response from Gemini LLM
        force_recommendation: Optional forced recommendation for testing (BUY/SELL/HOLD/etc)
        task_id: The ID for the current request, used for logging.

    Returns:
        Parsed evaluation data with recommendation
    """
    try:
        data = json.loads(format_json_response(response_text))

        # Validate quality scores (1-5)
        for field in ["summary_score", "sentiment_score", "insights_score", "overall_score"]:
            if field in data and isinstance(data[field], (int, float)):
                data[field] = max(1.0, min(5.0, float(data[field])))
            else:
                data[field] = 3.0  # Default

        # Calculate overall_score if missing
        if "overall_score" not in data:
            scores = [data[f] for f in ["summary_score", "sentiment_score", "insights_score"]]
            data["overall_score"] = round(sum(scores) / len(scores), 2) if scores else 3.0

        # Default feedback
        for fb_field in ["summary_feedback", "sentiment_feedback", "insights_feedback", "overall_feedback"]:
            if fb_field not in data:
                data[fb_field] = "No feedback provided."

        # Validate recommendation
        valid_recommendations = ["BUY", "SPECULATIVE BUY", "HOLD", "SELL", "AVOID"]
        if "recommendation" not in data or data["recommendation"] not in valid_recommendations:
            log_to_db(task_id, "evaluation", f"Invalid recommendation: {data.get('recommendation')}. Defaulting to HOLD.")
            logger.warning(f"Invalid recommendation: {data.get('recommendation')}. Defaulting to HOLD.")
            data["recommendation"] = "HOLD"

        # Validate confidence score (0-1)
        if "confidence_score" in data:
            data["confidence_score"] = max(0.0, min(1.0, float(data["confidence_score"])))
        else:
            data["confidence_score"] = 0.5  # Default medium confidence

        # Ensure reasoning exists
        if "recommendation_reasoning" not in data or not data["recommendation_reasoning"]:
            data["recommendation_reasoning"] = "No reasoning provided."

        # TESTING MODE: Force recommendation if configured
        if force_recommendation and force_recommendation.upper() in valid_recommendations:
            forced_rec = force_recommendation.upper()
            log_to_db(task_id, "evaluation", f"🧪 TESTING MODE: Forcing recommendation from {data['recommendation']} to {forced_rec}")
            logger.warning(f"🧪 TESTING MODE: Forcing recommendation from {data['recommendation']} to {forced_rec}")
            data["recommendation"] = forced_rec
            data["confidence_score"] = 0.99
            data["recommendation_reasoning"] = f"[TEST MODE] Forced to {forced_rec}. Original: {data.get('recommendation', 'N/A')}"

        return data

    except (json.JSONDecodeError, ValueError) as e:
        log_to_db(task_id, "evaluation", f"Failed to parse investment recommendation response: {e}")
        logger.error(f"Failed to parse investment recommendation response: {e}")
        # Return safe defaults
        return {
            "summary_score": 3.0,
            "summary_feedback": "Error parsing response.",
            "sentiment_score": 3.0,
            "sentiment_feedback": "Error parsing response.",
            "insights_score": 3.0,
            "insights_feedback": "Error parsing response.",
            "overall_score": 3.0,
            "overall_feedback": "Failed to parse evaluation from LLM.",
            "recommendation": "HOLD",
            "recommendation_reasoning": "Unable to generate recommendation due to parsing error.",
            "confidence_score": 0.1
        }

