from datetime import date, timedelta

from fastapi import APIRouter, Depends, Path, Query

from app.common.exception.app_exception import AppException
from app.common.response.base_response import BaseResponse
from app.domains.smart_money.adapter.outbound.persistence.investor_flow_repository_impl import (
    InvestorFlowRepositoryImpl,
)
from app.domains.smart_money.application.response.collect_global_portfolio_response import (
    CollectGlobalPortfolioResponse,
)
from app.domains.smart_money.application.response.collect_investor_flow_response import (
    CollectInvestorFlowResponse,
)
from app.domains.smart_money.application.response.concentrated_buying_response import (
    ConcentratedBuyingResponse,
)
from app.domains.smart_money.application.response.global_portfolio_response import (
    GlobalPortfolioResponse,
    InvestorListResponse,
)
from app.domains.smart_money.application.response.investor_flow_ranking_response import (
    InvestorFlowRankingResponse,
)
from app.domains.smart_money.application.response.investor_flow_trend_response import (
    InvestorFlowTrendResponse,
)
from app.domains.smart_money.application.response.kr_portfolio_response import (
    CollectKrPortfolioResponse,
    KrInvestorListResponse,
    KrPortfolioResponse,
)
from app.domains.smart_money.application.response.us_concentrated_buying_response import (
    USConcentratedBuyingResponse,
)
from app.domains.smart_money.application.usecase.collect_global_portfolio_usecase import (
    CollectGlobalPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.collect_investor_flow_usecase import (
    CollectInvestorFlowUseCase,
)
from app.domains.smart_money.application.usecase.collect_kr_portfolio_usecase import (
    CollectKrPortfolioUseCase,
    KR_INVESTOR_MAP,
)
from app.domains.smart_money.application.usecase.get_concentrated_buying_usecase import (
    GetConcentratedBuyingUseCase,
)
from app.domains.smart_money.application.usecase.get_global_portfolio_usecase import (
    GetGlobalPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_investor_flow_ranking_usecase import (
    GetInvestorFlowRankingUseCase,
)
from app.domains.smart_money.application.usecase.get_investor_flow_trend_usecase import (
    GetInvestorFlowTrendUseCase,
)
from app.domains.smart_money.application.usecase.get_kr_portfolio_usecase import (
    GetKrPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_us_concentrated_buying_usecase import (
    GetUSConcentratedBuyingUseCase,
)
from app.domains.smart_money.di import (
    get_collect_global_portfolio_usecase,
    get_collect_investor_flow_usecase,
    get_collect_kr_portfolio_usecase,
    get_concentrated_buying_usecase,
    get_global_portfolio_usecase,
    get_investor_flow_ranking_usecase,
    get_investor_flow_repository,
    get_investor_flow_trend_usecase,
    get_kr_portfolio_usecase,
    get_us_concentrated_buying_usecase,
)
from app.domains.smart_money.domain.entity.global_portfolio import ChangeType
from app.domains.smart_money.domain.entity.investor_flow import InvestorType

router = APIRouter(prefix="/smart-money", tags=["Smart Money"])


@router.post(
    "/collect", response_model=BaseResponse[CollectInvestorFlowResponse], status_code=201
)
async def collect_investor_flow(
    target_date: date | None = Query(default=None, description="수집 날짜 (YYYY-MM-DD, 생략 시 전일)"),
    usecase: CollectInvestorFlowUseCase = Depends(get_collect_investor_flow_usecase),
):
    """KRX에서 외국인·기관·개인 투자자 유형별 순매수 데이터를 수집하여 저장한다."""
    result = await usecase.execute(target_date=target_date)
    return BaseResponse.ok(data=result)


@router.post(
    "/global-portfolio/collect",
    response_model=BaseResponse[CollectGlobalPortfolioResponse],
    status_code=201,
)
async def collect_global_portfolio(
    usecase: CollectGlobalPortfolioUseCase = Depends(get_collect_global_portfolio_usecase),
):
    """SEC EDGAR 13F 공시에서 글로벌 저명 투자자 포트폴리오를 수집하여 저장한다."""
    result = await usecase.execute()
    return BaseResponse.ok(data=result)


@router.get("/investor-flow", response_model=BaseResponse[InvestorFlowRankingResponse])
async def get_investor_flow_ranking(
    investor_type: InvestorType = Query(..., description="투자자 유형 (FOREIGN | INSTITUTION | INDIVIDUAL)"),
    date: date | None = Query(default=None, description="조회 날짜 (YYYY-MM-DD, 생략 시 최근 영업일)"),
    limit: int = Query(default=20, ge=1, le=100, description="반환 종목 수 (기본: 20)"),
    usecase: GetInvestorFlowRankingUseCase = Depends(get_investor_flow_ranking_usecase),
):
    """투자자 유형별 순매수 금액 내림차순 종목 랭킹을 반환한다."""
    result = await usecase.execute(investor_type=investor_type, target_date=date, limit=limit)
    return BaseResponse.ok(data=result)


@router.get("/investors", response_model=BaseResponse[InvestorListResponse])
async def get_investor_list():
    """수집 대상 글로벌 저명 투자자 목록을 반환한다 (DB 수집 여부 무관)."""
    from app.domains.smart_money.application.usecase.collect_global_portfolio_usecase import (
        INVESTOR_CIK_MAP,
    )

    return BaseResponse.ok(data=InvestorListResponse(investors=list(INVESTOR_CIK_MAP.keys())))


@router.get("/global-portfolio", response_model=BaseResponse[GlobalPortfolioResponse])
async def get_global_portfolio(
    investor_name: str | None = Query(default=None, description="투자자 이름 필터 (생략 시 전체)"),
    change_type: ChangeType | None = Query(default=None, description="변동 유형 필터 (NEW | INCREASED | DECREASED | CLOSED)"),
    usecase: GetGlobalPortfolioUseCase = Depends(get_global_portfolio_usecase),
):
    """글로벌 저명 투자자 최신 분기 포트폴리오를 반환한다."""
    result = await usecase.execute(investor_name=investor_name, change_type=change_type)
    return BaseResponse.ok(data=result)


@router.get("/concentrated", response_model=BaseResponse[ConcentratedBuyingResponse])
async def get_concentrated_buying(
    days: int = Query(default=5, ge=1, le=30, description="최근 N 영업일 누적 집계 (기본: 5)"),
    limit: int = Query(default=50, ge=1, le=200, description="반환 종목 수 (기본: 50)"),
    usecase: GetConcentratedBuyingUseCase = Depends(get_concentrated_buying_usecase),
):
    """외국인·기관 동시 순매수 상위 집중 매수 종목을 반환한다."""
    result = await usecase.execute(days=days, limit=limit)
    return BaseResponse.ok(data=result)


@router.post(
    "/kr-portfolio/collect",
    response_model=BaseResponse[CollectKrPortfolioResponse],
    status_code=201,
)
async def collect_kr_portfolio(
    usecase: CollectKrPortfolioUseCase = Depends(get_collect_kr_portfolio_usecase),
):
    """DART OpenAPI에서 국내 유명 투자자(국민연금·자산운용사·개인) 5% 이상 보유 종목을 수집한다."""
    result = await usecase.execute()
    total = result.get("total_saved", 0)
    error = result.get("error")
    if error:
        raise AppException(status_code=500, message=f"수집 중 오류 발생: {error}")
    return BaseResponse.ok(
        data=CollectKrPortfolioResponse(
            total_saved=total,
            message=f"국내 포트폴리오 수집 완료: {total}건",
        )
    )


@router.get("/kr-investors", response_model=BaseResponse[KrInvestorListResponse])
async def get_kr_investor_list():
    """수집 대상 국내 유명 투자자 목록을 반환한다."""
    investors = [
        {"name": name, "type": investor_type} for name, investor_type in KR_INVESTOR_MAP.items()
    ]
    return BaseResponse.ok(data=KrInvestorListResponse(investors=investors))


@router.get("/kr-portfolio", response_model=BaseResponse[KrPortfolioResponse])
async def get_kr_portfolio(
    investor_name: str | None = Query(default=None, description="투자자 이름 (생략 시 전체 건수만 반환)"),
    usecase: GetKrPortfolioUseCase = Depends(get_kr_portfolio_usecase),
):
    """국내 유명 투자자의 5% 이상 보유 종목 포트폴리오를 반환한다. investor_name 생략 시 total 건수만 반환."""
    if investor_name:
        result = await usecase.execute(investor_name=investor_name)
    else:
        total = await usecase.get_total_count()
        result = KrPortfolioResponse(investor_name=None, items=[], total=total)
    return BaseResponse.ok(data=result)


@router.get("/us-concentrated", response_model=BaseResponse[USConcentratedBuyingResponse])
async def get_us_concentrated_buying(
    limit: int = Query(default=20, ge=1, le=100, description="반환 종목 수 (기본: 20)"),
    usecase: GetUSConcentratedBuyingUseCase = Depends(get_us_concentrated_buying_usecase),
):
    """19명 글로벌 유명 투자자가 최신 분기에 동시 매수(신규편입·비중확대)한 미국 주식 집중 매수 랭킹을 반환한다."""
    result = await usecase.execute(limit=limit)
    return BaseResponse.ok(data=result)


@router.get("/trend/{stock_code}", response_model=BaseResponse[InvestorFlowTrendResponse])
async def get_investor_flow_trend(
    stock_code: str = Path(..., description="종목 코드 (예: 005930)"),
    days: int = Query(default=30, ge=1, le=365, description="최근 N일 추이 (기본: 30)"),
    repository: InvestorFlowRepositoryImpl = Depends(get_investor_flow_repository),
    usecase: GetInvestorFlowTrendUseCase = Depends(get_investor_flow_trend_usecase),
):
    """종목별 외국인·기관·개인 일별 순매수 추이를 반환한다. (Redis TTL 10분)"""
    latest_date = await repository.find_latest_date(InvestorType.FOREIGN.value)
    if latest_date is None:
        raise AppException(status_code=404, message="수집된 투자자 순매수 데이터가 없습니다.")
    since_date = latest_date - timedelta(days=days - 1)
    result = await usecase.execute(stock_code=stock_code, since_date=since_date, days=days)
    return BaseResponse.ok(data=result)
