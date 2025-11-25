"""
Scraper Agent - ADK-based agent for scraping ASX announcements.
Fetches and filters price-sensitive announcements from ASX website.
"""

from typing import Optional, Dict, Any

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .skills import scrape_asx_announcements
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()


# ============================================================================
# ADK AGENT DEFINITION
# ============================================================================

# Wrap scraper skill as ADK tool
scraper_tool = FunctionTool(scrape_asx_announcements)

# Create LlmAgent with the scraper tool
scraper_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="asx_scraper",
    description="Scrapes and filters price-sensitive announcements from the ASX website",
    instruction="""
You are an ASX Announcement Scraper Agent. Your job is to fetch announcements from the ASX website.

When asked to scrape or fetch announcements:
1. Use the scrape_asx_announcements tool with the required input_data parameter
2. The input_data should contain: asx_code, limit (optional), and price_sensitive_only (optional)
3. Return the ScraperOutput showing total_scraped, new_count, and list of announcements

Always provide clear, concise summaries of the scraping results.
    """.strip(),
    tools=[scraper_tool],
)


# ============================================================================
# A2A SERVER APP
# ============================================================================

# Convert ADK agent to A2A Starlette application
app = to_a2a(
    scraper_agent,
    host="localhost",
    port=settings.scraper_agent_port,
    protocol="http"
)
