"""매크로 리스크 스냅샷 부트스트랩.

main.py 부팅 시: Redis 영속 캐시가 충분히 신선하면 메모리 store 로 복원해 LLM/
YouTube quota 호출을 회피. 실패 시 호출자가 fresh refresh 를 트리거하도록 False
반환.
"""

import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


async def try_restore_macro_snapshot(max_age_hours: int) -> bool:
    """Redis 매크로 스냅샷이 ``max_age_hours`` 이내면 메모리 store 로 복원.

    프로세스 재시작 / hot-reload 시 YouTube/LLM 재호출을 회피한다.
    복원 성공 시 True, 캐시 없음/만료/파싱 실패 시 False.
    """
    # Lazy import: 매크로 도메인 의존성을 메인 import 에서 끌어올리지 않기 위해.
    from app.domains.macro.adapter.outbound.cache.market_risk_snapshot_store import (
        get_market_risk_snapshot_store,
    )
    from app.domains.macro.application.response.market_risk_judgement_response import (
        MarketRiskJudgementResponse,
    )
    from app.infrastructure.cache.redis_client import redis_client
    from app.infrastructure.scheduler.macro_jobs import MACRO_SNAPSHOT_REDIS_KEY

    try:
        raw = await redis_client.get(MACRO_SNAPSHOT_REDIS_KEY)
        if not raw:
            return False
        payload = json.loads(raw)
        updated_at = datetime.fromisoformat(payload["updated_at"])
        if datetime.now() - updated_at > timedelta(hours=max_age_hours):
            return False
        response = MarketRiskJudgementResponse.model_validate(payload["response"])
        get_market_risk_snapshot_store().set(response, updated_at=updated_at)
        return True
    except Exception as e:
        logger.warning("[Startup] Macro snapshot restore from Redis failed: %s", e)
        return False
