"""
Test configuration and fixtures for the test suite.
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil
from datetime import datetime

from models.database import Base, get_engine, get_db_session, create_all_tables
from models.orm_models import Company, Announcement, Analysis
from utils.config import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_settings():
    """Get test settings."""
    settings = get_settings()
    # Override for testing
    settings.database_url = "sqlite:///:memory:"
    settings.log_level = "ERROR"
    return settings


@pytest.fixture(scope="function")
def test_db():
    """Create a test database for each test function."""
    # Create in-memory database
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    yield

    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_company():
    """Create a sample company."""
    with get_db_session() as db:
        company = Company(
            asx_code="TST",
            company_name="Test Company Limited",
            industry="Technology"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        return company


@pytest.fixture
def sample_announcement(sample_company):
    """Create a sample announcement."""
    with get_db_session() as db:
        announcement = Announcement(
            company_id=sample_company.id,
            asx_code=sample_company.asx_code,
            title="Test Quarterly Results",
            announcement_date=datetime.now(),
            pdf_url="https://example.com/test.pdf",
            is_price_sensitive=True
        )
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        return announcement


@pytest.fixture
def sample_analysis(sample_announcement):
    """Create a sample analysis."""
    import json
    with get_db_session() as db:
        analysis = Analysis(
            announcement_id=sample_announcement.id,
            summary="Test summary of quarterly results",
            sentiment="BULLISH",
            key_insights=json.dumps(["Revenue up 10%", "Strong margins", "Market share gain"]),
            management_promises=json.dumps(["Maintain guidance", "Focus on efficiency"]),
            financial_impact="Positive impact expected"
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file tests."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def mock_pdf_content():
    """Mock PDF content for testing."""
    return b"%PDF-1.4\n%Mock PDF content for testing\n%%EOF"


@pytest.fixture
def mock_html_content():
    """Mock ASX HTML content for testing."""
    return """
    <html>
    <body>
        <table>
            <tr>
                <td>TST</td>
                <td>Test Company</td>
                <td>Quarterly Results</td>
                <td><a href="/announcements/test.pdf">PDF</a></td>
                <td>10:30:00</td>
                <td>$</td>
            </tr>
        </table>
    </body>
    </html>
    """


@pytest.fixture
def mock_gemini_response():
    """Mock Gemini API response."""
    return """
    {
        "summary": "Test company reports strong quarterly results with revenue growth.",
        "sentiment": "BULLISH",
        "key_insights": [
            "Revenue increased 10% year-over-year",
            "Profit margins improved to 25%",
            "New product launch successful"
        ],
        "management_promises": [
            "Maintain FY guidance",
            "Continue R&D investment"
        ],
        "financial_impact": "Positive impact on earnings expected"
    }
    """
