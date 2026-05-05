# /api/v1 공통 라우터 집합
#
# 팀원 가이드: 새 도메인 라우터를 만들면 이 파일에 include_router 만 추가.
# 도메인 그룹별로 정리되어 있다 (Phase H7 — 일관성 정리). 인증 정책은
# `app/common/auth/dependencies.py` 참조.

from fastapi import APIRouter

# Auth & Account
from app.domains.auth.adapter.inbound.api.auth_router import router as auth_router
from app.domains.auth.adapter.inbound.api.kakao_auth_router import router as kakao_auth_router
from app.domains.account.adapter.inbound.api.account_router import router as account_router
from app.domains.account.adapter.inbound.api.users_router import router as users_router

# Agents (4개 — agent / history_agent / causality_agent(내부 only) / investment)
from app.domains.agent.adapter.inbound.api.agent_router import router as agent_router
from app.domains.history_agent.adapter.inbound.api.history_agent_router import router as history_agent_router
from app.domains.investment.adapter.inbound.api.investment_router import router as investment_router
from app.domains.api_schema.adapter.inbound.api.api_schema_router import router as api_schema_router

# Market data — Dashboard / Stock / Macro / Smart Money / Schedule
from app.domains.dashboard.adapter.inbound.api.dashboard_router import router as dashboard_router
from app.domains.stock.adapter.inbound.api.stock_router import router as stock_router
from app.domains.stock_theme.adapter.inbound.api.stock_theme_router import router as stock_theme_router
from app.domains.stock_theme.adapter.inbound.api.stocks_router import router as stocks_router
from app.domains.macro.adapter.inbound.api.macro_router import router as macro_router
from app.domains.smart_money.adapter.inbound.api.smart_money_router import router as smart_money_router
from app.domains.schedule.adapter.inbound.api.schedule_router import router as schedule_router

# Content — News / Disclosure / Sentiment
from app.domains.news.adapter.inbound.api.news_router import router as news_router
from app.domains.news.adapter.inbound.api.news_collect_router import router as news_collect_router
from app.domains.disclosure.adapter.inbound.api.disclosure_router import router as disclosure_router
from app.domains.sentiment.adapter.inbound.api.sentiment_router import router as sentiment_router

# Misc — Post / Study / Health
from app.domains.post.adapter.inbound.api.post_router import router as post_router
from app.domains.study.adapter.inbound.api.study_router import router as study_router
from app.adapter.inbound.api.health_router import router as health_router

# 모든 API 는 /api/v1 prefix.
api_v1_router = APIRouter(prefix="/api/v1")

# --- Auth & Account ---
api_v1_router.include_router(auth_router)            # /api/v1/auth/{signup,login,session/...,logout/...,me}
api_v1_router.include_router(kakao_auth_router)      # /api/v1/auth/kakao/...
api_v1_router.include_router(account_router)         # /api/v1/account/...
api_v1_router.include_router(users_router)           # /api/v1/users/me/watchlist/...

# --- Agents (causality_agent 는 history_agent 내부 only — 라우터 없음) ---
api_v1_router.include_router(agent_router)           # /api/v1/agent/...           (require_user_or_temp)
api_v1_router.include_router(history_agent_router)   # /api/v1/history-agent/...   (public)
api_v1_router.include_router(investment_router)      # /api/v1/investment/...      (require_user)
api_v1_router.include_router(api_schema_router)      # /api/v1/agent-schema

# --- Market data ---
api_v1_router.include_router(dashboard_router)       # /api/v1/dashboard/...
api_v1_router.include_router(stock_router)           # /api/v1/stock/...
api_v1_router.include_router(stock_theme_router)     # /api/v1/stock-theme/...
api_v1_router.include_router(stocks_router)          # /api/v1/stocks/themes, /api/v1/stocks?theme=
api_v1_router.include_router(macro_router)           # /api/v1/macro/...
api_v1_router.include_router(smart_money_router)     # /api/v1/smart-money/...
api_v1_router.include_router(schedule_router)        # /api/v1/schedule/...

# --- Content ---
api_v1_router.include_router(news_router)            # /api/v1/news/...
api_v1_router.include_router(news_collect_router)    # /api/v1/news/collect/...
api_v1_router.include_router(disclosure_router)      # /api/v1/disclosure/...
api_v1_router.include_router(sentiment_router)       # /api/v1/sentiment/...

# --- Misc ---
api_v1_router.include_router(post_router)            # /api/v1/post/...
api_v1_router.include_router(study_router)           # /api/v1/study/...
api_v1_router.include_router(health_router)          # /api/v1/health/...
