"""SQLAlchemy 메타데이터에 모든 도메인 ORM 모델을 등록.

`Base.metadata.create_all` 이 모든 테이블을 인식하려면 모델 클래스가 import 되어
``Base.subclasses`` 에 포함되어야 한다. main.py 가 한 줄

    from app.infrastructure.bootstrap import orm_imports  # noqa: F401

으로 이 모듈을 로드하면 아래 import 가 메타 등록을 일괄 수행한다.

새 ORM 모델을 추가했다면 이 파일에도 import 한 줄 추가할 것.
"""

# fmt: off
import app.domains.account.infrastructure.orm.account_orm  # noqa: F401
import app.domains.account.infrastructure.orm.user_watchlist_orm  # noqa: F401
import app.domains.agent.infrastructure.orm.integrated_analysis_orm  # noqa: F401
import app.domains.board.infrastructure.orm.board_orm  # noqa: F401
import app.domains.dashboard.infrastructure.orm.nasdaq_bar_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.collection_job_item_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.collection_job_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.company_data_coverage_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.company_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.disclosure_document_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.disclosure_orm  # noqa: F401
import app.domains.disclosure.infrastructure.orm.rag_document_chunk_orm  # noqa: F401
import app.domains.history_agent.infrastructure.orm.event_enrichment_orm  # noqa: F401
import app.domains.investment.infrastructure.orm.investment_news_content_orm  # noqa: F401
import app.domains.investment.infrastructure.orm.investment_youtube_log_orm  # noqa: F401
import app.domains.investment.infrastructure.orm.investment_youtube_video_comment_orm  # noqa: F401
import app.domains.investment.infrastructure.orm.investment_youtube_video_orm  # noqa: F401
import app.domains.news.infrastructure.orm.article_content_orm  # noqa: F401
import app.domains.news.infrastructure.orm.collected_news_orm  # noqa: F401
import app.domains.news.infrastructure.orm.investment_news_orm  # noqa: F401
import app.domains.news.infrastructure.orm.saved_article_orm  # noqa: F401
import app.domains.news.infrastructure.orm.user_saved_article_orm  # noqa: F401
import app.domains.post.infrastructure.orm.post_orm  # noqa: F401
import app.domains.schedule.infrastructure.orm.economic_event_orm  # noqa: F401
import app.domains.smart_money.infrastructure.orm.global_portfolio_orm  # noqa: F401
import app.domains.smart_money.infrastructure.orm.investor_flow_orm  # noqa: F401
import app.domains.smart_money.infrastructure.orm.kr_portfolio_orm  # noqa: F401
import app.domains.stock.infrastructure.orm.stock_vector_document_orm  # noqa: F401
import app.domains.stock.market_data.infrastructure.orm.daily_bar_orm  # noqa: F401
import app.domains.stock.market_data.infrastructure.orm.event_impact_metric_orm  # noqa: F401
import app.domains.stock.market_data.infrastructure.orm.popular_stock_ticker_orm  # noqa: F401
import app.domains.stock_theme.infrastructure.orm.stock_theme_orm  # noqa: F401
# fmt: on
