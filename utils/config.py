"""
Configuration management using Pydantic Settings.
Loads environment variables from .env file and provides typed configuration.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./data/asx_scraper.db",
        description="Database connection URL"
    )

    # Gemini API Configuration
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key"
    )
    gemini_model: str = Field(
        default="gemini-2.0-flash-exp",
        description="Gemini model to use"
    )
    gemini_temperature: float = Field(
        default=0.3,
        description="Temperature for LLM generation"
    )
    gemini_max_tokens: int = Field(
        default=2048,
        description="Maximum tokens for LLM generation"
    )

    # ASX Scraper Configuration
    company_announcements_url_template: str = Field(
        default="https://www.asx.com.au/markets/trade-our-cash-market/announcements.{asx_code}",
        description="ASX company-specific announcements URL template"
    )
    max_announcements_per_company: int = Field(
        default=1,
        description="Maximum number of announcements to fetch per company"
    )
    scrape_only_price_sensitive: bool = Field(
        default=True,
        description="Only scrape price-sensitive announcements"
    )

    # Storage Configuration
    pdf_storage_path: str = Field(
        default="./data/pdfs",
        description="Path to store downloaded PDFs"
    )
    markdown_storage_path: str = Field(
        default="./data/markdown",
        description="Path to store converted markdown files"
    )

    # Memory Configuration
    episodic_memory_limit: int = Field(
        default=10,
        description="Number of episodic memories to retrieve for timeline analysis"
    )
    semantic_memory_update_threshold: int = Field(
        default=3,
        description="Number of new announcements before updating semantic memory"
    )

    # A2A Protocol Configuration
    a2a_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for A2A communication"
    )
    a2a_timeout_seconds: int = Field(
        default=300,
        description="Timeout for A2A task completion"
    )

    # Evaluation Configuration
    enable_evaluation: bool = Field(
        default=True,
        description="Enable LLM-as-a-Judge evaluation"
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)"
    )

    # Agent Configuration
    coordinator_agent_port: int = Field(default=8000, description="Coordinator agent port")
    scraper_agent_port: int = Field(default=8001, description="Scraper agent port")
    analyzer_agent_port: int = Field(default=8002, description="Analyzer agent port")
    stock_agent_port: int = Field(default=8003, description="Stock agent port")
    memory_agent_port: int = Field(default=8004, description="Memory agent port")
    evaluation_agent_port: int = Field(default=8005, description="Evaluation agent port")
    trading_agent_port: int = Field(default=8006, description="Trading agent port")

    # Trading Configuration
    watchlist_companies: str = Field(
        default="BHP,CBA,WBC,CSL,RIO",
        description="Comma-separated list of ASX codes for trading watchlist"
    )
    trade_amount_usd: float = Field(
        default=1000.0,
        description="Fixed amount in USD for paper trades"
    )

    # Testing/Debug Configuration
    force_recommendation_for_testing: Optional[str] = Field(
        default="BUY",
        description="For testing: force evaluation to return this recommendation (BUY/SELL/HOLD/SPECULATIVE BUY/AVOID). Leave empty for normal operation."
    )

    # Observability - Phoenix Configuration
    phoenix_enabled: bool = Field(
        default=True,
        description="Enable Phoenix observability tracing"
    )
    phoenix_collector_endpoint: str = Field(
        default="http://localhost:6006/v1/traces",
        description="Phoenix OTEL collector endpoint for traces"
    )
    phoenix_project_name: str = Field(
        default="asx-adk-gemini",
        description="Phoenix project name for trace organization"
    )
    phoenix_api_key: Optional[str] = Field(
        default=None,
        description="Phoenix API key (only needed for Phoenix cloud)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        directories = [
            self.pdf_storage_path,
            self.markdown_storage_path,
            "data",
            "logs"
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def get_agent_url(self, agent_type: str) -> str:
        """Get the URL for a specific agent type."""
        port_map = {
            "coordinator": self.coordinator_agent_port,
            "scraper": self.scraper_agent_port,
            "analyzer": self.analyzer_agent_port,
            "stock": self.stock_agent_port,
            "memory": self.memory_agent_port,
            "evaluation": self.evaluation_agent_port,
            "trading": self.trading_agent_port,
        }

        port = port_map.get(agent_type.lower())
        if not port:
            raise ValueError(f"Unknown agent type: {agent_type}")

        return f"http://localhost:{port}"

    def get_watchlist(self) -> list[str]:
        """Get watchlist companies as a list of ASX codes."""
        return [code.strip().upper() for code in self.watchlist_companies.split(",") if code.strip()]


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment variables."""
    global _settings
    _settings = Settings()
    _settings.ensure_directories()
    return _settings


# Export settings instance
settings = get_settings()
