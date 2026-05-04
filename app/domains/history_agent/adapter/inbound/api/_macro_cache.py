"""macro-timeline 엔드포인트의 분산 락 + 캐시 키 helper.

`get_macro_timeline` / `stream_macro_timeline` 두 엔드포인트에서 동일하게
사용되는 cache key 빌드와 SETNX 락 워크플로우를 공유한다.

cache stampede 방지: usecase.execute() 가 LLM 랭커 + FRED + GPR 등을 호출해
cold 계산 시 ~30s 소요. 여러 worker 가 같은 region/period 를 동시에 계산하지
않도록 SETNX 분산 락을 둔다. Redis 장애 시 락 없이 진행 (graceful degrade).
"""

import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# cache key 스키마 버전 (응답 모델 호환 break 시 bump 필요)
CACHE_VERSION = "v1"

LOCK_TTL_SECONDS = 60
WAIT_INTERVAL_SECONDS = 1.0
MAX_WAIT_RETRIES = 30


def build_keys(region: str, lookback: str, limit: int) -> tuple[str, str]:
    """macro-timeline 응답 캐시 키와 분산 락 키를 생성한다.

    반환: ``(cache_key, lock_key)``
    """
    cache_key = f"macro_timeline:{CACHE_VERSION}:{region}:{lookback}:{limit}"
    return cache_key, f"lock:{cache_key}"


async def try_acquire_lock(redis: aioredis.Redis, lock_key: str) -> bool:
    """SETNX 락. Redis 장애 시 graceful (락 없이 진행 — True 반환)."""
    try:
        return bool(await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL_SECONDS))
    except aioredis.RedisError as exc:
        logger.warning("[macro-timeline] 락 획득 실패 (%s): %s — 락 없이 진행", lock_key, exc)
        return True


async def release_lock(redis: aioredis.Redis, lock_key: str) -> None:
    try:
        await redis.delete(lock_key)
    except aioredis.RedisError:
        pass


async def wait_for_cache(redis: aioredis.Redis, cache_key: str) -> Optional[bytes]:
    """다른 worker 가 락을 보유한 경우 캐시가 채워질 때까지 짧게 폴링한다.
    timeout 시 None 을 반환해 호출자가 락 없이 계산을 진행하도록 한다."""
    for _ in range(MAX_WAIT_RETRIES):
        await asyncio.sleep(WAIT_INTERVAL_SECONDS)
        try:
            cached = await redis.get(cache_key)
        except aioredis.RedisError:
            return None
        if cached:
            return cached
    return None
