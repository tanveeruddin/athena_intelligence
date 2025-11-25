"""
Skills for the Memory Agent (KEY INNOVATION).
"""
import json
from typing import Dict, Any, List, Optional
import google.generativeai as genai

from models.database import get_db_session
from models.orm_models import EpisodicMemory, SemanticMemory, TimelineComparison, Company, Announcement
from models.schemas import (
    StoreEpisodicMemoryInput, StoreEpisodicMemoryOutput,
    RetrieveEpisodicMemoryInput, RetrieveEpisodicMemoryOutput,
    UpdateSemanticMemoryInput, UpdateSemanticMemoryOutput,
    CompareTimelineInput, CompareTimelineOutput,
    EpisodicMemoryResponse, AnalysisResponse, PromiseTracking, PerformanceTrend
)
from utils.config import get_settings
from utils.logging import get_logger
from utils.prompts import get_timeline_comparison_prompt, TIMELINE_ANALYSIS_SYSTEM_PROMPT, format_json_response

logger = get_logger()
settings = get_settings()

# Gemini Model for timeline analysis
try:
    if settings.gemini_api_key:
        genai.configure(api_key=settings.gemini_api_key)
        gemini_model = genai.GenerativeModel(settings.gemini_model)
    else:
        gemini_model = None
        logger.warning("GEMINI_API_KEY not set, timeline analysis will not function.")
except Exception as e:
    gemini_model = None
    logger.error(f"Failed to initialize Gemini model for memory skills: {e}")

async def store_episodic_memory(input_data: StoreEpisodicMemoryInput) -> StoreEpisodicMemoryOutput:
    """Stores an episodic memory in the database."""
    logger.info(f"Storing episodic memory for announcement {input_data.announcement_id}")
    with get_db_session() as db:
        ann = db.query(Announcement).filter(Announcement.id == input_data.announcement_id).first()
        if not ann:
            raise ValueError(f"Announcement not found: {input_data.announcement_id}")

        memory = EpisodicMemory(
            company_id=input_data.company_id,
            announcement_id=input_data.announcement_id,
            event_date=ann.announcement_date,
            summary=input_data.analysis_data.summary,
            sentiment=input_data.analysis_data.sentiment,
            key_insights=input_data.analysis_data.key_insights,
            management_promises=input_data.analysis_data.management_promises,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        logger.info(f"Stored episodic memory {memory.id}")
        return StoreEpisodicMemoryOutput(memory_id=memory.id)

async def retrieve_episodic_memory(input_data: RetrieveEpisodicMemoryInput) -> RetrieveEpisodicMemoryOutput:
    """Retrieves a timeline of episodic memories for a company."""
    logger.info(f"Retrieving timeline for company {input_data.company_id}")
    with get_db_session() as db:
        memories = db.query(EpisodicMemory).filter(EpisodicMemory.company_id == input_data.company_id).order_by(EpisodicMemory.event_date.desc()).limit(input_data.limit).all()
        response_memories = [EpisodicMemoryResponse.from_orm(m) for m in memories]
        logger.info(f"Retrieved {len(response_memories)} memories.")
        return RetrieveEpisodicMemoryOutput(memories=response_memories, count=len(response_memories))

async def update_semantic_memory(input_data: UpdateSemanticMemoryInput) -> UpdateSemanticMemoryOutput:
    """Updates the semantic memory for a company."""
    logger.info(f"Updating semantic memory for company {input_data.company_id}")
    with get_db_session() as db:
        semantic = db.query(SemanticMemory).filter(SemanticMemory.company_id == input_data.company_id).first()
        if not semantic:
            semantic = SemanticMemory(company_id=input_data.company_id)
            db.add(semantic)

        semantic.performance_trend = input_data.performance_trend
        semantic.recent_themes = input_data.recent_themes
        semantic.promise_tracking = {k: v.dict() for k, v in input_data.promise_tracking.items()}
        db.commit()
        db.refresh(semantic)
        logger.info(f"Updated semantic memory for company {input_data.company_id}")
        return UpdateSemanticMemoryOutput(semantic_memory_id=semantic.id)

async def compare_timeline(input_data: CompareTimelineInput) -> CompareTimelineOutput:
    """Performs timeline comparison and trend analysis using an LLM."""
    if not gemini_model:
        raise RuntimeError("Gemini model not initialized.")

    logger.info(f"⭐ Performing timeline comparison for company {input_data.company_id}")
    
    historical_data = await retrieve_episodic_memory(RetrieveEpisodicMemoryInput(company_id=input_data.company_id))
    if not historical_data.memories:
        raise ValueError("No historical memories found to perform comparison.")

    with get_db_session() as db:
        company = db.query(Company).filter(Company.id == input_data.company_id).first()
        if not company:
            raise ValueError(f"Company not found: {input_data.company_id}")

    prompt = get_timeline_comparison_prompt(
        company_name=company.company_name,
        asx_code=company.asx_code,
        historical_announcements=[m.dict() for m in historical_data.memories],
        new_announcement=input_data.new_announcement_data.dict()
    )
    
    full_prompt = f"{TIMELINE_ANALYSIS_SYSTEM_PROMPT}\n\n{prompt}"
    response = await gemini_model.generate_content_async(full_prompt)
    
    parsed_response = _parse_timeline_response(response.text)

    # Store the comparison result
    with get_db_session() as db:
        ann = db.query(Announcement).filter(Announcement.id == input_data.new_announcement_data.announcement_id).first()
        comparison = TimelineComparison(
            company_id=input_data.company_id,
            latest_announcement_id=input_data.new_announcement_data.announcement_id,
            comparison_date=ann.announcement_date,
            **parsed_response
        )
        db.add(comparison)
        db.commit()
        db.refresh(comparison)
        logger.info(f"Stored timeline comparison {comparison.id}")
        
        # Update semantic memory based on the new analysis
        # This logic could be expanded
        await update_semantic_memory(UpdateSemanticMemoryInput(
            company_id=input_data.company_id,
            performance_trend=parsed_response.get("performance_trend", "STABLE"),
            recent_themes=list(set(m.summary for m in historical_data.memories[:3])) , # simplified
            promise_tracking= {f"p{i}": PromiseTracking(**p) for i, p in enumerate(parsed_response.get("promise_tracking",[]))}
        ))

        return CompareTimelineOutput(comparison_id=comparison.id, **parsed_response)

def _parse_timeline_response(response_text: str) -> Dict[str, Any]:
    """Parses and validates the timeline analysis response from the LLM."""
    try:
        data = json.loads(format_json_response(response_text))
        # Basic validation
        if 'performance_trend' not in data or 'analysis_summary' not in data:
            raise ValueError("Timeline response missing required fields.")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse timeline response: {e}")
        # Return a default/error structure
        return {
            "performance_trend": "STABLE",
            "improvement_score": 0.0,
            "consistency_score": 0.0,
            "promise_fulfillment_score": 0.0,
            "analysis_summary": "Error parsing analysis from LLM.",
            "promise_tracking": [],
            "strategic_shifts": "Unknown",
        }
