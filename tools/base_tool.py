"""
Base MCP (Model Context Protocol) tool interface.
All tools implement this interface for standardized agent interaction.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import time

from utils.logging import get_logger, log_metric

logger = get_logger()


class ToolMetadata(BaseModel):
    """Metadata for a tool."""
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    version: str = Field(default="1.0.0", description="Tool version")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters schema")
    returns: Dict[str, Any] = Field(default_factory=dict, description="Return value schema")


class ToolResult(BaseModel):
    """Result from tool execution."""
    success: bool = Field(..., description="Whether the tool executed successfully")
    data: Optional[Any] = Field(None, description="Result data")
    error: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    execution_time_ms: Optional[int] = Field(None, description="Execution time in milliseconds")


class BaseTool(ABC):
    """
    Base class for all MCP-compliant tools.

    All tools must implement:
    - get_metadata(): Return tool metadata
    - _execute(): Core tool logic
    """

    def __init__(self):
        """Initialize the tool."""
        self.metadata = self.get_metadata()
        logger.info(f"Initialized tool: {self.metadata.name} v{self.metadata.version}")

    @abstractmethod
    def get_metadata(self) -> ToolMetadata:
        """
        Get tool metadata.

        Returns:
            ToolMetadata with name, description, parameters, etc.
        """
        pass

    @abstractmethod
    async def _execute(self, **kwargs) -> Any:
        """
        Core tool execution logic (must be implemented by subclasses).

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool-specific result data
        """
        pass

    async def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with error handling and metrics.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with success status, data, and metadata
        """
        start_time = time.time()

        try:
            logger.info(f"Executing tool: {self.metadata.name}", tool_params=kwargs)

            # Validate parameters (basic check)
            self._validate_parameters(kwargs)

            # Execute core logic
            result_data = await self._execute(**kwargs)

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Log metrics
            log_metric(
                metric_name=f"tool_{self.metadata.name}_execution_time",
                metric_value=execution_time_ms,
                metric_unit="ms"
            )

            logger.info(
                f"Tool executed successfully: {self.metadata.name}",
                execution_time_ms=execution_time_ms
            )

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "tool_name": self.metadata.name,
                    "tool_version": self.metadata.version,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"{type(e).__name__}: {str(e)}"

            logger.error(
                f"Tool execution failed: {self.metadata.name}",
                error=error_msg,
                execution_time_ms=execution_time_ms
            )

            return ToolResult(
                success=False,
                error=error_msg,
                metadata={
                    "tool_name": self.metadata.name,
                    "tool_version": self.metadata.version,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                execution_time_ms=execution_time_ms,
            )

    def _validate_parameters(self, params: Dict[str, Any]) -> None:
        """
        Validate tool parameters (basic validation).

        Args:
            params: Parameters to validate

        Raises:
            ValueError: If required parameters are missing
        """
        required_params = self.metadata.parameters.get("required", [])

        for param in required_params:
            if param not in params:
                raise ValueError(f"Missing required parameter: {param}")

    def get_description(self) -> str:
        """Get a human-readable description of the tool."""
        return f"{self.metadata.name} (v{self.metadata.version}): {self.metadata.description}"


class ToolRegistry:
    """
    Registry for all available tools.
    Allows agents to discover and use tools dynamically.
    """

    def __init__(self):
        """Initialize the tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        logger.info("Tool registry initialized")

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        tool_name = tool.metadata.name
        self._tools[tool_name] = tool
        logger.info(f"Registered tool: {tool_name}")

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(tool_name)

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_all_metadata(self) -> List[ToolMetadata]:
        """
        Get metadata for all registered tools.

        Returns:
            List of ToolMetadata objects
        """
        return [tool.metadata for tool in self._tools.values()]


# Global tool registry
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry (singleton)."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry
