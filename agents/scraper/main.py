"""
Scraper Agent A2A Server - Starts the scraper agent as an A2A service.
"""
import os
import uvicorn
from utils.config import get_settings
from utils.logging import get_logger
from utils.observability import setup_phoenix_instrumentation
from .agent import app

logger = get_logger()
settings = get_settings()

# Ensure GEMINI_API_KEY is set from settings if available
if settings.gemini_api_key and not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

if __name__ == "__main__":
    # Initialize Phoenix observability instrumentation
    setup_phoenix_instrumentation("asx-scraper")

    logger.info(f"🚀 Starting Scraper Agent A2A server on port {settings.scraper_agent_port}")
    uvicorn.run(app, host="0.0.0.0", port=settings.scraper_agent_port)
