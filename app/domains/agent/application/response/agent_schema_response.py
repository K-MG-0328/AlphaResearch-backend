from typing import Any, Optional

from pydantic import BaseModel


class AgentToolResponse(BaseModel):
    name: str
    description: str
    method: str
    path: str
    parameters: Optional[dict[str, Any]] = None
    response_schema: Optional[dict[str, Any]] = None


class AgentSchemaResponse(BaseModel):
    schema_version: str
    api_base_url: str
    total_endpoints: int
    tools: list[AgentToolResponse]
