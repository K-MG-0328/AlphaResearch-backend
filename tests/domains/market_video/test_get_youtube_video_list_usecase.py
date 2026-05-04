"""market_video.GetYoutubeVideoListUseCase 단위 테스트."""

from typing import Optional

import pytest

from app.domains.market_video.application.port.out.youtube_video_provider import (
    YoutubeVideoProvider,
    YoutubeVideoSearchResult,
)
from app.domains.market_video.application.usecase.get_youtube_video_list_usecase import (
    GetYoutubeVideoListUseCase,
)
from app.domains.market_video.domain.entity.video_item import VideoItem

pytestmark = pytest.mark.asyncio


class FakeYoutubeProvider(YoutubeVideoProvider):
    def __init__(self, result: YoutubeVideoSearchResult):
        self._result = result
        self.calls: list[Optional[str]] = []

    async def search(self, page_token: Optional[str] = None) -> YoutubeVideoSearchResult:
        self.calls.append(page_token)
        return self._result


def _video(idx: int) -> VideoItem:
    return VideoItem(
        video_id=f"v-{idx}",
        title=f"video {idx}",
        thumbnail_url=f"https://thumb/{idx}.png",
        channel_name=f"channel {idx}",
        published_at="2026-05-01",
        video_url=f"https://yt/watch?v=v-{idx}",
    )


async def test_returns_paginated_result():
    provider = FakeYoutubeProvider(
        YoutubeVideoSearchResult(
            items=[_video(i) for i in range(3)],
            next_page_token="next",
            prev_page_token=None,
            total_results=42,
        )
    )
    usecase = GetYoutubeVideoListUseCase(provider)

    response = await usecase.execute()

    assert len(response.items) == 3
    assert response.next_page_token == "next"
    assert response.prev_page_token is None
    assert response.total_results == 42
    # provider 첫 호출은 page_token=None
    assert provider.calls == [None]


async def test_passes_page_token_through():
    provider = FakeYoutubeProvider(
        YoutubeVideoSearchResult(items=[], next_page_token=None, prev_page_token="prev", total_results=0)
    )
    usecase = GetYoutubeVideoListUseCase(provider)

    await usecase.execute(page_token="token-123")

    assert provider.calls == ["token-123"]


async def test_returns_empty_items_when_provider_empty():
    provider = FakeYoutubeProvider(
        YoutubeVideoSearchResult(items=[], next_page_token=None, prev_page_token=None, total_results=0)
    )
    usecase = GetYoutubeVideoListUseCase(provider)

    response = await usecase.execute()

    assert response.items == []
    assert response.total_results == 0


async def test_maps_video_item_fields_to_response():
    """VideoItem 의 모든 필드가 VideoItemResponse 에 매핑되는지 확인. video_id 만 응답에서 제외."""
    provider = FakeYoutubeProvider(
        YoutubeVideoSearchResult(items=[_video(0)], next_page_token=None, prev_page_token=None, total_results=1)
    )
    usecase = GetYoutubeVideoListUseCase(provider)

    response = await usecase.execute()
    item = response.items[0]

    assert item.title == "video 0"
    assert item.thumbnail_url == "https://thumb/0.png"
    assert item.channel_name == "channel 0"
    assert item.published_at == "2026-05-01"
    assert item.video_url == "https://yt/watch?v=v-0"
