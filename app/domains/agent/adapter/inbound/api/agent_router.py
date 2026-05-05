
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.auth.dependencies import require_user_or_temp_session
from app.common.response.base_response import BaseResponse
from app.domains.agent.adapter.outbound.cache.redis_finance_analysis_cache import (
    RedisFinanceAnalysisCache,
)
from app.domains.agent.adapter.outbound.external.disclosure_sub_agent_adapter import (
    DisclosureSubAgentAdapter,
)
from app.domains.agent.adapter.outbound.external.finance_sub_agent_adapter import (
    FinanceSubAgentAdapter,
)
from app.domains.agent.adapter.outbound.external.langgraph_finance_agent_provider import (
    LangGraphFinanceAgentProvider,
)
from app.domains.agent.adapter.outbound.external.news_sub_agent_adapter import (
    NewsSubAgentAdapter,
)
from app.domains.agent.adapter.outbound.external.sentiment_sub_agent_adapter import (
    SentimentSubAgentAdapter,
)
from app.domains.agent.adapter.outbound.external.openai_synthesis_client import (
    OpenAISynthesisClient,
)
from app.domains.agent.adapter.outbound.persistence.integrated_analysis_repository_impl import (
    IntegratedAnalysisRepositoryImpl,
)
from app.domains.agent.application.request.agent_query_request import AgentQueryRequest
from app.domains.agent.application.request.finance_analysis_request import (
    FinanceAnalysisRequest,
)
from app.domains.agent.application.response.frontend_agent_response import (
    FrontendAgentResponse,
)
from app.domains.agent.application.response.integrated_analysis_response import (
    IntegratedAnalysisResponse,
)
from app.domains.agent.application.usecase.analyze_finance_agent_usecase import (
    AnalyzeFinanceAgentUseCase,
)
from app.domains.agent.application.usecase.run_agent_query_usecase import (
    RunAgentQueryUseCase,
)
from app.domains.company_profile.adapter.outbound.cache.business_overview_cache import (
    RedisBusinessOverviewCache,
)
from app.domains.company_profile.adapter.outbound.cache.company_profile_cache import (
    RedisCompanyProfileCache,
)
from app.domains.company_profile.adapter.outbound.external.dart_company_info_client import (
    DartCompanyInfoClient,
)
from app.domains.company_profile.adapter.outbound.external.openai_business_overview_client import (
    OpenAIBusinessOverviewClient,
)
from app.domains.company_profile.adapter.outbound.external.sec_company_name_adapter import (
    SecCompanyNameAdapter,
)
from app.domains.company_profile.application.usecase.get_company_profile_usecase import (
    GetCompanyProfileUseCase,
)
from app.domains.dashboard.adapter.outbound.external.cached_asset_type_adapter import (
    CachedAssetTypeAdapter,
)
from app.domains.dashboard.adapter.outbound.external.yahoo_finance_asset_type_client import (
    YahooFinanceAssetTypeClient,
)
from app.domains.disclosure.adapter.outbound.external.sec_edgar_api_client import (
    SecEdgarApiClient,
)
from app.domains.disclosure.adapter.outbound.persistence.company_repository_impl import (
    CompanyRepositoryImpl,
)
from app.domains.disclosure.adapter.outbound.persistence.rag_chunk_repository_impl import (
    RagChunkRepositoryImpl,
)
from app.domains.stock.adapter.outbound.persistence.stock_repository_impl import (
    StockRepositoryImpl,
)
from app.domains.stock.adapter.outbound.persistence.stock_vector_repository_impl import (
    StockVectorRepositoryImpl,
)
from app.domains.stock.application.usecase.get_stored_stock_data_usecase import (
    GetStoredStockDataUseCase,
)
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.database import get_db

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post(
    "/query",
    response_model=BaseResponse[FrontendAgentResponse],
    status_code=200,
)
async def query_agent(
    body: AgentQueryRequest,
    _: None = Depends(require_user_or_temp_session),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    settings = get_settings()
    repository = IntegratedAnalysisRepositoryImpl(db)
    llm_synthesis = OpenAISynthesisClient(api_key=settings.openai_api_key)

    sec_client = SecEdgarApiClient(user_agent=settings.sec_edgar_user_agent)
    company_profile_usecase = GetCompanyProfileUseCase(
        company_repository=CompanyRepositoryImpl(db),
        dart_company_info=DartCompanyInfoClient(),
        cache=RedisCompanyProfileCache(redis),
        rag_chunk_repository=RagChunkRepositoryImpl(db),
        business_overview=OpenAIBusinessOverviewClient(),
        overview_cache=RedisBusinessOverviewCache(redis),
        us_company_name=SecCompanyNameAdapter(sec_client),
        asset_type_port=CachedAssetTypeAdapter(YahooFinanceAssetTypeClient(), redis),
    )

    usecase = RunAgentQueryUseCase(
        news_agent=NewsSubAgentAdapter(db=db, api_key=settings.openai_api_key),
        disclosure_agent=DisclosureSubAgentAdapter(),
        finance_agent=FinanceSubAgentAdapter(),
        sentiment_agent=SentimentSubAgentAdapter(db=db, api_key=settings.openai_api_key),  # SNS 감정분석 서브에이전트
        llm_synthesis=llm_synthesis,
        repository=repository,
        company_profile_usecase=company_profile_usecase,
    )
    internal_result = await usecase.execute(body)
    frontend_result = FrontendAgentResponse.from_internal(internal_result)
    return BaseResponse.ok(data=frontend_result)


@router.get(
    "/history",
    response_model=BaseResponse[list[IntegratedAnalysisResponse]],
    status_code=200,
)
async def get_analysis_history(
    ticker: str = Query(..., description="종목 코드 (예: 005930)"),
    limit: int = Query(default=10, ge=1, le=50),
    _: None = Depends(require_user_or_temp_session),
    db: AsyncSession = Depends(get_db),
):
    """ticker 기준 최근 통합 분석 이력을 반환합니다."""
    repository = IntegratedAnalysisRepositoryImpl(db)
    history = await repository.find_history(ticker, limit=limit)
    return BaseResponse.ok(data=history)


@router.post(
    "/finance-analysis",
    response_model=BaseResponse[FrontendAgentResponse],
    status_code=200,
)
async def analyze_finance(
    request: FinanceAnalysisRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    벡터 DB에 저장된 데이터를 기반으로 재무 분석을 수행합니다.
    먼저 /stock/{ticker}/collect로 데이터를 적재해야 합니다.
    """
    settings = get_settings()
    stock_repository = StockRepositoryImpl()
    stock_vector_repository = StockVectorRepositoryImpl()

    get_stored_stock_data_usecase = GetStoredStockDataUseCase(
        stock_repository=stock_repository,
        stock_vector_repository=stock_vector_repository,
    )

    finance_provider = LangGraphFinanceAgentProvider(
        api_key=settings.openai_api_key,
        chat_model=settings.openai_finance_agent_model,
        embedding_model=settings.openai_embedding_model,
        top_k=settings.finance_rag_top_k,
        langsmith_tracing=settings.langsmith_tracing,
        langsmith_api_key=settings.langsmith_api_key,
        langsmith_project=settings.langsmith_project,
        langsmith_endpoint=settings.langsmith_endpoint,
    )

    usecase = AnalyzeFinanceAgentUseCase(
        stock_repository=stock_repository,
        get_stored_stock_data_usecase=get_stored_stock_data_usecase,
        finance_agent_provider=finance_provider,
        finance_analysis_cache=RedisFinanceAnalysisCache(
            redis=redis,
            ttl_seconds=settings.finance_analysis_cache_ttl_seconds,
        ),
    )
    internal_result = await usecase.execute(request)
    frontend_result = FrontendAgentResponse.from_internal(internal_result)
    return BaseResponse.ok(data=frontend_result)
