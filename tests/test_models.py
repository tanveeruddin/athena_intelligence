"""
Tests for database models and relationships.
"""

import pytest
from datetime import datetime
import json

from models.database import get_db_session
from models.orm_models import (
    Company, Announcement, Analysis, StockData,
    EpisodicMemory, SemanticMemory, TimelineComparison,
    Evaluation, AgentTask
)


class TestCompany:
    """Test Company model."""

    def test_create_company(self, test_db):
        """Test creating a company."""
        with get_db_session() as db:
            company = Company(
                asx_code="BHP",
                company_name="BHP Group Limited",
                industry="Mining"
            )
            db.add(company)
            db.commit()

            assert company.id is not None
            assert company.asx_code == "BHP"
            assert company.company_name == "BHP Group Limited"

    def test_company_unique_asx_code(self, test_db, sample_company):
        """Test that ASX code must be unique."""
        with pytest.raises(Exception):
            with get_db_session() as db:
                duplicate = Company(
                    asx_code=sample_company.asx_code,
                    company_name="Another Company"
                )
                db.add(duplicate)
                db.commit()


class TestAnnouncement:
    """Test Announcement model."""

    def test_create_announcement(self, test_db, sample_company):
        """Test creating an announcement."""
        with get_db_session() as db:
            announcement = Announcement(
                company_id=sample_company.id,
                asx_code=sample_company.asx_code,
                title="Test Announcement",
                announcement_date=datetime.now(),
                pdf_url="https://example.com/test.pdf",
                is_price_sensitive=True
            )
            db.add(announcement)
            db.commit()

            assert announcement.id is not None
            assert announcement.company_id == sample_company.id

    def test_announcement_company_relationship(self, test_db, sample_announcement):
        """Test announcement-company relationship."""
        with get_db_session() as db:
            announcement = db.query(Announcement).filter(
                Announcement.id == sample_announcement.id
            ).first()

            assert announcement.company is not None
            assert announcement.company.asx_code == sample_announcement.asx_code


class TestAnalysis:
    """Test Analysis model."""

    def test_create_analysis(self, test_db, sample_announcement):
        """Test creating an analysis."""
        with get_db_session() as db:
            analysis = Analysis(
                announcement_id=sample_announcement.id,
                summary="Test summary",
                sentiment="BULLISH",
                key_insights=json.dumps(["Insight 1", "Insight 2"]),
                financial_impact="Positive"
            )
            db.add(analysis)
            db.commit()

            assert analysis.id is not None
            assert analysis.sentiment == "BULLISH"

    def test_sentiment_constraint(self, test_db, sample_announcement):
        """Test sentiment must be valid value."""
        with pytest.raises(Exception):
            with get_db_session() as db:
                analysis = Analysis(
                    announcement_id=sample_announcement.id,
                    summary="Test",
                    sentiment="INVALID",
                    key_insights=json.dumps([])
                )
                db.add(analysis)
                db.commit()


class TestMemory:
    """Test memory models."""

    def test_create_episodic_memory(self, test_db, sample_company, sample_announcement):
        """Test creating episodic memory."""
        with get_db_session() as db:
            memory = EpisodicMemory(
                company_id=sample_company.id,
                announcement_id=sample_announcement.id,
                event_date=datetime.now(),
                summary="Test memory",
                sentiment="BULLISH",
                key_insights=json.dumps(["Insight"])
            )
            db.add(memory)
            db.commit()

            assert memory.id is not None

    def test_create_semantic_memory(self, test_db, sample_company):
        """Test creating semantic memory."""
        with get_db_session() as db:
            memory = SemanticMemory(
                company_id=sample_company.id,
                performance_trend="IMPROVING",
                recent_themes=json.dumps(["growth", "efficiency"]),
                promise_tracking=json.dumps({"p1": {"status": "ON_TRACK"}})
            )
            db.add(memory)
            db.commit()

            assert memory.id is not None
            assert memory.performance_trend == "IMPROVING"

    def test_timeline_comparison(self, test_db, sample_company, sample_announcement):
        """Test timeline comparison."""
        with get_db_session() as db:
            comparison = TimelineComparison(
                company_id=sample_company.id,
                latest_announcement_id=sample_announcement.id,
                comparison_date=datetime.now(),
                improvement_score=0.75,
                consistency_score=0.85,
                promise_fulfillment_score=0.90,
                analysis_summary="Strong performance"
            )
            db.add(comparison)
            db.commit()

            assert comparison.id is not None
            assert 0.0 <= comparison.improvement_score <= 1.0


class TestEvaluation:
    """Test Evaluation model."""

    def test_create_evaluation(self, test_db, sample_announcement):
        """Test creating an evaluation."""
        with get_db_session() as db:
            evaluation = Evaluation(
                announcement_id=sample_announcement.id,
                summary_score=4.5,
                sentiment_score=5.0,
                insights_score=4.0,
                overall_score=4.5,
                overall_feedback="Good quality analysis"
            )
            db.add(evaluation)
            db.commit()

            assert evaluation.id is not None
            assert 1.0 <= evaluation.overall_score <= 5.0


class TestAgentTask:
    """Test AgentTask model."""

    def test_create_agent_task(self, test_db):
        """Test creating an agent task."""
        with get_db_session() as db:
            task = AgentTask(
                agent_id="test-agent",
                task_type="test-task",
                status="pending",
                input_data=json.dumps({"param": "value"})
            )
            db.add(task)
            db.commit()

            assert task.id is not None
            assert task.status == "pending"
