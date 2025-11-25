"""
Pydantic schemas for data validation and serialization.
Provides type-safe data structures for API inputs/outputs.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Enums
class SentimentType(str, Enum):
    """Sentiment classification types."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class PerformanceTrend(str, Enum):
    """Performance trend types."""
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"


class TaskStatus(str, Enum):
    """Agent task status types."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PromiseStatus(str, Enum):
    """Management promise tracking status."""
    ON_TRACK = "ON_TRACK"
    FULFILLED = "FULFILLED"
    BROKEN = "BROKEN"
    UNKNOWN = "UNKNOWN"


# Base schemas
class CompanyBase(BaseModel):
    """Base schema for Company."""
    asx_code: str = Field(..., description="ASX ticker code", min_length=1, max_length=10)
    company_name: str = Field(..., description="Full company name")
    industry: Optional[str] = Field(None, description="Industry sector")


class CompanyCreate(CompanyBase):
    """Schema for creating a new company."""
    pass


class CompanyResponse(CompanyBase):
    """Schema for company response."""
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


# Announcement schemas
class AnnouncementBase(BaseModel):
    """Base schema for Announcement."""
    asx_code: str = Field(..., description="ASX ticker code")
    title: str = Field(..., description="Announcement title")
    announcement_date: datetime = Field(..., description="Date of announcement")
    pdf_url: str = Field(..., description="URL to PDF document")
    is_price_sensitive: bool = Field(default=False, description="Price sensitive flag")


class AnnouncementCreate(AnnouncementBase):
    """Schema for creating a new announcement."""
    company_id: str


class AnnouncementResponse(AnnouncementBase):
    """Schema for announcement response."""
    id: str
    company_id: str
    pdf_local_path: Optional[str] = None
    markdown_path: Optional[str] = None
    num_pages: Optional[int] = None
    file_size_kb: Optional[int] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Analysis schemas
class AnalysisBase(BaseModel):
    """Base schema for Analysis."""
    summary: Optional[str] = Field(None, description="2-3 sentence summary")
    sentiment: Optional[SentimentType] = Field(None, description="Sentiment classification")
    key_insights: Optional[List[str]] = Field(None, description="3-5 key insights")
    management_promises: Optional[List[str]] = Field(None, description="Management commitments")
    financial_impact: Optional[str] = Field(None, description="Financial impact assessment")


class AnalysisCreate(AnalysisBase):
    """Schema for creating analysis."""
    announcement_id: str
    llm_model: str = "gemini-2.0-flash-exp"
    processing_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None


class AnalysisResponse(AnalysisBase):
    """Schema for analysis response."""
    id: str
    announcement_id: str
    llm_model: str
    processing_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    created_at: datetime

    @field_validator('key_insights', 'management_promises', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Parse JSON strings to lists if needed (for database reads)."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return []
        return v if v is not None else []

    class Config:
        from_attributes = True


# Stock data schemas
class StockDataBase(BaseModel):
    """Base schema for Stock Data."""
    price_at_announcement: Optional[float] = Field(None, description="Stock price at announcement")
    market_cap: Optional[float] = Field(None, description="Market capitalization")
    performance_1m_pct: Optional[float] = Field(None, description="1-month performance %")
    performance_3m_pct: Optional[float] = Field(None, description="3-month performance %")
    performance_6m_pct: Optional[float] = Field(None, description="6-month performance %")


class StockDataCreate(StockDataBase):
    """Schema for creating stock data."""
    announcement_id: str
    company_id: str


class StockDataResponse(StockDataBase):
    """Schema for stock data response."""
    id: str
    announcement_id: str
    company_id: str
    fetched_at: datetime

    class Config:
        from_attributes = True


# Episodic memory schemas
class EpisodicMemoryBase(BaseModel):
    """Base schema for Episodic Memory."""
    event_date: datetime = Field(..., description="Date of the event")
    summary: str = Field(..., description="Event summary")
    sentiment: Optional[SentimentType] = None
    key_insights: Optional[List[str]] = None
    management_promises: Optional[List[str]] = None


class EpisodicMemoryCreate(EpisodicMemoryBase):
    """Schema for creating episodic memory."""
    company_id: str
    announcement_id: str


class EpisodicMemoryResponse(EpisodicMemoryBase):
    """Schema for episodic memory response."""
    id: str
    company_id: str
    announcement_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# Semantic memory schemas
class PromiseTracking(BaseModel):
    """Schema for promise tracking."""
    promise: str
    date_made: datetime
    status: PromiseStatus
    evidence: Optional[str] = None


class SemanticMemoryBase(BaseModel):
    """Base schema for Semantic Memory."""
    performance_trend: Optional[PerformanceTrend] = None
    recent_themes: Optional[List[str]] = None
    promise_tracking: Optional[Dict[str, PromiseTracking]] = None


class SemanticMemoryCreate(SemanticMemoryBase):
    """Schema for creating semantic memory."""
    company_id: str


class SemanticMemoryResponse(SemanticMemoryBase):
    """Schema for semantic memory response."""
    id: str
    company_id: str
    last_updated: datetime

    class Config:
        from_attributes = True


# Timeline comparison schemas
class TimelineComparisonBase(BaseModel):
    """Base schema for Timeline Comparison."""
    comparison_date: datetime
    improvement_score: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Improvement score (-1 to 1)")
    consistency_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Consistency score (0 to 1)")
    promise_fulfillment_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Promise fulfillment (0 to 1)")
    analysis_summary: Optional[str] = None
    promises_tracked: Optional[List[str]] = None


class TimelineComparisonCreate(TimelineComparisonBase):
    """Schema for creating timeline comparison."""
    company_id: str
    latest_announcement_id: str


class TimelineComparisonResponse(TimelineComparisonBase):
    """Schema for timeline comparison response."""
    id: str
    company_id: str
    latest_announcement_id: str
    created_at: datetime

    class Config:
        from_attributes = True


# Evaluation schemas
class EvaluationBase(BaseModel):
    """Base schema for Evaluation."""
    # Quality scoring (LLM-as-a-judge)
    summary_score: Optional[float] = Field(None, ge=1, le=5, description="Summary quality (1-5)")
    summary_feedback: Optional[str] = None
    sentiment_score: Optional[float] = Field(None, ge=1, le=5, description="Sentiment accuracy (1-5)")
    sentiment_feedback: Optional[str] = None
    insights_score: Optional[float] = Field(None, ge=1, le=5, description="Insights quality (1-5)")
    insights_feedback: Optional[str] = None
    overall_score: Optional[float] = Field(None, ge=1, le=5, description="Overall score (1-5)")
    overall_feedback: Optional[str] = None

    # Investment recommendation (BUY/HOLD/SELL/SPECULATIVE BUY/AVOID)
    recommendation: Optional[str] = Field(None, description="Investment recommendation: BUY, HOLD, SELL, SPECULATIVE BUY, or AVOID")
    recommendation_reasoning: Optional[str] = Field(None, description="Detailed reasoning for the recommendation")
    confidence_score: Optional[float] = Field(None, ge=0, le=1, description="Confidence in recommendation (0-1)")


class EvaluationCreate(EvaluationBase):
    """Schema for creating evaluation."""
    announcement_id: str
    processing_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None


class EvaluationResponse(EvaluationBase):
    """Schema for evaluation response."""
    id: str
    announcement_id: str
    processing_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    evaluated_at: datetime

    class Config:
        from_attributes = True


# Agent task schemas
class AgentTaskBase(BaseModel):
    """Base schema for Agent Task."""
    agent_id: str = Field(..., description="Agent identifier")
    task_type: str = Field(..., description="Type of task")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Task status")
    context_id: Optional[str] = None
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class AgentTaskCreate(AgentTaskBase):
    """Schema for creating agent task."""
    pass


class AgentTaskResponse(AgentTaskBase):
    """Schema for agent task response."""
    id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Combined response schemas
class AnnouncementWithAnalysis(AnnouncementResponse):
    """Announcement with analysis data."""
    analysis: Optional[AnalysisResponse] = None
    stock_data: Optional[List[StockDataResponse]] = None
    evaluation: Optional[EvaluationResponse] = None


class CompanyWithMemory(CompanyResponse):
    """Company with memory data."""
    episodic_memories: Optional[List[EpisodicMemoryResponse]] = None
    semantic_memory: Optional[SemanticMemoryResponse] = None
    timeline_comparisons: Optional[List[TimelineComparisonResponse]] = None


# A2A Protocol schemas
class A2AMessage(BaseModel):
    """A2A message schema."""
    role: str = Field(default="user", description="Message role")
    parts: List[Dict[str, Any]] = Field(..., description="Message parts")


class A2ATaskRequest(BaseModel):
    """A2A task request schema."""
    message: A2AMessage


class A2ATaskResponse(BaseModel):
    """A2A task response schema."""
    task_id: str = Field(..., description="Unique task identifier")
    context_id: str = Field(..., description="Context identifier")
    status: TaskStatus = Field(..., description="Task status")


class A2AArtifact(BaseModel):
    """A2A artifact schema."""
    type: str = Field(default="data", description="Artifact type")
    mime_type: str = Field(default="application/json", description="MIME type")
    data: Dict[str, Any] = Field(..., description="Artifact data")


class A2ATaskResult(BaseModel):
    """A2A task result schema."""
    task_id: str
    status: TaskStatus
    output: Optional[Dict[str, Any]] = None
    artifacts: Optional[List[A2AArtifact]] = None
    error: Optional[str] = None


# Pipeline schemas
class PipelineResult(BaseModel):
    """Complete pipeline execution result."""
    announcements_processed: int = Field(..., description="Number of announcements processed")
    summaries: List[AnalysisResponse] = Field(default_factory=list)
    timeline_comparisons: List[TimelineComparisonResponse] = Field(default_factory=list)
    quality_scores: List[EvaluationResponse] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    processing_time_ms: int = Field(..., description="Total processing time")


class TimelineAnalysisRequest(BaseModel):
    """Request for timeline analysis."""
    company_id: Optional[str] = None
    asx_code: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=100, description="Number of historical events to analyze")


class TimelineAnalysisResponse(BaseModel):
    """Response for timeline analysis."""
    company: CompanyResponse
    episodic_memories: List[EpisodicMemoryResponse]
    semantic_memory: Optional[SemanticMemoryResponse] = None
    latest_comparison: Optional[TimelineComparisonResponse] = None
    improvement_score: Optional[float] = None
    consistency_score: Optional[float] = None
    promise_fulfillment_score: Optional[float] = None
    analysis_summary: Optional[str] = None


# Trading decision schemas
class TradingDecisionBase(BaseModel):
    """Base schema for Trading Decision."""
    decision: str = Field(..., description="Trading decision: BUY, SELL, or HOLD")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0 to 1)")
    reasoning: str = Field(..., description="LLM reasoning for the decision")
    sentiment: Optional[str] = None
    current_price: Optional[float] = Field(None, gt=0, description="Current stock price")
    improvement_score: Optional[int] = Field(None, ge=0, le=10, description="Timeline improvement (0-10)")
    consistency_score: Optional[int] = Field(None, ge=0, le=10, description="Timeline consistency (0-10)")
    promise_fulfillment_score: Optional[int] = Field(None, ge=0, le=10, description="Promise fulfillment (0-10)")


class TradingDecisionCreate(TradingDecisionBase):
    """Schema for creating trading decision."""
    company_id: str
    announcement_id: Optional[str] = None


class TradingDecisionApproval(BaseModel):
    """Schema for human approval of trading decision."""
    decision_id: str = Field(..., description="Trading decision ID")
    action: str = Field(..., description="APPROVED or REJECTED")
    feedback: Optional[str] = Field(None, description="Optional human feedback")
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")


class TradingDecisionResponse(TradingDecisionBase):
    """Schema for trading decision response."""
    id: str
    company_id: str
    announcement_id: Optional[str] = None

    # Human approval
    human_approved: Optional[bool] = None
    human_decision: Optional[str] = None
    human_feedback: Optional[str] = None

    # Execution
    executed: bool = False
    trade_amount: float = 1000.0
    execution_price: Optional[float] = None
    quantity: Optional[float] = None

    # Timestamps
    created_at: datetime
    decided_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PendingApprovalsResponse(BaseModel):
    """Schema for listing pending approvals."""
    pending_approvals: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = Field(..., description="Number of pending approvals")


# Scraper Skill Schemas
class ScraperInput(BaseModel):
    """Input for the scraper skill."""
    asx_code: str = Field(..., description="ASX ticker code to scrape announcements for")
    price_sensitive_only: bool = Field(default=True, description="Filter only price-sensitive announcements")
    limit: Optional[int] = Field(default=None, description="Maximum number of announcements to return")
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")


class ScrapedAnnouncement(BaseModel):
    """Schema for a single scraped announcement."""
    asx_code: str
    company_name: str
    title: str
    pdf_url: str
    announcement_date: datetime
    is_price_sensitive: bool
    announcement_id: Optional[str] = None  # Set by scraper after creating DB record


class ScraperOutput(BaseModel):
    """Output for the scraper skill."""
    announcements: List[ScrapedAnnouncement]
    total_scraped: int
    new_count: int


# Analyzer Skill Schemas
class AnalyzerInput(BaseModel):
    """Input for the analyzer skill."""
    announcement_id: str
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")


class AnalyzerOutput(BaseModel):
    """Output for the analyzer skill."""
    announcement_id: str
    pdf_path: str
    markdown_path: str
    num_pages: int
    file_size_kb: int
    analysis: AnalysisResponse


# Stock Data Skill Schemas
class StockDataInput(BaseModel):
    """Input for the stock data skill."""
    asx_code: str
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")


class StockDataOutput(BaseModel):
    """Output for the stock data skill."""
    asx_code: str
    price: Optional[float]
    market_cap: Optional[float]
    performance_1m_pct: Optional[float]
    performance_3m_pct: Optional[float]
    performance_6m_pct: Optional[float]


# Memory Skill Schemas

# Store Episodic Memory
class StoreEpisodicMemoryInput(BaseModel):
    company_id: str
    announcement_id: str
    analysis_data: AnalysisResponse

class StoreEpisodicMemoryOutput(BaseModel):
    memory_id: str

# Retrieve Episodic Memory
class RetrieveEpisodicMemoryInput(BaseModel):
    company_id: str
    limit: int = 10

class RetrieveEpisodicMemoryOutput(BaseModel):
    memories: List[EpisodicMemoryResponse]
    count: int

# Update Semantic Memory
class UpdateSemanticMemoryInput(BaseModel):
    company_id: str
    performance_trend: PerformanceTrend
    recent_themes: List[str]
    promise_tracking: Dict[str, PromiseTracking]

class UpdateSemanticMemoryOutput(BaseModel):
    semantic_memory_id: str

# Compare Timeline
class CompareTimelineInput(BaseModel):
    company_id: str
    new_announcement_data: AnalysisResponse

class CompareTimelineOutput(BaseModel):
    comparison_id: str
    performance_trend: PerformanceTrend
    improvement_score: float
    consistency_score: float
    promise_fulfillment_score: float
    analysis_summary: str
    promise_tracking: List[PromiseTracking]
    strategic_shifts: str


# Evaluation Skill Schemas

# Evaluate Analysis Skill
class EvaluateAnalysisInput(BaseModel):
    original_content: str
    analysis_data: AnalysisResponse
    announcement_id: str
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")

class EvaluateAnalysisOutput(BaseModel):
    summary_score: float
    summary_feedback: str
    sentiment_score: float
    sentiment_feedback: str
    insights_score: float
    insights_feedback: str
    overall_score: float
    overall_feedback: str
    processing_time_ms: int
    tokens_used: int

# Get Aggregate Scores Skill
class GetAggregateScoresInput(BaseModel):
    min_date: Optional[datetime] = None

class GetAggregateScoresOutput(BaseModel):
    count: int
    avg_summary_score: Optional[float] = None
    avg_sentiment_score: Optional[float] = None
    avg_insights_score: Optional[float] = None
    avg_overall_score: Optional[float] = None
    min_overall_score: Optional[float] = None
    max_overall_score: Optional[float] = None


# Trading Skill Schemas

# Make Trading Decision Skill
class MakeTradingDecisionInput(BaseModel):
    asx_code: str
    company_id: str
    announcement_id: Optional[str] = None
    analysis_data: AnalysisResponse
    stock_data: StockDataOutput
    timeline_data: Optional[CompareTimelineOutput] = None
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")

class MakeTradingDecisionOutput(BaseModel):
    decision_id: str
    decision: str
    confidence_score: float
    reasoning: str
    status: str
    approved: Optional[bool] = None
    executed: Optional[bool] = False

# Approve Trading Decision Skill
class ApproveTradingDecisionInput(BaseModel):
    decision_id: str
    approved: bool
    approval_notes: Optional[str] = None
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")

class ApproveTradingDecisionOutput(BaseModel):
    decision_id: str
    status: str
    executed: bool

# Get Pending Approvals Skill
class GetPendingApprovalsInput(BaseModel):
    limit: int = 20

class GetPendingApprovalsOutput(BaseModel):
    pending_decisions: List[TradingDecisionResponse]
    count: int


# Coordinator Skill Schemas
class RunPipelineInput(BaseModel):
    asx_code: str = Field(..., description="ASX ticker code to process announcements for")
    price_sensitive_only: bool = True
    limit: Optional[int] = None
    enable_evaluation: bool = True
    watchlist_codes: Optional[List[str]] = None
    task_id: Optional[str] = Field(default=None, description="The ID for the current request, used for logging.")

class RunPipelineOutput(BaseModel):
    announcements_processed: int
    analyses: List[Dict[str, Any]]
    stock_data: List[Dict[str, Any]]
    timeline_comparisons: List[Dict[str, Any]]
    evaluations: List[Dict[str, Any]]
    trading_signals: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
