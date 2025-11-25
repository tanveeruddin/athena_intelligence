"""
Analyzer Agent - ADK-based agent for PDF processing and LLM analysis.
Downloads PDFs, converts to markdown, and generates AI-powered insights using Gemini.
"""

from typing import Dict, Any, Optional

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .skills import process_and_analyze_announcement
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()


# ============================================================================
# ADK AGENT DEFINITION
# ============================================================================

# Wrap analysis skill as ADK tool
analyzer_tool = FunctionTool(process_and_analyze_announcement)

# Create LlmAgent with analysis tools
analyzer_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="asx_analyzer",
    description="Processes PDF announcements and generates AI-powered analysis",
    instruction="""
You are an ASX Announcement Analyzer Agent. Your job is to process PDF announcements and generate insightful analysis.

When given an announcement:
1. Use the process_and_analyze_announcement tool with input_data parameter
2. The input_data should contain: pdf_url, announcement_id, company_name, and asx_code
3. This will download the PDF, convert to markdown, and generate AI-powered analysis in one step

The tool will return AnalyzerOutput containing:
- PDF metadata (path, pages, size)
- Markdown path
- Analysis results (summary, sentiment, key_insights, management_promises, financial_impact)

Always provide clear summaries of the analysis results.
    """.strip(),
    tools=[analyzer_tool],
)


# ============================================================================
# A2A SERVER APP
# ============================================================================

# Convert ADK agent to A2A Starlette application
app = to_a2a(
    analyzer_agent,
    host="localhost",
    port=settings.analyzer_agent_port,
    protocol="http"
)
