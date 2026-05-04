"""market_video.ExtractNounsUseCase 단위 테스트."""

from datetime import datetime

import pytest

from app.domains.market_video.application.port.out.morpheme_analyzer_port import (
    MorphemeAnalyzerPort,
)
from app.domains.market_video.application.port.out.video_comment_repository_port import (
    VideoCommentRepositoryPort,
)
from app.domains.market_video.application.usecase.extract_nouns_usecase import (
    ExtractNounsUseCase,
)
from app.domains.market_video.domain.entity.video_comment import VideoComment

pytestmark = pytest.mark.asyncio


class FakeCommentRepo(VideoCommentRepositoryPort):
    def __init__(self, comments: list[VideoComment]):
        self._comments = comments

    async def save_all(self, comments):
        return None

    async def find_all(self):
        return list(self._comments)


class FakeNounAnalyzer(MorphemeAnalyzerPort):
    """단순한 공백 분리 — 테스트 용도."""

    def extract_nouns(self, text: str) -> list[str]:
        return text.split()


def _comment(idx: int, content: str) -> VideoComment:
    return VideoComment(
        comment_id=f"c-{idx}",
        video_id="v-0",
        author_name=f"author {idx}",
        content=content,
        published_at=datetime(2026, 5, 1),
        like_count=0,
    )


async def test_returns_empty_when_no_comments():
    usecase = ExtractNounsUseCase(FakeCommentRepo(comments=[]), FakeNounAnalyzer())

    response = await usecase.execute(top_n=10)

    assert response.total_unique_nouns == 0
    assert response.selected_count == 0
    assert response.items == []


async def test_counts_noun_frequencies_and_returns_top_n():
    comments = [
        _comment(0, "삼성 반도체 삼성"),
        _comment(1, "반도체 호황 반도체"),
        _comment(2, "엔비디아 호황"),
    ]
    usecase = ExtractNounsUseCase(FakeCommentRepo(comments=comments), FakeNounAnalyzer())

    response = await usecase.execute(top_n=2)

    # 빈도 (synonym 병합 후): 반도체=3, 삼성=2, 호황=2, 엔비디아=1
    assert response.total_unique_nouns >= 2
    assert response.selected_count == 2
    # Top-1 은 반도체 (3회)
    assert response.items[0].noun == "반도체"
    assert response.items[0].count == 3


async def test_top_n_caps_response_size():
    comments = [_comment(i, f"단어{i}") for i in range(50)]
    usecase = ExtractNounsUseCase(FakeCommentRepo(comments=comments), FakeNounAnalyzer())

    response = await usecase.execute(top_n=5)

    # 전체 unique 50, selected 만 5
    assert response.total_unique_nouns >= 5
    assert response.selected_count == 5
    assert len(response.items) == 5
