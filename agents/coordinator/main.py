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
Coordinator Agent A2A Server - ROOT AGENT with access to user.

Orchestrates the pipeline and delegates to Trading Agent for HTIL.
"""
import os
import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from utils.config import get_settings
from utils.logging import get_logger
from utils.observability import setup_phoenix_instrumentation
from .agent import coordinator_agent

logger = get_logger()
settings = get_settings()

# Ensure GEMINI_API_KEY is set from settings if available
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

# Convert the Coordinator Agent to an A2A-compliant FastAPI application
app = to_a2a(
    coordinator_agent,
    host="localhost",
    port=settings.coordinator_agent_port,
    protocol="http"
)

if __name__ == "__main__":
    # Initialize Phoenix observability instrumentation
    setup_phoenix_instrumentation("asx-coordinator")

    logger.info(f"🚀 Starting Coordinator Agent (ROOT AGENT) A2A server on port {settings.coordinator_agent_port}")
    logger.info(f"   Agent: {coordinator_agent.name}")
    logger.info(f"   Sub-agents: {[agent.name for agent in (coordinator_agent.sub_agents or [])]}")
    uvicorn.run(app, host="0.0.0.0", port=settings.coordinator_agent_port)
