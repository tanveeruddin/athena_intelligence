"""
Phoenix Observability Integration for ASX ADK Gemini.

Provides centralized instrumentation setup for tracing LLM calls,
agent interactions, and A2A protocol communication across all agents.
"""

from typing import Optional
from utils.config import get_settings
from utils.logging import get_logger

logger = get_logger()
settings = get_settings()

# Global flag to track initialization state
_is_instrumented = False


def setup_phoenix_instrumentation(service_name: str) -> None:
    """
    Initialize Phoenix observability instrumentation for an agent.

    This function configures OpenTelemetry to send traces to Phoenix,
    and instruments the Google ADK SDK to automatically capture:
    - LLM calls (prompts, completions, tokens)
    - Agent tool executions
    - A2A protocol communication
    - Sub-agent delegations

    Args:
        service_name: The name of the agent service (e.g., "asx-coordinator",
                     "asx-scraper"). This will appear in Phoenix traces for
                     filtering and attribution.

    Example:
        >>> from utils.observability import setup_phoenix_instrumentation
        >>> setup_phoenix_instrumentation("asx-coordinator")
        >>> # Now all ADK operations in this process will be traced
    """
    global _is_instrumented

    # Skip if already instrumented or disabled
    if _is_instrumented:
        logger.debug(f"Phoenix instrumentation already initialized for {service_name}")
        return

    if not settings.phoenix_enabled:
        logger.info(f"Phoenix observability disabled for {service_name}")
        return

    try:
        # Import Phoenix/OTEL dependencies
        # from opentelemetry import trace
        # from opentelemetry.sdk.trace import TracerProvider
        # from opentelemetry.sdk.trace.export import BatchSpanProcessor
        # from opentelemetry.sdk.resources import Resource
        # from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from phoenix.otel import register
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor

        logger.info(f"🔍 Initializing Phoenix observability for {service_name}")
        logger.info(f"   📡 Collector endpoint: {settings.phoenix_collector_endpoint}")
        logger.info(f"   📁 Project name: {settings.phoenix_project_name}")

        # Register Phoenix OTEL components
        # Configure the Phoenix tracer
        trace_provider = register(
            project_name=settings.phoenix_project_name,
            auto_instrument=True # Auto-instrument your app based on installed OI dependencies
        )
        # Create resource with service identification
        # resource = Resource(attributes={
        #     "service.name": service_name,
        #     "project.name": settings.phoenix_project_name,
        #     "service.version": "0.2.0",  # Match your project version
        #     "deployment.environment": "development"  # Can be configured via .env
        # })

        # Configure otel trace provider
        
        # Configure trace provider
        #trace_provider = TracerProvider(resource=resource)
        #trace.set_tracer_provider(trace_provider)

        # Configure OTLP exporter to send traces to Phoenix
        # otlp_exporter = OTLPSpanExporter(
        #     endpoint=settings.phoenix_collector_endpoint,
        #     # Phoenix doesn't require authentication for local deployment
        #     # headers={"api_key": settings.phoenix_api_key} if settings.phoenix_api_key else {}
        # )

        # Add batch processor for efficient trace export
        # span_processor = BatchSpanProcessor(otlp_exporter)
        # trace_provider.add_span_processor(span_processor)

        # Instrument Google ADK
        # This will automatically trace:
        # - Agent invocations
        # - LLM generation calls
        # - Tool executions (FunctionTool, LongRunningFunctionTool)
        # - Sub-agent delegations
        GoogleADKInstrumentor().instrument(tracer_provider=trace_provider)

        _is_instrumented = True
        logger.info(f"✅ Phoenix instrumentation initialized successfully for {service_name}")

    except ImportError as e:
        logger.warning(
            f"⚠️  Phoenix dependencies not found. "
            f"Run: pip install openinference-instrumentation-google-adk arize-phoenix-otel"
        )
        logger.debug(f"Import error details: {e}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize Phoenix instrumentation for {service_name}: {e}")
        logger.debug(f"Error details: {e}", exc_info=True)


def shutdown_instrumentation() -> None:
    """
    Gracefully shutdown instrumentation and flush remaining spans.

    Call this before process termination to ensure all traces are sent.
    """
    global _is_instrumented

    if not _is_instrumented:
        return

    try:
        from opentelemetry import trace

        logger.info("Shutting down Phoenix instrumentation...")

        # Get trace provider and shut down
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            tracer_provider.shutdown()

        logger.info("✅ Phoenix instrumentation shutdown complete")
        _is_instrumented = False

    except Exception as e:
        logger.error(f"Error during instrumentation shutdown: {e}")
