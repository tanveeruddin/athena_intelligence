"""
Stock Agent - ADK-based agent for fetching stock market data.
Retrieves current prices, market cap, and performance metrics for ASX stocks using yfinance.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from google.adk.agents import LlmAgent
from google.adk.tools.function_tool import FunctionTool
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .skills import get_stock_data
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()


# ============================================================================
# ADK AGENT DEFINITION
# ============================================================================

# Wrap stock skill as ADK tool
stock_data_tool = FunctionTool(get_stock_data)

# Create LlmAgent with stock tools
stock_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="asx_stock",
    description="Fetches stock market data and performance metrics using yfinance",
    instruction="""
You are an ASX Stock Data Agent. Your job is to fetch stock market data for ASX companies.

When asked for stock data:
1. Use the get_stock_data tool with input_data parameter
2. The input_data should contain: asx_code (required)
3. This will fetch current price, market cap, and 1M/3M/6M performance metrics using yfinance

The tool will return StockDataOutput containing:
- Current stock price
- Market capitalization
- Performance percentages (1-month, 3-month, 6-month)

Always provide clear, data-driven responses with specific numbers and metrics.
    """.strip(),
    tools=[stock_data_tool],
)


# ============================================================================
# A2A SERVER APP
# ============================================================================

# Convert ADK agent to A2A Starlette application
app = to_a2a(
    stock_agent,
    host="localhost",
    port=settings.stock_agent_port,
    protocol="http"
)
