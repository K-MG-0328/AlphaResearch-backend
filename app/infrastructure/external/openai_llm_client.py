from functools import lru_cache

from openai import AsyncOpenAI

from app.infrastructure.config.settings import get_settings
from app.infrastructure.external.llm_client_port import LlmClientPort


class OpenAILlmClient(LlmClientPort):
    def __init__(self, client: AsyncOpenAI, model: str):
        self._client = client
        self._model = model

    async def generate(self, prompt: str) -> str:
        response = await self._client.responses.create(
            model=self._model,
            input=prompt,
        )
        return response.output_text


@lru_cache
def get_openai_llm_client() -> OpenAILlmClient:
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    return OpenAILlmClient(client, model=settings.llm_model_standard)
