from app.common.response.base_agent_response import BaseAgentResponse


class InvestmentDecisionResponse(BaseAgentResponse):
    query: str
    final_response: str
    disclaimer: str
    iteration_count: int
