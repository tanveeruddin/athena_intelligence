# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Trading Agent - Remote A2A agent with Human-in-the-Loop using LongRunningFunctionTool.

This agent runs as a separate A2A service and handles trade execution with human approval.
Uses LongRunningFunctionTool to pause execution and surface approval requests to root agent.
"""
import os
from typing import Any

from google.adk import Agent
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .skills import execute_trade, approve_trade, get_trade_history
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Ensure GEMINI_API_KEY is set
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key


# ============================================================================
# TRADING AGENT WITH LONG-RUNNING TOOL FOR HUMAN APPROVAL
# ============================================================================

trading_agent = Agent(
    model=settings.gemini_model,
    name="asx_trading_agent",
    instruction="""You are a trading agent that handles stock trade execution with human approval.

Your tools:
1. execute_trade: Creates a pending trade decision (returns immediately with ticket_id)
2. approve_trade: Approves/rejects a pending trade and executes if approved
3. get_trade_history: Retrieves recent trading decisions

WORKFLOW:
- When asked to execute a trade: Use execute_trade to create pending decision
- When asked to approve a trade: Use approve_trade with ticket_id
- The root agent handles human interaction and calls approve_trade after getting approval

Always provide clear information about the trade status and next steps.""",
    tools=[
        LongRunningFunctionTool(func=execute_trade),
        approve_trade,
        get_trade_history,
    ],
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
)
