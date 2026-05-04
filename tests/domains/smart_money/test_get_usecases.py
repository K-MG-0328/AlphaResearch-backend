"""smart_money 의 Get* UseCase 단위 테스트.

- GetInvestorFlowRanking / GetConcentratedBuying / GetGlobalPortfolio /
  GetUSConcentratedBuying / GetInvestorFlowTrend / GetKrPortfolio
- Collect* UseCase 는 외부 API (KRX/SEC EDGAR/DART) 호출이 dominant 라 단위 테스트
  가치 낮음 → 별도 통합/스모크 테스트 필요 시 추가
"""

from datetime import date
from typing import Optional

import pytest

from app.domains.smart_money.application.port.out.global_portfolio_repository_port import (
    GlobalPortfolioRepositoryPort,
    USConcentratedStock,
)
from app.domains.smart_money.application.port.out.investor_flow_repository_port import (
    InvestorFlowRepositoryPort,
)
from app.domains.smart_money.application.port.out.kr_portfolio_repository_port import (
    KrPortfolioRepositoryPort,
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
from app.domains.smart_money.application.usecase.get_kr_portfolio_usecase import (
    GetKrPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_us_concentrated_buying_usecase import (
    GetUSConcentratedBuyingUseCase,
)
from app.domains.smart_money.domain.entity.global_portfolio import ChangeType, GlobalPortfolio
from app.domains.smart_money.domain.entity.investor_flow import InvestorFlow, InvestorType
from app.domains.smart_money.domain.service.smart_money_domain_service import AccumulatedFlow

pytestmark = pytest.mark.asyncio


# ── Fakes ─────────────────────────────────────────────────────────────────


class FakeInvestorFlowRepo(InvestorFlowRepositoryPort):
    def __init__(
        self,
        latest_date: Optional[date] = None,
        recent_dates: Optional[list[date]] = None,
        ranking: Optional[list[InvestorFlow]] = None,
        accumulated: Optional[dict[str, list[AccumulatedFlow]]] = None,
        trend: Optional[list[InvestorFlow]] = None,
    ):
        self._latest = latest_date
        self._recent = recent_dates or []
        self._ranking = ranking or []
        self._accumulated = accumulated or {}
        self._trend = trend or []

    async def exists(self, target_date, investor_type, stock_code):
        return False

    async def save_batch(self, flows):
        return 0

    async def find_ranking(self, target_date, investor_type, limit):
        return list(self._ranking[:limit])

    async def find_latest_date(self, investor_type):
        return self._latest

    async def find_recent_dates(self, investor_type, n):
        return list(self._recent[:n])

    async def find_accumulated_flows(self, since_date, investor_type):
        return list(self._accumulated.get(investor_type, []))

    async def find_trend_by_stock(self, stock_code, since_date):
        return list(self._trend)


class FakeGlobalPortfolioRepo(GlobalPortfolioRepositoryPort):
    def __init__(
        self,
        latest: Optional[list[GlobalPortfolio]] = None,
        names: Optional[list[str]] = None,
        us_concentrated: Optional[list[USConcentratedStock]] = None,
    ):
        self._latest = latest or []
        self._names = names or []
        self._us = us_concentrated or []

    async def find_previous_holdings(self, investor_name, before_date):
        return []

    async def exists_for_period(self, investor_name, reported_at):
        return False

    async def save_batch(self, portfolios):
        return 0

    async def find_latest(self, investor_name=None, change_type=None):
        items = self._latest
        if investor_name:
            items = [h for h in items if h.investor_name == investor_name]
        if change_type:
            items = [h for h in items if h.change_type == change_type]
        return list(items)

    async def find_investor_names(self):
        return list(self._names)

    async def find_us_concentrated(self, limit=20):
        return list(self._us[:limit])


# ── GetInvestorFlowRankingUseCase ─────────────────────────────────────────


async def test_ranking_uses_latest_date_when_target_date_none():
    flow = InvestorFlow(
        date=date(2026, 5, 1),
        investor_type=InvestorType.FOREIGN,
        stock_code="005930",
        stock_name="삼성전자",
        net_buy_amount=1_000_000,
        net_buy_volume=100,
    )
    repo = FakeInvestorFlowRepo(latest_date=date(2026, 5, 1), ranking=[flow])
    usecase = GetInvestorFlowRankingUseCase(repo)

    response = await usecase.execute(investor_type=InvestorType.FOREIGN, target_date=None, limit=20)

    assert response.date == date(2026, 5, 1)
    assert len(response.items) == 1
    assert response.items[0].rank == 1
    assert response.items[0].stock_code == "005930"


async def test_ranking_returns_empty_when_no_data():
    repo = FakeInvestorFlowRepo(latest_date=None, ranking=[])
    usecase = GetInvestorFlowRankingUseCase(repo)

    response = await usecase.execute(investor_type=InvestorType.FOREIGN)

    assert response.items == []
    assert response.date is None


async def test_ranking_assigns_sequential_ranks():
    flows = [
        InvestorFlow(
            date=date(2026, 5, 1),
            investor_type=InvestorType.INSTITUTION,
            stock_code=f"00000{i}",
            stock_name=f"S{i}",
            net_buy_amount=1000 - i,
            net_buy_volume=10,
        )
        for i in range(3)
    ]
    repo = FakeInvestorFlowRepo(latest_date=date(2026, 5, 1), ranking=flows)
    usecase = GetInvestorFlowRankingUseCase(repo)

    response = await usecase.execute(investor_type=InvestorType.INSTITUTION, limit=20)

    assert [it.rank for it in response.items] == [1, 2, 3]


# ── GetConcentratedBuyingUseCase ──────────────────────────────────────────


async def test_concentrated_returns_empty_when_no_recent_dates():
    repo = FakeInvestorFlowRepo(recent_dates=[])
    usecase = GetConcentratedBuyingUseCase(repo)

    response = await usecase.execute(days=5, limit=50)

    assert response.total == 0
    assert response.items == []
    assert response.since_date is None
    assert response.days == 5


async def test_concentrated_returns_intersection_with_score():
    repo = FakeInvestorFlowRepo(
        recent_dates=[date(2026, 5, 1), date(2026, 5, 2)],
        accumulated={
            "FOREIGN": [
                AccumulatedFlow(stock_code="005930", stock_name="삼성전자", total_net_buy=1_000_000),
                AccumulatedFlow(stock_code="000660", stock_name="SK하이닉스", total_net_buy=500_000),
            ],
            "INSTITUTION": [
                AccumulatedFlow(stock_code="005930", stock_name="삼성전자", total_net_buy=800_000),
                AccumulatedFlow(stock_code="035720", stock_name="카카오", total_net_buy=300_000),
            ],
        },
    )
    usecase = GetConcentratedBuyingUseCase(repo)

    response = await usecase.execute(days=2, limit=10)

    # 외국인·기관 동시 매수 종목은 005930 (삼성전자) 만
    assert response.total == 1
    assert response.items[0].stock_code == "005930"
    assert response.items[0].foreign_net_buy == 1_000_000
    assert response.items[0].institution_net_buy == 800_000
    assert response.since_date == date(2026, 5, 1)


# ── GetGlobalPortfolioUseCase ─────────────────────────────────────────────


async def test_global_portfolio_returns_all_when_no_filter():
    holdings = [
        GlobalPortfolio(
            investor_name="Buffett",
            ticker="AAPL",
            stock_name="Apple",
            cusip="037833100",
            shares=1000,
            market_value=200000,
            portfolio_weight=10.5,
            change_type=ChangeType.NEW,
            reported_at=date(2026, 3, 31),
        ),
    ]
    usecase = GetGlobalPortfolioUseCase(FakeGlobalPortfolioRepo(latest=holdings))

    response = await usecase.execute()

    assert response.total == 1
    assert response.items[0].investor_name == "Buffett"
    assert response.items[0].ticker == "AAPL"


async def test_global_portfolio_filters_by_investor_name():
    holdings = [
        GlobalPortfolio(
            investor_name="Buffett", ticker="AAPL", stock_name="Apple",
            cusip="037833100", shares=1000, market_value=1, portfolio_weight=1,
            change_type=ChangeType.NEW, reported_at=date(2026, 3, 31),
        ),
        GlobalPortfolio(
            investor_name="Burry", ticker="TSLA", stock_name="Tesla",
            cusip="88160R101", shares=500, market_value=1, portfolio_weight=1,
            change_type=ChangeType.NEW, reported_at=date(2026, 3, 31),
        ),
    ]
    usecase = GetGlobalPortfolioUseCase(FakeGlobalPortfolioRepo(latest=holdings))

    response = await usecase.execute(investor_name="Buffett")

    assert response.total == 1
    assert response.items[0].investor_name == "Buffett"
    assert response.investor_name == "Buffett"


async def test_global_portfolio_filters_by_change_type():
    holdings = [
        GlobalPortfolio(
            investor_name="A", ticker="X", stock_name="X", cusip="C1",
            shares=1, market_value=1, portfolio_weight=1,
            change_type=ChangeType.NEW, reported_at=date(2026, 3, 31),
        ),
        GlobalPortfolio(
            investor_name="A", ticker="Y", stock_name="Y", cusip="C2",
            shares=1, market_value=1, portfolio_weight=1,
            change_type=ChangeType.CLOSED, reported_at=date(2026, 3, 31),
        ),
    ]
    usecase = GetGlobalPortfolioUseCase(FakeGlobalPortfolioRepo(latest=holdings))

    response = await usecase.execute(change_type=ChangeType.NEW)

    assert response.total == 1
    assert response.items[0].change_type == ChangeType.NEW


async def test_global_portfolio_get_investor_names():
    repo = FakeGlobalPortfolioRepo(names=["Buffett", "Burry", "Munger"])
    usecase = GetGlobalPortfolioUseCase(repo)

    response = await usecase.get_investor_names()

    assert response.investors == ["Buffett", "Burry", "Munger"]


# ── GetUSConcentratedBuyingUseCase ────────────────────────────────────────


async def test_us_concentrated_returns_items_with_investor_count():
    stocks = [
        USConcentratedStock(
            ticker="NVDA", stock_name="NVIDIA",
            investor_count=5, total_market_value=100_000_000,
            investors=["Buffett", "Burry"], reported_at=date(2026, 3, 31),
        ),
    ]
    usecase = GetUSConcentratedBuyingUseCase(FakeGlobalPortfolioRepo(us_concentrated=stocks))

    response = await usecase.execute(limit=20)

    assert len(response.items) == 1
    assert response.items[0].ticker == "NVDA"
    assert response.items[0].investor_count == 5


async def test_us_concentrated_returns_empty_when_none():
    usecase = GetUSConcentratedBuyingUseCase(FakeGlobalPortfolioRepo(us_concentrated=[]))

    response = await usecase.execute(limit=20)

    assert response.items == []


# ── GetKrPortfolioUseCase ─────────────────────────────────────────────────


class FakeKrPortfolioRepo(KrPortfolioRepositoryPort):
    def __init__(self, items: Optional[list] = None, total: int = 0):
        self._items = items or []
        self._total = total

    async def save_batch(self, portfolios):
        return 0

    async def find_by_investor(self, investor_name):
        return [it for it in self._items if it.investor_name == investor_name]

    async def find_one(self, investor_name, stock_code):
        return None

    async def upsert(self, holding):
        return None

    async def find_all_investor_names(self):
        return []

    async def count(self):
        return self._total


async def test_kr_portfolio_get_total_count():
    repo = FakeKrPortfolioRepo(total=42)
    usecase = GetKrPortfolioUseCase(repo)

    total = await usecase.get_total_count()

    assert total == 42
