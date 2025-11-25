"""
Tests for the refactored, skill-based agent architecture.
"""
import pytest
from unittest.mock import patch, AsyncMock

from agents.scraper.skills import scrape_asx_announcements
from agents.analyzer.skills import process_and_analyze_announcement
from models.schemas import ScraperInput, AnalyzerInput

# ============================================================================
# Scraper Skill Tests
# ============================================================================

@pytest.mark.asyncio
@patch('agents.scraper.skills.get_db_session')
@patch('agents.scraper.skills.httpx.AsyncClient')
async def test_scrape_asx_announcements_skill(MockAsyncClient, mock_get_db_session):
    """Unit test for the scrape_asx_announcements skill."""
    # Mock the HTTP response from ASX
    mock_response = AsyncMock()
    mock_response.text = """
    <table>
        <tr><td>BHP</td><td>BHP Group</td><td>Some Announcement</td><td><a href="/some/path.pdf">PDF</a></td><td>19/11/2025 10:00:00</td><td>$</td></tr>
        <tr><td>CBA</td><td>Commonwealth Bank</td><td>Another One</td><td><a href="/another.pdf">PDF</a></td><td>19/11/2025 11:00:00</td><td></td></tr>
    </table>
    """
    mock_response.raise_for_status = lambda: None
    MockAsyncClient.return_value.__aenter__.return_value.get.return_value = mock_response

    # Mock the database query to simulate no duplicates
    mock_db_session = mock_get_db_session.return_value.__enter__.return_value
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    # Execute the skill
    input_data = ScraperInput(price_sensitive_only=False, limit=5)
    result = await scrape_asx_announcements(input_data)

    # Assertions
    assert result.total_scraped == 2
    assert result.new_count == 2
    assert len(result.announcements) == 2
    assert result.announcements[0].asx_code == "BHP"
    assert result.announcements[0].is_price_sensitive is True
    assert result.announcements[1].asx_code == "CBA"
    assert result.announcements[1].is_price_sensitive is False

@pytest.mark.asyncio
@patch('agents.scraper.skills.get_db_session')
@patch('agents.scraper.skills.httpx.AsyncClient')
async def test_scrape_asx_announcements_skill_price_sensitive(MockAsyncClient, mock_get_db_session):
    """Test the scraper skill with price_sensitive_only=True."""
    mock_response = AsyncMock()
    mock_response.text = """
    <table>
        <tr><td>BHP</td><td>BHP Group</td><td>Some Announcement</td><td><a href="/some/path.pdf">PDF</a></td><td>19/11/2025 10:00:00</td><td>$</td></tr>
        <tr><td>CBA</td><td>Commonwealth Bank</td><td>Another One</td><td><a href="/another.pdf">PDF</a></td><td>19/11/2025 11:00:00</td><td></td></tr>
    </table>
    """
    mock_response.raise_for_status = lambda: None
    MockAsyncClient.return_value.__aenter__.return_value.get.return_value = mock_response

    mock_db_session = mock_get_db_session.return_value.__enter__.return_value
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    input_data = ScraperInput(price_sensitive_only=True)
    result = await scrape_asx_announcements(input_data)

    assert result.total_scraped == 2
    assert result.new_count == 1
    assert len(result.announcements) == 1
    assert result.announcements[0].asx_code == "BHP"

# ============================================================================
# Analyzer Skill Tests
# ============================================================================

@pytest.mark.asyncio
@patch('agents.analyzer.skills.get_db_session')
@patch('agents.analyzer.skills.httpx.AsyncClient')
@patch('agents.analyzer.skills.fitz.open')
@patch('agents.analyzer.skills.gemini_model')
async def test_process_and_analyze_announcement_skill(mock_gemini_model, mock_fitz_open, MockAsyncClient, mock_get_db_session):
    """Unit test for the process_and_analyze_announcement skill."""
    # Mock PDF download
    mock_pdf_response = AsyncMock()
    mock_pdf_response.content = b'fake-pdf-content'
    mock_pdf_response.raise_for_status = lambda: None
    MockAsyncClient.return_value.__aenter__.return_value.get.return_value = mock_pdf_response

    # Mock PDF processing
    mock_pdf_doc = MagicMock()
    mock_pdf_doc.page_count = 1
    mock_pdf_doc.__len__.return_value = 1
    mock_pdf_page = MagicMock()
    mock_pdf_page.get_text.return_value = "This is the PDF content."
    mock_pdf_doc.__iter__.return_value = iter([mock_pdf_page])
    mock_fitz_open.return_value = mock_pdf_doc
    
    # Mock Path object
    with patch('agents.analyzer.skills.Path') as MockPath:
        mock_path_instance = MockPath.return_value
        mock_path_instance.exists.return_value = False
        mock_path_instance.stat.return_value.st_size = 10240 # 10 KB

        # Mock Gemini response
        mock_gemini_response = AsyncMock()
        mock_gemini_response.text = '{"summary": "A summary.", "sentiment": "NEUTRAL", "key_insights": ["An insight."], "management_promises": [], "financial_impact": "None"}'
        mock_gemini_model.generate_content_async.return_value = mock_gemini_response
        
        # Mock DB
        mock_db_session = mock_get_db_session.return_value.__enter__.return_value
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        input_data = AnalyzerInput(
            announcement_id="ann-123",
            pdf_url="http://example.com/doc.pdf",
            company_name="TestCorp",
            asx_code="TC"
        )
        result = await process_and_analyze_announcement(input_data)

        # Assertions
        assert result.announcement_id == "ann-123"
        assert result.num_pages == 1
        assert result.file_size_kb == 10
        assert result.analysis.summary == "A summary."
        assert result.analysis.sentiment == "NEUTRAL"
        mock_gemini_model.generate_content_async.assert_called_once()


# Placeholder for other agent skill tests
def test_stock_agent_skills():
    pass

def test_memory_agent_skills():
    pass

def test_evaluation_agent_skills():
    pass

def test_trading_agent_skills():
    pass

def test_coordinator_skills():
    pass
