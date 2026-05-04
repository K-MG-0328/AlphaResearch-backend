"""news.SaveArticleUseCase + GetInterestArticleUseCase + SaveInterestArticleUseCase 단위 테스트.

Fake repository / fake content provider 로 외부 의존(SQLAlchemy/HTTP) 격리.
"""

from datetime import datetime
from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.news.application.port.article_content_provider import (
    ArticleContentProvider,
)
from app.domains.news.application.port.article_content_repository import (
    ArticleContentRepository,
)
from app.domains.news.application.port.saved_article_repository import (
    SavedArticleRepository,
)
from app.domains.news.application.port.user_saved_article_repository import (
    UserSavedArticleRepository,
)
from app.domains.news.application.request.save_article_request import SaveArticleRequest
from app.domains.news.application.request.save_user_article_request import (
    SaveUserArticleRequest,
)
from app.domains.news.application.usecase.get_interest_article_usecase import (
    GetInterestArticleUseCase,
)
from app.domains.news.application.usecase.save_article_usecase import SaveArticleUseCase
from app.domains.news.application.usecase.save_interest_article_usecase import (
    SaveInterestArticleUseCase,
)
from app.domains.news.domain.entity.saved_article import SavedArticle
from app.domains.news.domain.entity.user_saved_article import UserSavedArticle

pytestmark = pytest.mark.asyncio


# ── Fakes ─────────────────────────────────────────────────────────────────


class FakeSavedArticleRepository(SavedArticleRepository):
    def __init__(self, by_link: Optional[dict[str, SavedArticle]] = None):
        self._by_link = dict(by_link or {})
        self._next_id = max((a.article_id or 0 for a in self._by_link.values()), default=0) + 1
        self.saved: list[SavedArticle] = []

    async def save(self, article: SavedArticle) -> SavedArticle:
        article.article_id = self._next_id
        self._next_id += 1
        article.saved_at = datetime.now()
        self.saved.append(article)
        self._by_link[article.link] = article
        return article

    async def find_by_id(self, article_id):
        return next((a for a in self._by_link.values() if a.article_id == article_id), None)

    async def find_by_link(self, link: str) -> Optional[SavedArticle]:
        return self._by_link.get(link)

    async def find_all(self, page, page_size):
        items = list(self._by_link.values())
        offset = (page - 1) * page_size
        return items[offset : offset + page_size], len(items)


class FakeUserSavedArticleRepository(UserSavedArticleRepository):
    def __init__(self):
        self._articles: dict[int, UserSavedArticle] = {}
        self._next_id = 1
        self.deleted: list[int] = []

    async def save(self, article: UserSavedArticle) -> UserSavedArticle:
        article.article_id = self._next_id
        self._next_id += 1
        article.saved_at = datetime.now()
        self._articles[article.article_id] = article
        return article

    async def find_by_user_and_link(self, account_id: int, link: str):
        return next(
            (a for a in self._articles.values()
             if a.account_id == account_id and a.link == link),
            None,
        )

    async def find_by_id(self, article_id: int):
        return self._articles.get(article_id)

    async def find_all_by_user(self, account_id, page, page_size):
        items = [a for a in self._articles.values() if a.account_id == account_id]
        offset = (page - 1) * page_size
        return items[offset : offset + page_size], len(items)

    async def delete_by_id(self, article_id):
        self._articles.pop(article_id, None)
        self.deleted.append(article_id)


class FakeContentRepository(ArticleContentRepository):
    def __init__(self, by_id: Optional[dict[int, str]] = None):
        self._by_id = dict(by_id or {})
        self.saves: list[tuple[int, Optional[str], Optional[str]]] = []

    async def save(self, user_saved_article_id, content, snippet):
        self.saves.append((user_saved_article_id, content, snippet))
        if content:
            self._by_id[user_saved_article_id] = content

    async def find_by_article_id(self, user_saved_article_id):
        return self._by_id.get(user_saved_article_id)


class FakeContentProvider(ArticleContentProvider):
    def __init__(self, content: str = "<scraped body>", raise_exc: bool = False):
        self._content = content
        self._raise = raise_exc

    async def fetch_content(self, url: str) -> str:
        if self._raise:
            raise RuntimeError("scrape failed")
        return self._content


# ── SaveArticleUseCase ────────────────────────────────────────────────────


async def test_save_raises_409_when_link_already_saved():
    existing = SavedArticle(title="existing", link="https://x/1", article_id=42)
    repo = FakeSavedArticleRepository(by_link={"https://x/1": existing})
    usecase = SaveArticleUseCase(repo, FakeContentProvider())

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            SaveArticleRequest(title="new", link="https://x/1"),
        )

    assert exc.value.status_code == 409
    assert repo.saved == []


async def test_save_scrapes_content_and_persists():
    repo = FakeSavedArticleRepository()
    usecase = SaveArticleUseCase(
        repo, FakeContentProvider(content="<scraped body>"),
    )

    response = await usecase.execute(
        SaveArticleRequest(
            title="new", link="https://x/2", source="src", snippet="s",
        ),
    )

    assert response.article_id == 1
    assert response.title == "new"
    assert response.content == "<scraped body>"
    assert len(repo.saved) == 1


# ── SaveInterestArticleUseCase ────────────────────────────────────────────


async def test_save_interest_raises_409_when_user_already_saved_link():
    repo = FakeUserSavedArticleRepository()
    await repo.save(UserSavedArticle(account_id=1, title="t", link="https://x/3"))
    usecase = SaveInterestArticleUseCase(
        repo, FakeContentRepository(), FakeContentProvider(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            account_id=1,
            request=SaveUserArticleRequest(title="t2", link="https://x/3"),
        )

    assert exc.value.status_code == 409


async def test_save_interest_persists_metadata_and_content():
    repo = FakeUserSavedArticleRepository()
    content_repo = FakeContentRepository()
    usecase = SaveInterestArticleUseCase(
        repo, content_repo, FakeContentProvider(content="full body"),
    )

    response = await usecase.execute(
        account_id=2,
        request=SaveUserArticleRequest(title="t", link="https://x/4", snippet="s"),
    )

    assert response.id == 1
    assert response.content == "full body"
    # 본문 JSONB 저장 호출 확인
    assert len(content_repo.saves) == 1
    assert content_repo.saves[0][0] == 1  # user_saved_article_id


async def test_save_interest_rolls_back_when_content_save_fails():
    """스크래핑 실패 시 메타데이터 롤백 + 502."""
    repo = FakeUserSavedArticleRepository()
    content_repo = FakeContentRepository()
    usecase = SaveInterestArticleUseCase(
        repo, content_repo, FakeContentProvider(raise_exc=True),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            account_id=2,
            request=SaveUserArticleRequest(title="t", link="https://x/5"),
        )

    assert exc.value.status_code == 502
    # 메타데이터 롤백 — delete_by_id 호출 + 보관소 비어있음
    assert repo.deleted == [1]


# ── GetInterestArticleUseCase ─────────────────────────────────────────────


async def test_get_interest_raises_404_when_article_missing():
    usecase = GetInterestArticleUseCase(
        FakeUserSavedArticleRepository(), FakeContentRepository(), FakeContentProvider(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(account_id=1, article_id=999)

    assert exc.value.status_code == 404


async def test_get_interest_raises_403_when_other_user_owns():
    repo = FakeUserSavedArticleRepository()
    await repo.save(UserSavedArticle(account_id=99, title="t", link="https://x/6"))
    usecase = GetInterestArticleUseCase(repo, FakeContentRepository(), FakeContentProvider())

    with pytest.raises(AppException) as exc:
        await usecase.execute(account_id=1, article_id=1)

    assert exc.value.status_code == 403


async def test_get_interest_returns_cached_content_without_rescrape():
    repo = FakeUserSavedArticleRepository()
    await repo.save(UserSavedArticle(account_id=1, title="t", link="https://x/7"))
    content_repo = FakeContentRepository(by_id={1: "cached body"})
    provider = FakeContentProvider(content="should-not-be-called")
    usecase = GetInterestArticleUseCase(repo, content_repo, provider)

    response = await usecase.execute(account_id=1, article_id=1)

    assert response.content == "cached body"
    # cache hit 시 재스크래핑 안 함
    assert content_repo.saves == []


async def test_get_interest_rescrapes_when_content_missing():
    repo = FakeUserSavedArticleRepository()
    await repo.save(UserSavedArticle(account_id=1, title="t", link="https://x/8"))
    content_repo = FakeContentRepository()  # 빈 cache
    usecase = GetInterestArticleUseCase(
        repo, content_repo, FakeContentProvider(content="fresh body"),
    )

    response = await usecase.execute(account_id=1, article_id=1)

    assert response.content == "fresh body"
    # 재스크래핑 결과 cache 에 저장됨
    assert len(content_repo.saves) == 1


async def test_get_interest_returns_empty_content_when_rescrape_fails():
    repo = FakeUserSavedArticleRepository()
    await repo.save(UserSavedArticle(account_id=1, title="t", link="https://x/9"))
    content_repo = FakeContentRepository()
    usecase = GetInterestArticleUseCase(
        repo, content_repo, FakeContentProvider(raise_exc=True),
    )

    # 재스크래핑 실패는 graceful — 빈 content 로 응답
    response = await usecase.execute(account_id=1, article_id=1)

    assert response.content == ""
