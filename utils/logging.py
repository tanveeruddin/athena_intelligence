"""
Structured logging setup using loguru.
Provides JSON and text logging with MELT (Metrics, Events, Logs, Traces) support.
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger
from datetime import datetime

from utils.config import get_settings


class LogFormatter:
    """Custom log formatter for JSON output."""

    def __init__(self, format_type: str = "json"):
        self.format_type = format_type

    def format_json(self, record: Dict[str, Any]) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
        }

        # Add extra fields from record
        if "extra" in record:
            log_entry.update(record["extra"])

        # Add exception info if present
        if record["exception"]:
            log_entry["exception"] = {
                "type": record["exception"].type.__name__,
                "value": str(record["exception"].value),
            }

        return json.dumps(log_entry) + "\n"

    def format_text(self, record: Dict[str, Any]) -> str:
        """Format log record as human-readable text."""
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>\n"
        )


def setup_logging() -> None:
    """
    Configure loguru logger with file and console handlers.
    Supports both JSON and text formats based on configuration.
    """
    settings = get_settings()

    # Remove default logger
    logger.remove()

    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    # Console handler (always text format for readability)
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=settings.log_level,
        colorize=True,
    )

    # File handler for all logs (JSON format)
    logger.add(
        "logs/asx_scraper_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {module}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="00:00",  # Rotate at midnight
        retention="30 days",
        compression="zip",
    )

    # JSON log file for structured logging (for observability)
    if settings.log_format.lower() == "json":
        def json_formatter(record):
            """Format record as JSON."""
            return json.dumps({
                "timestamp": record["time"].isoformat(),
                "level": record["level"].name,
                "message": record["message"],
                "module": record["module"],
                "function": record["function"],
                "line": record["line"],
                "extra": record.get("extra", {}),
            }) + "\n"

        logger.add(
            "logs/asx_scraper_json_{time:YYYY-MM-DD}.json",
            format="{message}",  # Use simple format, we'll handle JSON in serialize
            serialize=True,
            level="DEBUG",
            rotation="00:00",
            retention="30 days",
            compression="zip",
        )

    # Error log file
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {module}:{function}:{line} - {message}",
        level="ERROR",
        rotation="00:00",
        retention="90 days",
        compression="zip",
    )

    logger.info("Logging system initialized", log_level=settings.log_level, log_format=settings.log_format)


def log_event(event_type: str, event_data: Dict[str, Any], agent_id: Optional[str] = None) -> None:
    """
    Log a discrete event (for MELT observability).

    Args:
        event_type: Type of event (e.g., 'scrape_started', 'pdf_downloaded')
        event_data: Event data dictionary
        agent_id: Optional agent identifier
    """
    log_data = {
        "event_type": event_type,
        "event_data": event_data,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if agent_id:
        log_data["agent_id"] = agent_id

    logger.info(f"EVENT: {event_type}", **log_data)


def log_metric(metric_name: str, metric_value: float, metric_unit: str = "", tags: Optional[Dict[str, str]] = None) -> None:
    """
    Log a metric (for MELT observability).

    Args:
        metric_name: Name of the metric (e.g., 'processing_time_ms')
        metric_value: Metric value
        metric_unit: Unit of measurement (e.g., 'ms', 'bytes')
        tags: Optional tags for categorization
    """
    log_data = {
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_unit": metric_unit,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if tags:
        log_data["tags"] = tags

    logger.debug(f"METRIC: {metric_name}={metric_value}{metric_unit}", **log_data)


def log_trace(trace_id: str, span_name: str, duration_ms: float, status: str = "success", **kwargs) -> None:
    """
    Log a trace span (for MELT observability).

    Args:
        trace_id: Unique trace identifier
        span_name: Name of the span (e.g., 'analyze_announcement')
        duration_ms: Duration in milliseconds
        status: Status of the span ('success', 'error', 'timeout')
        **kwargs: Additional trace data
    """
    log_data = {
        "trace_id": trace_id,
        "span_name": span_name,
        "duration_ms": duration_ms,
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        **kwargs,
    }

    logger.debug(f"TRACE: {span_name} [{trace_id}] - {duration_ms}ms ({status})", **log_data)


def get_logger():
    """Get the configured logger instance."""
    return logger


# Initialize logging on module import
setup_logging()
