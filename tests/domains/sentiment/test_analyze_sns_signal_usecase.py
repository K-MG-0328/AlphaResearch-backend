"""sentiment.AnalyzeSnsSignalUseCase 단위 테스트.

분기:
- collect_usecase 주입 + 게시물 부족 → 자동 수집 트리거 (실패 시 graceful)
- 게시물 0건 → "분석할 SNS 게시물이 없습니다" neutral 응답
- 정상 케이스 → analysis_port.analyze 호출 + 결과 elapsed_ms 덮어쓰기
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest

from app.domains.news.application.port.ticker_keyword_resolver_port import (
    TickerKeywordResolverPort,
)
from app.domains.sentiment.application.port.sns_post_repository_port import (
    SnsPostRepositoryPort,
)
from app.domains.sentiment.application.port.sns_signal_analysis_port import (
    SnsSignalAnalysisPort,
)
from app.domains.sentiment.application.response.analyze_sns_signal_response import (
    SnsSignalResult,
)
from app.domains.sentiment.application.usecase.analyze_sns_signal_usecase import (
    AnalyzeSnsSignalUseCase,
)
from app.domains.sentiment.application.usecase.collect_sns_posts_usecase import (
    CollectSnsPostsUseCase,
)
from app.domains.sentiment.domain.entity.sns_post import SnsPost

pytestmark = pytest.mark.asyncio


class FakeSnsPostRepo(SnsPostRepositoryPort):
    def __init__(self, posts: Optional[list[SnsPost]] = None, count_by: Optional[dict[str, int]] = None):
        self._posts = posts or []
        self._count_by = count_by or {}

    async def save(self, post):
        return post

    async def save_batch(self, posts):
        return len(posts)

    async def exists_by_hash(self, post_hash):
        return False

    async def find_by_ticker(self, ticker, platform=None, limit=100):
        return [p for p in self._posts if p.ticker == ticker][:limit]

    async def count_by_ticker(self, ticker):
        return self._count_by.get(ticker, 0)


class FakeAnalysisPort(SnsSignalAnalysisPort):
    def __init__(self, result: SnsSignalResult):
        self._result = result
        self.calls: list[tuple] = []

    async def analyze(self, ticker, company_name, posts):
        self.calls.append((ticker, company_name, len(posts)))
        # caller 가 elapsed_ms 를 덮어쓰므로 그대로 반환
        return self._result


class FakeKeywordResolver(TickerKeywordResolverPort):
    def __init__(self, keywords: Optional[list[str]] = None):
        self._kw = keywords or []

    async def resolve(self, ticker):
        return list(self._kw)


class FakeCollectUseCase:
    """CollectSnsPostsUseCase 의 형태만 모방 (execute coroutine)."""

    def __init__(self, raise_exc: bool = False):
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def execute(self, ticker: str, limit_per_platform: int = 20):
        self.calls.append({"ticker": ticker, "limit_per_platform": limit_per_platform})
        if self._raise:
            raise RuntimeError("collect failed (graceful test)")


def _make_post(ticker: str = "005930") -> SnsPost:
    return SnsPost(
        platform="reddit",
        post_id=f"p-{ticker}",
        post_hash=f"hash-{ticker}",
        ticker=ticker,
        content="some content",
        url="https://example.com/p",
        author="anon",
    )


def _make_result(ticker: str) -> SnsSignalResult:
    return SnsSignalResult(
        ticker=ticker,
        signal="bullish",
        confidence=0.85,
        total_sample_size=10,
        reasoning="positive sentiment dominant",
        elapsed_ms=999,  # caller 가 덮어씀
    )


# ── 분기 1: 게시물 0건 → neutral ──────────────────────────────────────────


async def test_returns_neutral_when_no_posts():
    repo = FakeSnsPostRepo(posts=[])
    analysis = FakeAnalysisPort(_make_result("005930"))
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(["삼성전자"]), collect_usecase=None,
    )

    result = await usecase.execute(ticker="005930")

    assert result.signal == "neutral"
    assert result.confidence == 0.0
    assert result.total_sample_size == 0
    assert result.reasoning == "분석할 SNS 게시물이 없습니다."
    # analysis_port 호출 안 됨
    assert analysis.calls == []


# ── 분기 2: 정상 케이스 ────────────────────────────────────────────────────


async def test_normal_case_calls_analysis_with_company_name():
    posts = [_make_post() for _ in range(3)]
    repo = FakeSnsPostRepo(posts=posts)
    expected = _make_result("005930")
    analysis = FakeAnalysisPort(expected)
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(["삼성전자"]), collect_usecase=None,
    )

    result = await usecase.execute(ticker="005930", lookback_limit=10)

    # analyze 호출 검증
    assert len(analysis.calls) == 1
    ticker, company_name, posts_count = analysis.calls[0]
    assert ticker == "005930"
    assert company_name == "삼성전자"  # keyword[0] 사용
    assert posts_count == 3
    # 결과 그대로 반환 (elapsed_ms 만 caller 에서 덮어씀)
    assert result.signal == "bullish"
    assert result.confidence == 0.85
    assert result.elapsed_ms != 999  # caller 가 덮어씀 — 0 또는 양수


async def test_falls_back_to_ticker_when_no_keyword():
    posts = [_make_post(ticker="AAPL")]
    repo = FakeSnsPostRepo(posts=posts)
    analysis = FakeAnalysisPort(_make_result("AAPL"))
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(keywords=[]), collect_usecase=None,
    )

    await usecase.execute(ticker="AAPL")

    # company_name fallback to ticker
    assert analysis.calls[0][1] == "AAPL"


# ── 분기 3: collect_usecase 주입 + 게시물 부족 ────────────────────────────


async def test_triggers_auto_collect_when_count_below_threshold():
    repo = FakeSnsPostRepo(posts=[_make_post()], count_by={"005930": 2})  # < 5
    analysis = FakeAnalysisPort(_make_result("005930"))
    collect = FakeCollectUseCase(raise_exc=False)
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(["삼성전자"]), collect_usecase=collect,
    )

    await usecase.execute(ticker="005930")

    assert len(collect.calls) == 1
    assert collect.calls[0]["ticker"] == "005930"
    assert collect.calls[0]["limit_per_platform"] == 20


async def test_skips_auto_collect_when_count_at_or_above_threshold():
    repo = FakeSnsPostRepo(posts=[_make_post()], count_by={"005930": 5})  # 임계값 동일
    analysis = FakeAnalysisPort(_make_result("005930"))
    collect = FakeCollectUseCase(raise_exc=False)
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(["삼성전자"]), collect_usecase=collect,
    )

    await usecase.execute(ticker="005930")

    # 임계값(5) 이상이면 자동 수집 trigger 안 됨
    assert collect.calls == []


async def test_continues_analysis_when_auto_collect_fails():
    """자동 수집 실패는 graceful — 분석은 계속 진행."""
    repo = FakeSnsPostRepo(posts=[_make_post()], count_by={"005930": 0})
    analysis = FakeAnalysisPort(_make_result("005930"))
    collect = FakeCollectUseCase(raise_exc=True)
    usecase = AnalyzeSnsSignalUseCase(
        repo, analysis, FakeKeywordResolver(["삼성전자"]), collect_usecase=collect,
    )

    # 예외 없이 정상 결과 반환
    result = await usecase.execute(ticker="005930")

    assert result.signal == "bullish"
    assert len(analysis.calls) == 1
