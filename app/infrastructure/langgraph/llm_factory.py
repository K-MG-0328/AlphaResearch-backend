from functools import lru_cache
from typing import Optional

from langchain_openai import ChatOpenAI

from app.infrastructure.config.settings import get_settings


@lru_cache(maxsize=8)
def get_workflow_llm(model: Optional[str] = None) -> ChatOpenAI:
    """워크플로우 노드에서 공유하는 ChatOpenAI 인스턴스를 반환한다.

    model 미지정 시 settings.llm_model_standard 사용 (기본 gpt-5-mini).
    Phase H1: import-time 상수 제거, 호출 시점에 settings 조회.
    """
    settings = get_settings()
    resolved_model = model or settings.llm_model_standard
    return ChatOpenAI(
        model=resolved_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )
