from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolSecurityPolicy(BaseModel):
    allowed_roles: List[str] = ["admin", "expert", "customer"]
    requires_confirmation: bool = False
    risk_level: str = "low"  # low | medium | high


class ToolParameter(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


class BaseTool:
    """
    Base class for all agentic tools in the system.

    Every tool receives a secure execution context:
      - db:              async database session
      - user:            the authenticated User ORM object
      - conversation_id: current conversation id
      - **kwargs:        tool-specific arguments from the AI
    """
    name: str = ""
    description: str = ""
    parameters: List[ToolParameter] = []
    security_policy: ToolSecurityPolicy = ToolSecurityPolicy()
    use_when: str = ""
    do_not_use_when: str = ""

    async def execute(self, *, db, user, conversation_id: int, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with the provided arguments.
        Must be implemented by subclasses.

        Args:
            db: AsyncSession — the database session for queries/writes.
            user: User — the authenticated user who triggered this tool.
            conversation_id: int — the conversation this tool is running in.
            **kwargs: tool-specific arguments validated against self.parameters.

        Returns:
            A structured dict with at minimum {"success": bool, "tool": str, ...}.
        """
        raise NotImplementedError("Tools must implement the execute method.")

    def get_schema(self) -> Dict[str, Any]:
        """Returns the JSON schema describing this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [p.model_dump() for p in self.parameters],
            "risk_level": self.security_policy.risk_level,
            "requires_confirmation": self.security_policy.requires_confirmation,
            "use_when": self.use_when,
            "do_not_use_when": self.do_not_use_when,
        }
