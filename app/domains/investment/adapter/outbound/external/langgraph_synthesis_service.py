"""LangGraph Investment workflow 의 Synthesis 단계 LLM 호출 service.

`_synthesize_from_decision` (경로 A: investment_decision 기반) +
`_synthesize_fallback` (경로 B: analysis_insights 기반) 두 메서드를 추출.
둘 다 self._llm 만 의존하므로 thin service 로 분리 가능.

UseCase 본체는 thin wrapper 로 호출 → 외부 호출자(테스트 포함) 영향 0.
"""

from langchain_openai import ChatOpenAI

from app.domains.investment.adapter.outbound.external.langgraph_investment_helpers import (
    confidence_label,
)


class LangGraphSynthesisService:
    """Synthesis 단계 LLM 응답 생성. self._llm 만 의존."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm

    async def synthesize_from_decision(
        self,
        *,
        query: str,
        company: str,
        intent: str,
        investment_decision: dict,
    ) -> str:
        """investment_decision 의 verdict·reasons·risk_factors 만을 사용하여 자연어 응답 생성.

        LLM 이 새로운 근거를 만들지 못하도록 엄격히 지시한다.
        """
        verdict     = investment_decision["verdict"]
        confidence  = investment_decision["confidence"]
        direction   = investment_decision.get("direction", "neutral")
        rationale   = investment_decision.get("rationale", "")
        reasons     = investment_decision.get("reasons", {})
        risk_factors = investment_decision.get("risk_factors", [])

        verdict_ko  = {"buy": "매수", "hold": "보유", "sell": "매도"}[verdict]
        conf_label  = confidence_label(confidence)
        is_conservative = verdict == "hold" and confidence <= 0.3

        print(
            f"[SynthesisAgent] 경로 A (decision 기반) "
            f"| verdict={verdict}({verdict_ko}) | confidence={confidence:.3f}({conf_label})"
            + (" | 보수적판단" if is_conservative else "")
        )

        # 근거 텍스트 구성
        pos_reasons = reasons.get("positive", [])
        neg_reasons = reasons.get("negative", [])
        pos_text = "\n".join(f"  - {r}" for r in pos_reasons) if pos_reasons else "  - 없음"
        neg_text = "\n".join(f"  - {r}" for r in neg_reasons) if neg_reasons else "  - 없음"
        risk_text = "\n".join(f"  - {r}" for r in risk_factors) if risk_factors else "  - 없음"

        conservative_note = (
            "\n[주의] 이 판단은 수집된 데이터가 충분하지 않아 신호 부족으로 인한 "
            "보수적 기본값입니다. 추가 정보 확인을 권장합니다."
            if is_conservative else ""
        )

        system_prompt = """당신은 한국 주식 투자 어드바이저입니다.
아래에 제공된 투자 판단 결과와 근거를 사용자 친화적 한국어 서술로 변환하세요.

절대 규칙:
1. verdict(매수/보유/매도) 표현을 완곡하게 바꾸거나 의미를 흐리면 안 됩니다.
2. 제공된 reasons와 risk_factors 이외의 새로운 근거나 수치를 생성하지 마세요.
3. 응답 구조: [결론 한 줄] → [긍정 근거 요약] → [부정·리스크 요약] (총 2~4문단)
4. 마크다운 헤더(#) 없이 일반 텍스트로만 작성하세요."""

        user_prompt = f"""사용자 질문: {query}
분석 대상: {company}
질문 의도: {intent}
{conservative_note}

[확정된 투자 판단 — 변경 불가]
  의견(verdict)  : {verdict_ko} ({verdict})
  방향성         : {direction}
  확신도         : {confidence:.1%} ({conf_label})
  판단 근거 요약 : {rationale}

[긍정 근거 — 이 내용만 사용하세요]
{pos_text}

[부정 근거 — 이 내용만 사용하세요]
{neg_text}

[리스크 요인 — 이 내용만 사용하세요]
{risk_text}

위 정보를 바탕으로 verdict를 가장 먼저 명확하게 전달하고,
근거와 리스크를 자연스럽게 서술하는 2~4문단 한국어 응답을 작성하세요.
새로운 사실이나 수치를 추가하지 마세요."""

        print("[SynthesisAgent] LLM 호출 중 (경로 A)...")
        response = await self._llm.ainvoke([
            ("system", system_prompt),
            ("human", user_prompt),
        ])
        text = response.content.strip()
        print(f"[SynthesisAgent] LLM 응답 수신 | 길이={len(text)}자")
        return text

    async def synthesize_fallback(
        self,
        *,
        query: str,
        company: str,
        intent: str,
        analysis_insights: dict,
    ) -> str:
        """investment_decision 누락 시 analysis_insights 기반 fallback 응답."""
        investment_points = analysis_insights.get("investment_points", [])
        points_text = (
            "\n".join(f"  - {p}" for p in investment_points) if investment_points else "  - 없음"
        )

        system_prompt = """당신은 한국 주식 투자 어드바이저입니다.
아래 분석 결과를 바탕으로 사용자 질문에 대한 참고용 응답을 작성하세요.
투자 판단 데이터가 부족하여 정량 의견 대신 정성 분석만 제공됩니다.
마크다운 헤더(#) 없이 일반 텍스트로 작성하세요."""

        user_prompt = f"""[참고용 분석 결과 — 투자 판단 데이터 부족]
사용자 질문: {query}
분석 대상: {company}
질문 의도: {intent}

전망: {analysis_insights.get('outlook', '정보 없음')}
리스크: {analysis_insights.get('risk', '정보 없음')}
투자 포인트:
{points_text}

이 결과는 정량 신호 부족으로 참고용 분석에 해당합니다.
이를 명시하고 2~3문단으로 사용자 친화적 응답을 작성하세요."""

        print("[SynthesisAgent] LLM 호출 중 (경로 B fallback)...")
        response = await self._llm.ainvoke([
            ("system", system_prompt),
            ("human", user_prompt),
        ])
        text = response.content.strip()
        print(f"[SynthesisAgent] LLM fallback 응답 수신 | 길이={len(text)}자")
        return text
