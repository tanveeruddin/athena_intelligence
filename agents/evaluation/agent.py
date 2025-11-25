"""
Evaluation Agent - ADK-based agent for quality assessment using LLM-as-a-Judge.
"""
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from models.schemas import (
    EvaluateAnalysisInput, GetAggregateScoresInput, AnalysisResponse
)
from .skills import evaluate_analysis, get_aggregate_scores, generate_investment_recommendation
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Ensure GEMINI_API_KEY is set from settings if available
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# Define functions that will be wrapped by ADK's FunctionTool.
async def evaluate_analysis_skill(original_content: str, analysis_data: Dict[str, Any], announcement_id: str):
    """Use LLM-as-a-Judge to evaluate analysis quality."""
    input_data = EvaluateAnalysisInput(
        original_content=original_content,
        analysis_data=AnalysisResponse(**analysis_data),
        announcement_id=announcement_id
    )
    return (await evaluate_analysis(input_data)).dict()

async def get_aggregate_scores_skill(min_date: Optional[str] = None):
    """Retrieve aggregate quality statistics across all evaluations."""
    min_date_obj = datetime.fromisoformat(min_date) if min_date else None
    input_data = GetAggregateScoresInput(min_date=min_date_obj)
    return (await get_aggregate_scores(input_data)).dict()

async def generate_investment_recommendation_skill(
    announcement_id: str,
    current_analysis: Dict[str, Any],
    historical_analyses: Optional[List[Dict[str, Any]]] = None,
    stock_data: Optional[Dict[str, Any]] = None,
    asx_code: Optional[str] = None,
    task_id: Optional[str] = None
):
    """
    Generate investment recommendations (BUY/HOLD/SELL/SPECULATIVE BUY/AVOID).

    Combines quality scoring with investment analysis based on:
    - Current announcement analysis
    - Historical analysis trends (last X announcements)
    - Stock price and performance metrics

    This is the PRIMARY tool for the coordinator agent to request recommendations.

    Args:
        task_id: The ID for the current request, used for logging (REQUIRED - must be passed from coordinator)
    """
    input_data = {
        "announcement_id": announcement_id,
        "current_analysis": current_analysis,
        "historical_analyses": historical_analyses or [],
        "stock_data": stock_data or {},
        "asx_code": asx_code or "UNKNOWN",
        "task_id": task_id
    }
    return await generate_investment_recommendation(input_data)

# Create LlmAgent with the skill-based tools
evaluation_agent = LlmAgent(
    model=settings.gemini_model,
    name="asx_evaluation_agent",
    description="Evaluates analysis quality and generates investment recommendations.",
    instruction="""You are an expert evaluation and investment analysis agent.

Your capabilities:
1. **Quality Scoring** (evaluate_analysis_skill): Score analysis quality on 1-5 scale
2. **Investment Recommendations** (generate_investment_recommendation_skill): Generate BUY/HOLD/SELL recommendations
3. **Aggregate Stats** (get_aggregate_scores_skill): Calculate aggregate performance metrics

**Primary Function**: generate_investment_recommendation_skill
This is your main tool - it combines quality scoring WITH investment analysis.
Use this when asked to evaluate announcements or provide investment advice.

**IMPORTANT: task_id handling**
- When you receive a request, it will include a task_id parameter for logging purposes
- You MUST extract the task_id and pass it to the generate_investment_recommendation_skill function
- The task_id is critical for tracking logs across the system

**When called**:
- Expect: announcement_id, current_analysis, historical_analyses, stock_data, asx_code, task_id
- Return: Quality scores + recommendation (BUY/HOLD/SELL/SPECULATIVE BUY/AVOID) + reasoning + confidence
- Always pass task_id parameter to the function

Always provide objective, data-driven recommendations.""".strip(),
    tools=[
        FunctionTool(evaluate_analysis_skill),
        FunctionTool(get_aggregate_scores_skill),
        FunctionTool(generate_investment_recommendation_skill),  # NEW: Primary tool
    ],
)

# Convert the Agent to an A2A-compliant FastAPI application
app = to_a2a(
    evaluation_agent,
    host="localhost",
    port=settings.evaluation_agent_port,
    protocol="http"
)

