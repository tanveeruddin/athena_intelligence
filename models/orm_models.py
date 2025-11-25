
"""
SQLAlchemy ORM models for the ASX Announcement Scraper.
Defines all database tables and relationships.
"""

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from models.database import Base


def generate_uuid():
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Company(Base):
    """Companies table - stores ASX-listed companies."""

    __tablename__ = "companies"

    id = Column(String, primary_key=True, default=generate_uuid)
    asx_code = Column(String, unique=True, nullable=False, index=True)
    company_name = Column(String, nullable=False)
    industry = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    announcements = relationship("Announcement", back_populates="company", cascade="all, delete-orphan")
    stock_data = relationship("StockData", back_populates="company", cascade="all, delete-orphan")
    episodic_memories = relationship("EpisodicMemory", back_populates="company", cascade="all, delete-orphan")
    semantic_memory = relationship("SemanticMemory", back_populates="company", cascade="all, delete-orphan", uselist=False)
    timeline_comparisons = relationship("TimelineComparison", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company(asx_code='{self.asx_code}', name='{self.company_name}')>"


class Announcement(Base):
    """Announcements table - stores ASX announcements."""

    __tablename__ = "announcements"

    id = Column(String, primary_key=True, default=generate_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    asx_code = Column(String, nullable=False, index=True)
    title = Column(Text, nullable=False)
    announcement_date = Column(DateTime, nullable=False, index=True)
    pdf_url = Column(Text, nullable=False)
    pdf_local_path = Column(String, nullable=True)
    markdown_path = Column(String, nullable=True)
    is_price_sensitive = Column(Boolean, default=False)
    num_pages = Column(Integer, nullable=True)
    file_size_kb = Column(Integer, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", back_populates="announcements")
    analysis = relationship("Analysis", back_populates="announcement", cascade="all, delete-orphan", uselist=False)
    stock_data = relationship("StockData", back_populates="announcement", cascade="all, delete-orphan")
    episodic_memory = relationship("EpisodicMemory", back_populates="announcement", cascade="all, delete-orphan", uselist=False)
    timeline_comparisons = relationship("TimelineComparison", back_populates="latest_announcement", cascade="all, delete-orphan")
    evaluation = relationship("Evaluation", back_populates="announcement", cascade="all, delete-orphan", uselist=False)

    # Unique constraint for duplicate detection
    __table_args__ = (
        Index("idx_announcements_unique", "asx_code", "announcement_date", "title", unique=True),
        Index("idx_announcements_company", "company_id"),
        Index("idx_announcements_date", "announcement_date"),
    )

    def __repr__(self):
        return f"<Announcement(asx_code='{self.asx_code}', title='{self.title[:50]}...', date='{self.announcement_date}')>"


class Analysis(Base):
    """Analysis table - stores AI-generated analysis of announcements."""

    __tablename__ = "analysis"

    id = Column(String, primary_key=True, default=generate_uuid)
    announcement_id = Column(String, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, unique=True)
    summary = Column(Text, nullable=True)
    sentiment = Column(String, nullable=True)
    key_insights = Column(Text, nullable=True)  # JSON array stored as text
    management_promises = Column(Text, nullable=True)  # JSON array stored as text
    financial_impact = Column(Text, nullable=True)
    llm_model = Column(String, default="gemini-2.0-flash-exp")
    processing_time_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    announcement = relationship("Announcement", back_populates="analysis")

    # Check constraint for sentiment
    __table_args__ = (
        CheckConstraint(
            "sentiment IN ('BULLISH', 'BEARISH', 'NEUTRAL')",
            name="check_sentiment_values"
        ),
    )

    def __repr__(self):
        return f"<Analysis(announcement_id='{self.announcement_id}', sentiment='{self.sentiment}')>"


class StockData(Base):
    """Stock data table - stores market data for announcements."""

    __tablename__ = "stock_data"

    id = Column(String, primary_key=True, default=generate_uuid)
    announcement_id = Column(String, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    price_at_announcement = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    performance_1m_pct = Column(Float, nullable=True)
    performance_3m_pct = Column(Float, nullable=True)
    performance_6m_pct = Column(Float, nullable=True)
    fetched_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    announcement = relationship("Announcement", back_populates="stock_data")
    company = relationship("Company", back_populates="stock_data")

    def __repr__(self):
        return f"<StockData(company_id='{self.company_id}', price={self.price_at_announcement})>"


class EpisodicMemory(Base):
    """Episodic memory table - stores timeline events for companies."""

    __tablename__ = "episodic_memory"

    id = Column(String, primary_key=True, default=generate_uuid)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    announcement_id = Column(String, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, unique=True)
    event_date = Column(DateTime, nullable=False, index=True)
    summary = Column(Text, nullable=False)
    sentiment = Column(String, nullable=True)
    key_insights = Column(Text, nullable=True)  # JSON array
    management_promises = Column(Text, nullable=True)  # JSON array
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", back_populates="episodic_memories")
    announcement = relationship("Announcement", back_populates="episodic_memory")

    # Index for efficient timeline queries
    __table_args__ = (
        Index("idx_episodic_memory_company_date", "company_id", "event_date"),
    )

    def __repr__(self):
        return f"<EpisodicMemory(company_id='{self.company_id}', event_date='{self.event_date}')>"


class SemanticMemory(Base):
    """Semantic memory table - stores aggregated company knowledge."""

    __tablename__ = "semantic_memory"

    id = Column(String, primary_key=True, default=generate_uuid)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    performance_trend = Column(String, nullable=True)
    recent_themes = Column(Text, nullable=True)  # JSON array
    promise_tracking = Column(Text, nullable=True)  # JSON object
    last_updated = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", back_populates="semantic_memory")

    # Check constraint for performance trend
    __table_args__ = (
        CheckConstraint(
            "performance_trend IN ('IMPROVING', 'STABLE', 'DECLINING')",
            name="check_performance_trend_values"
        ),
    )

    def __repr__(self):
        return f"<SemanticMemory(company_id='{self.company_id}', trend='{self.performance_trend}')>"


class TimelineComparison(Base):
    """Timeline comparisons table - stores historical analysis results."""

    __tablename__ = "timeline_comparisons"

    id = Column(String, primary_key=True, default=generate_uuid)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    latest_announcement_id = Column(String, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False)
    comparison_date = Column(DateTime, nullable=False, index=True)
    improvement_score = Column(Float, nullable=True)
    consistency_score = Column(Float, nullable=True)
    promise_fulfillment_score = Column(Float, nullable=True)
    analysis_summary = Column(Text, nullable=True)
    promises_tracked = Column(Text, nullable=True)  # JSON array
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", back_populates="timeline_comparisons")
    latest_announcement = relationship("Announcement", back_populates="timeline_comparisons")

    # Index for efficient queries
    __table_args__ = (
        Index("idx_timeline_comparisons_company", "company_id"),
    )

    def __repr__(self):
        return f"<TimelineComparison(company_id='{self.company_id}', improvement_score={self.improvement_score})>"


class Evaluation(Base):
    """Evaluations table - stores LLM-as-a-Judge quality scores and investment recommendations."""

    __tablename__ = "evaluations"

    id = Column(String, primary_key=True, default=generate_uuid)
    announcement_id = Column(String, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Quality scoring
    summary_score = Column(Float, nullable=True)
    summary_feedback = Column(Text, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    sentiment_feedback = Column(Text, nullable=True)
    insights_score = Column(Float, nullable=True)
    insights_feedback = Column(Text, nullable=True)
    overall_score = Column(Float, nullable=True)
    overall_feedback = Column(Text, nullable=True)

    # Investment recommendation
    recommendation = Column(String(50), nullable=True)  # BUY, HOLD, SELL, SPECULATIVE BUY, AVOID
    recommendation_reasoning = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    processing_time_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    evaluated_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    announcement = relationship("Announcement", back_populates="evaluation")

    # Check constraints for scores (1-5 range)
    __table_args__ = (
        CheckConstraint("summary_score BETWEEN 1 AND 5", name="check_summary_score"),
        CheckConstraint("sentiment_score BETWEEN 1 AND 5", name="check_sentiment_score"),
        CheckConstraint("insights_score BETWEEN 1 AND 5", name="check_insights_score"),
        CheckConstraint("overall_score BETWEEN 1 AND 5", name="check_overall_score"),
    )

    def __repr__(self):
        return f"<Evaluation(announcement_id='{self.announcement_id}', overall_score={self.overall_score})>"


class AgentTask(Base):
    """Agent tasks table - stores A2A task tracking."""

    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    agent_id = Column(String, nullable=False, index=True)
    task_type = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)
    context_id = Column(String, nullable=True)
    input_data = Column(Text, nullable=True)  # JSON
    output_data = Column(Text, nullable=True)  # JSON
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Check constraint for status
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'failed')",
            name="check_status_values"
        ),
        Index("idx_agent_tasks_status", "status"),
    )

    def __repr__(self):
        return f"<AgentTask(id='{self.id}', agent_id='{self.agent_id}', status='{self.status}')>"


class TradingDecision(Base):
    """Trading decisions table - stores trading recommendations with human approval."""

    __tablename__ = "trading_decisions"

    id = Column(String, primary_key=True, default=generate_uuid)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    announcement_id = Column(String, ForeignKey("announcements.id", ondelete="SET NULL"), nullable=True)

    # Company/Stock info
    asx_code = Column(String, nullable=False)
    ticket_id = Column(String, nullable=True, unique=True, index=True)  # Long-running tool ticket ID
    task_id = Column(String, nullable=True, index=True) # The ID for the current request, used for logging.

    # Trading decision
    decision = Column(String, nullable=False)  # BUY/SELL/HOLD
    decision_type = Column(String, nullable=False)  # BUY/HOLD/SELL/SPECULATIVE BUY
    confidence_score = Column(Float, nullable=True)
    recommendation_score = Column(Float, nullable=True)  # Confidence from evaluation agent
    reasoning = Column(Text, nullable=False)
    status = Column(String, default="PENDING", nullable=False)  # PENDING/APPROVED/REJECTED

    # Input data used for decision
    price_at_decision = Column(Float, nullable=True)  # Stock price when decision was made
    sentiment = Column(String, nullable=True)
    current_price = Column(Float, nullable=True)
    improvement_score = Column(Integer, nullable=True)
    consistency_score = Column(Integer, nullable=True)
    promise_fulfillment_score = Column(Integer, nullable=True)

    # Human approval
    human_approved = Column(Boolean, default=None, nullable=True)
    human_decision = Column(String, nullable=True)  # APPROVED/REJECTED
    human_feedback = Column(Text, nullable=True)
    approved_by = Column(String, nullable=True)  # Who approved (human identifier)

    # Paper trade execution
    executed = Column(Boolean, default=False, nullable=False)
    trade_amount = Column(Float, default=1000.0, nullable=False)
    execution_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    decided_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)

    # Relationships
    company = relationship("Company", backref="trading_decisions")
    announcement = relationship("Announcement", backref="trading_decisions")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint(
            "decision IN ('BUY', 'SELL', 'HOLD')",
            name="check_decision_values"
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="check_status_values"
        ),
        CheckConstraint(
            "human_decision IN ('APPROVED', 'REJECTED') OR human_decision IS NULL",
            name="check_human_decision_values"
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="check_confidence_score_range"
        ),
        Index("idx_trading_decisions_company", "company_id"),
        Index("idx_trading_decisions_approval", "human_approved"),
        Index("idx_trading_decisions_created", "created_at"),
    )

    def __repr__(self):
        return f"<TradingDecision(id='{self.id}', decision='{self.decision}', approved={self.human_approved})>"

class LogMessage(Base):
    """Log messages table - stores log messages from agents."""

    __tablename__ = "log_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_log_messages_task_id", "task_id"),
    )

    def __repr__(self):
        return f"<LogMessage(agent_name='{self.agent_name}', message='{self.message[:50]}...')>"

