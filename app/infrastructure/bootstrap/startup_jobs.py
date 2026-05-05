"""lifespan 부트스트랩 작업 모음.

main.py 의 lifespan 안에 있던 try/except 8개 블록 + 부수 init 을 함수별로 분리.
``run_all_bootstraps()`` 가 동일한 순서로 일괄 실행한다. 로직 변경 0 (이동만).

부팅 순서 (의존성 순):
1. DB health check + Base.metadata.create_all (vector 포함)
2. seed stock themes
3. disclosure 부트스트랩 5개 (bootstrap, news, incremental_collect, refresh_company_list, process_documents)
4. nasdaq + stock_bars 부트스트랩
5. 매크로 스냅샷 (Redis 캐시 4h 이내 복원, 아니면 fresh refresh)
6. corp_earnings 부트스트랩
7. Kiwi 형태소 분석기 사전 로딩
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def _init_database() -> None:
    """PostgreSQL health + pgvector extension + Base.metadata.create_all (메인 + vector)."""
    from app.infrastructure.database.database import Base, check_db_health, engine
    from app.infrastructure.database.vector_database import VectorBase, vector_engine

    if not await check_db_health():
        raise RuntimeError("PostgreSQL 연결 실패 — 서버를 시작할 수 없습니다.")

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async with vector_engine.begin() as conn:
        await conn.run_sync(VectorBase.metadata.create_all)


async def _seed_stock_themes() -> None:
    from app.domains.stock_theme.adapter.outbound.persistence.stock_theme_repository_impl import (
        StockThemeRepositoryImpl,
    )
    from app.domains.stock_theme.application.usecase.seed_stock_themes_usecase import (
        SeedStockThemesUseCase,
    )
    from app.infrastructure.database.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        await SeedStockThemesUseCase(StockThemeRepositoryImpl(session)).execute()


async def _run_disclosure_bootstrap_jobs() -> None:
    """disclosure 도메인의 5개 catch-up 작업 — 각각 try/except 로 graceful 진행."""
    from app.infrastructure.scheduler.disclosure_jobs import (
        job_bootstrap,
        job_collect_news,
        job_incremental_collect,
        job_process_documents,
        job_refresh_company_list,
    )

    try:
        await job_bootstrap()
    except Exception as e:
        logger.error("Bootstrap failed (server continues normally): %s", str(e))

    try:
        await job_collect_news()
    except Exception as e:
        logger.error("News bootstrap failed (server continues normally): %s", str(e))

    try:
        await job_incremental_collect()
    except Exception as e:
        logger.error(
            "Incremental collect on startup failed (server continues normally): %s", str(e)
        )

    try:
        from app.domains.disclosure.adapter.outbound.persistence.collection_job_repository_impl import (
            CollectionJobRepositoryImpl,
        )
        from app.infrastructure.database.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            latest = await CollectionJobRepositoryImpl(session).find_latest_by_job_name(
                "refresh_company_list"
            )
            should_run = (
                latest is None
                or latest.status != "success"
                or latest.started_at is None
                or (datetime.now() - latest.started_at) > timedelta(hours=24)
            )
        if should_run:
            await job_refresh_company_list()
        else:
            logger.info("[Startup] refresh_company_list skipped (last success < 24h)")
    except Exception as e:
        logger.error(
            "Refresh company list on startup failed (server continues normally): %s", str(e)
        )

    try:
        from app.domains.disclosure.adapter.outbound.persistence.disclosure_repository_impl import (
            DisclosureRepositoryImpl,
        )
        from app.infrastructure.database.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            unprocessed = await DisclosureRepositoryImpl(session).find_unprocessed_core(limit=1)
        if unprocessed:
            await job_process_documents()
        else:
            logger.info("[Startup] process_documents skipped (no unprocessed core disclosures)")
    except Exception as e:
        logger.error(
            "Process documents on startup failed (server continues normally): %s", str(e)
        )


async def _run_market_data_bootstrap() -> None:
    """nasdaq + stock_bars 일별 봉 부트스트랩."""
    from app.infrastructure.scheduler.nasdaq_jobs import job_bootstrap_nasdaq
    from app.infrastructure.scheduler.stock_bars_jobs import job_bootstrap_stock_bars

    try:
        await job_bootstrap_nasdaq()
    except Exception as e:
        logger.error("Nasdaq bootstrap failed (server continues normally): %s", str(e))

    try:
        await job_bootstrap_stock_bars()
    except Exception as e:
        logger.error("Stock bars bootstrap failed (server continues normally): %s", str(e))


async def _run_macro_snapshot_bootstrap() -> None:
    """Redis 영속 캐시가 4h 이내면 복원, 아니면 신규 생성.
    YouTube/LLM quota 절약 — 코드 hot-reload 마다 매번 호출되는 것을 방지."""
    from app.infrastructure.bootstrap.macro_snapshot import try_restore_macro_snapshot
    from app.infrastructure.scheduler.macro_jobs import job_refresh_market_risk

    try:
        restored = await try_restore_macro_snapshot(max_age_hours=4)
        if restored:
            logger.info("[Startup] Macro snapshot restored from Redis (skip bootstrap)")
        else:
            await job_refresh_market_risk()
    except Exception as e:
        logger.error(
            "Macro snapshot bootstrap failed (server continues normally): %s", str(e)
        )


async def _run_corp_earnings_bootstrap() -> None:
    """잠정실적 일정 최초 적재 (이후 분기 초 + 주간으로 스케줄러가 재수집)."""
    from app.infrastructure.scheduler.corp_earnings_jobs import job_refresh_corp_earnings

    try:
        await job_refresh_corp_earnings()
    except Exception as e:
        logger.error(
            "Corp earnings bootstrap failed (server continues normally): %s", str(e)
        )


async def run_all_bootstraps() -> None:
    """lifespan 의 yield 직전까지 실행되는 부트스트랩 전체.

    순서 의존: DB → seed → disclosure → market data → macro → corp earnings.
    각 단계 내부의 catch-up 작업은 try/except 로 graceful (실패해도 서버 부팅 계속).
    """
    await _init_database()
    await _seed_stock_themes()
    await _run_disclosure_bootstrap_jobs()
    await _run_market_data_bootstrap()
    await _run_macro_snapshot_bootstrap()
    await _run_corp_earnings_bootstrap()


def start_scheduler():
    """APScheduler 인스턴스 생성·시작. 호출자가 lifespan 종료 시 ``shutdown(wait=False)`` 책임."""
    from app.infrastructure.scheduler.disclosure_scheduler import create_disclosure_scheduler

    scheduler = create_disclosure_scheduler()
    scheduler.start()
    return scheduler
