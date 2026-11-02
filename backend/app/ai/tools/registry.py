from typing import Dict, Any, Type, List
from app.ai.tools.base import BaseTool

class ToolRegistry:
    """
    Central registry for all available tools.
    """
    _tools: Dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get_tool(cls, name: str) -> BaseTool:
        if name not in cls._tools:
            raise ValueError(f"Tool {name} not found in registry.")
        return cls._tools[name]

    @classmethod
    def get_all_schemas(cls) -> List[Dict[str, Any]]:
        return [tool.get_schema() for tool in cls._tools.values()]

    @classmethod
    def list_tool_names(cls) -> List[str]:
        return list(cls._tools.keys())

    @classmethod
    def has_tool(cls, name: str) -> bool:
        return name in cls._tools


# ═══════════════════════════════════════════════════════════
# Register Production Tools  (M12.3)
# ═══════════════════════════════════════════════════════════
from app.ai.tools.implemented import (
    GetOrderStatusTool,
    GetTicketStatusTool,
    GetCustomerAccountInfoTool,
    CreateSupportTicketTool,
    UpdateTicketInfoTool,
    RequestHumanSupportTool,
    CheckTransactionTool,
)

ToolRegistry.register(GetOrderStatusTool())
ToolRegistry.register(GetTicketStatusTool())
ToolRegistry.register(GetCustomerAccountInfoTool())
ToolRegistry.register(CreateSupportTicketTool())
ToolRegistry.register(UpdateTicketInfoTool())
ToolRegistry.register(RequestHumanSupportTool())
ToolRegistry.register(CheckTransactionTool())
