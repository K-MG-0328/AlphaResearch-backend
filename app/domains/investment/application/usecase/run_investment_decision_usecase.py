from app.domains.investment.application.port.investment_workflow_port import InvestmentWorkflowPort
from app.domains.investment.application.request.investment_decision_request import InvestmentDecisionRequest
from app.domains.investment.application.response.investment_decision_response import InvestmentDecisionResponse

DISCLAIMER = (
    "본 응답은 투자 권유가 아닌 정보 제공 목적으로만 활용되어야 하며, "
    "투자 판단 및 그에 따른 결과는 전적으로 투자자 본인의 책임입니다."
)


class RunInvestmentDecisionUseCase:
    def __init__(self, workflow: InvestmentWorkflowPort) -> None:
        self._workflow = workflow

    async def execute(self, user_id: str, request: InvestmentDecisionRequest) -> InvestmentDecisionResponse:
        print(f"[UseCase] 투자 판단 워크플로우 시작 | user_id={user_id} | query={request.query!r}")

        final_state = await self._workflow.run(user_id=user_id, query=request.query)

        print(f"[UseCase] 워크플로우 완료 | iteration_count={final_state.get('iteration_count', 0)}")

        return InvestmentDecisionResponse(
            query=request.query,
            final_response=final_state.get("final_response", ""),
            disclaimer=DISCLAIMER,
            iteration_count=final_state.get("iteration_count", 0),
        )
