"""post 도메인 UseCase 단위 테스트.

Fake repository 로 외부 의존(SQLAlchemy/DB) 제거. CreatePost / GetPost / GetPostList
3개 UseCase 핵심 path + edge case 커버.
"""

from datetime import datetime
from typing import Optional

import pytest

from app.domains.post.application.port.post_repository import PostRepository
from app.domains.post.application.request.create_post_request import CreatePostRequest
from app.domains.post.application.usecase.create_post_usecase import CreatePostUseCase
from app.domains.post.application.usecase.get_post_list_usecase import GetPostListUseCase
from app.domains.post.application.usecase.get_post_usecase import GetPostUseCase
from app.domains.post.domain.entity.post import Post

pytestmark = pytest.mark.asyncio


class FakePostRepository(PostRepository):
    """In-memory PostRepository. id 자동 증가."""

    def __init__(self, posts: Optional[list[Post]] = None):
        self._posts: list[Post] = list(posts or [])
        self._next_id = max((p.post_id or 0 for p in self._posts), default=0) + 1

    async def save(self, post: Post) -> Post:
        post.post_id = self._next_id
        self._next_id += 1
        post.created_at = post.created_at or datetime.now()
        self._posts.append(post)
        return post

    async def find_by_id(self, post_id: int) -> Post | None:
        for p in self._posts:
            if p.post_id == post_id:
                return p
        return None

    async def find_all(self, page: int, size: int) -> tuple[list[Post], int]:
        # 최신순(created_at desc) 보존
        sorted_posts = sorted(self._posts, key=lambda p: p.created_at, reverse=True)
        offset = (page - 1) * size
        return sorted_posts[offset : offset + size], len(self._posts)


# ── CreatePostUseCase ──────────────────────────────────────────────────────


async def test_create_post_returns_response_with_assigned_id():
    repo = FakePostRepository()
    usecase = CreatePostUseCase(repo)

    response = await usecase.execute(CreatePostRequest(title="제목", content="본문"))

    assert response.post_id == 1
    assert response.title == "제목"
    assert response.content == "본문"
    assert response.created_at is not None


async def test_create_post_persists_to_repository():
    repo = FakePostRepository()
    usecase = CreatePostUseCase(repo)

    await usecase.execute(CreatePostRequest(title="t", content="c"))
    posts, total = await repo.find_all(page=1, size=10)

    assert total == 1
    assert posts[0].title == "t"
    assert posts[0].content == "c"


# ── GetPostUseCase ─────────────────────────────────────────────────────────


async def test_get_post_returns_detail_when_exists():
    existing = Post(title="hello", content="world", post_id=42, created_at=datetime(2026, 1, 1))
    repo = FakePostRepository(posts=[existing])
    usecase = GetPostUseCase(repo)

    response = await usecase.execute(post_id=42)

    assert response is not None
    assert response.post_id == 42
    assert response.title == "hello"
    assert response.content == "world"


async def test_get_post_returns_none_when_not_found():
    repo = FakePostRepository()
    usecase = GetPostUseCase(repo)

    response = await usecase.execute(post_id=999)

    assert response is None


# ── GetPostListUseCase ─────────────────────────────────────────────────────


async def test_get_post_list_paginates_and_returns_total():
    posts = [
        Post(title=f"t{i}", content=f"c{i}", post_id=i, created_at=datetime(2026, 1, i + 1))
        for i in range(5)
    ]
    repo = FakePostRepository(posts=posts)
    usecase = GetPostListUseCase(repo)

    response = await usecase.execute(page=1, size=3)

    assert response.total == 5
    assert response.page == 1
    assert response.size == 3
    assert len(response.posts) == 3
    # created_at desc 정렬 확인 (가장 최신 = i=4)
    assert response.posts[0].title == "t4"


async def test_get_post_list_returns_empty_when_no_posts():
    repo = FakePostRepository()
    usecase = GetPostListUseCase(repo)

    response = await usecase.execute(page=1, size=10)

    assert response.total == 0
    assert response.posts == []
    assert response.page == 1
    assert response.size == 10
