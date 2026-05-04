from fastapi import APIRouter, Depends, Query

from app.domains.disclosure.application.response.analysis_response import AnalysisResponse
from app.domains.disclosure.application.service.disclosure_analysis_service import (
    DisclosureAnalysisService,
)
from app.domains.disclosure.di import get_disclosure_analysis_service

router = APIRouter(prefix="/disclosure", tags=["Disclosure"])


@router.get("/analyze", response_model=AnalysisResponse)
async def analyze_disclosure(
    ticker: str = Query(..., description="종목코드 (예: 005930)"),
    analysis_type: str = Query(
        "full_analysis",
        description="분석 유형: flow_analysis | signal_analysis | full_analysis",
    ),
    service: DisclosureAnalysisService = Depends(get_disclosure_analysis_service),
) -> AnalysisResponse:
    """공시 분석 테스트 엔드포인트.

    ticker(종목코드)를 받아 해당 기업의 공시를 분석한 결과를 반환한다.
    """
    return await service.analyze(ticker=ticker, analysis_type=analysis_type)


@router.post("/process-documents")
async def process_documents():
    """핵심 공시 원문을 DART에서 다운로드하여 요약 + RAG 청크를 생성한다.

    스케줄러(매일 02:30)가 자동 실행하지만, 이 엔드포인트로 수동 트리거할 수 있다.
    """
    from app.infrastructure.scheduler.disclosure_jobs import job_process_documents
    await job_process_documents()
    return {"status": "ok", "message": "Document processing job triggered."}
