
"""
Coordinator Agent - ADK-based orchestrator for the multi-agent system.

This is the ROOT AGENT that has access to the user and coordinates the entire pipeline.
It delegates to the Trading Agent (remote A2A) for human-in-the-loop trade execution.
"""
import os
from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.genai import types

from models.schemas import RunPipelineInput, RunPipelineOutput
from .skills import run_announcement_pipeline
from utils.config import get_settings

settings = get_settings()

# Ensure GEMINI_API_KEY is set from settings if available
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# Define the coordinator's skills
skills = [
    FunctionTool(run_announcement_pipeline),
]

# Configure Trading Agent as a remote A2A sub-agent
# This agent handles trade execution with human-in-the-loop approval
trading_agent_remote = RemoteA2aAgent(
    name='trading_agent',
    description='Handles stock trade execution with human approval. Use this agent when a BUY or SPECULATIVE BUY recommendation is made.',
    agent_card=(
        f'http://localhost:{settings.trading_agent_port}/a2a/asx_trading_agent{AGENT_CARD_WELL_KNOWN_PATH}'
    ),
)

# Create the coordinator Agent (ROOT AGENT)
# Note: Agent reads GEMINI_API_KEY from environment variable (set above)
coordinator_agent = Agent(
    model=settings.gemini_model,
    name="asx_coordinator_agent",
    instruction="""You are the main coordinator agent for the ASX announcement processing pipeline.

Your responsibilities:
1. Run the announcement processing pipeline (scraper → analyzer → stock → evaluation)
2. When a BUY or SPECULATIVE BUY recommendation is made, delegate to the trading_agent for execution
3. The trading_agent will request human approval - you should surface this to the user
4. After receiving human approval/rejection, inform the trading_agent to proceed

IMPORTANT: task_id handling
- When you receive a message, check if it contains a task_id in the message parts (as data).
- If a task_id is present, you MUST extract it and pass it to the run_announcement_pipeline function.
- The task_id is crucial for tracking logs and must be preserved throughout the pipeline.
- Format: run_announcement_pipeline(asx_code="XXX", limit=N, task_id="the-task-id-from-message")

Example:
- User message: "analyze BHP limit 5"
- Message parts may include: {"data": {"task_id": "abc-123"}}
- You should call: run_announcement_pipeline(asx_code="BHP", limit=5, task_id="abc-123")

Use the run_announcement_pipeline tool to process announcements.
Use the trading_agent sub-agent when trade execution with approval is needed.""",
    tools=skills,
    sub_agents=[trading_agent_remote],
    generate_content_config=types.GenerateContentConfig(temperature=0.3),
)

# Convert the Agent to an A2A-compliant FastAPI application
app = to_a2a(
    coordinator_agent,
    host="localhost",
    port=settings.coordinator_agent_port,
    protocol="http"
)



