"""
Memory Agent - ADK-based agent for memory management and timeline analysis (KEY INNOVATION).
"""
import os
from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from models.schemas import (
    StoreEpisodicMemoryInput, RetrieveEpisodicMemoryInput,
    UpdateSemanticMemoryInput, CompareTimelineInput,
    AnalysisResponse, PerformanceTrend, PromiseTracking
)
from .skills import (
    store_episodic_memory,
    retrieve_episodic_memory,
    update_semantic_memory,
    compare_timeline
)
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Ensure GEMINI_API_KEY is set from settings if available
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# Define functions that will be wrapped by ADK's FunctionTool.
async def store_episodic_memory_skill(company_id: str, announcement_id: str, analysis_data: dict):
    """Stores an announcement in the company's timeline (episodic memory)."""
    input_data = StoreEpisodicMemoryInput(
        company_id=company_id,
        announcement_id=announcement_id,
        analysis_data=AnalysisResponse(**analysis_data)
    )
    return (await store_episodic_memory(input_data)).dict()

async def retrieve_timeline_skill(company_id: str, limit: int = 10):
    """Gets historical announcements for a company."""
    input_data = RetrieveEpisodicMemoryInput(company_id=company_id, limit=limit)
    return (await retrieve_episodic_memory(input_data)).dict()

async def update_semantic_memory_skill(
    company_id: str,
    performance_trend: str,
    recent_themes: list,
    promise_tracking: dict
):
    """Updates aggregated company knowledge (semantic memory)."""
    input_data = UpdateSemanticMemoryInput(
        company_id=company_id,
        performance_trend=PerformanceTrend(performance_trend),
        recent_themes=recent_themes,
        promise_tracking={k: PromiseTracking(**v) for k, v in promise_tracking.items()}
    )
    return (await update_semantic_memory(input_data)).dict()

async def compare_timeline_skill(company_id: str, new_announcement_data: dict):
    """Analyzes company performance trends over time by comparing the new announcement to historical ones."""
    input_data = CompareTimelineInput(
        company_id=company_id,
        new_announcement_data=AnalysisResponse(**new_announcement_data)
    )
    return (await compare_timeline(input_data)).dict()

# Create LlmAgent with the skill-based tools
memory_agent = LlmAgent(
    model=settings.gemini_model,
    name="asx_memory_agent",
    description="Manages episodic and semantic memory with timeline comparison analysis.",
    instruction="You are an advanced memory agent. Use your tools to store, retrieve, and analyze company announcement timelines.",
    tools=[
        FunctionTool(store_episodic_memory_skill),
        FunctionTool(retrieve_timeline_skill),
        FunctionTool(update_semantic_memory_skill),
        FunctionTool(compare_timeline_skill),
    ],
)

# Convert the Agent to an A2A-compliant FastAPI application
app = to_a2a(
    memory_agent,
    host="localhost",
    port=settings.memory_agent_port,
    protocol="http"
)

