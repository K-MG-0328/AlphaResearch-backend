from app.domains.agent.application.port.endpoint_collector import EndpointCollector
from app.domains.agent.application.response.agent_schema_response import (
    AgentSchemaResponse,
    AgentToolResponse,
)


class GenerateAgentSchemaUseCase:
    SCHEMA_VERSION = "1.0.0"

    def __init__(self, collector: EndpointCollector, api_base_url: str):
        self.collector = collector
        self.api_base_url = api_base_url

    def execute(self) -> AgentSchemaResponse:
        endpoints = self.collector.collect()
        tools = [
            AgentToolResponse(**endpoint.to_agent_tool())
            for endpoint in endpoints
        ]
        return AgentSchemaResponse(
            schema_version=self.SCHEMA_VERSION,
            api_base_url=self.api_base_url,
            total_endpoints=len(tools),
            tools=tools,
        )
