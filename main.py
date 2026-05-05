import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapter.inbound.api.v1_router import api_v1_router
from app.common.exception.global_exception_handler import register_exception_handlers
from app.domains.authentication.adapter.inbound.api.authentication_router import (
    router as authentication_router,
)
from app.infrastructure.bootstrap import orm_imports  # noqa: F401
from app.infrastructure.bootstrap.startup_jobs import run_all_bootstraps, start_scheduler
from app.infrastructure.config.langsmith_config import configure_langsmith
from app.infrastructure.config.logging_config import setup_logging
from app.infrastructure.config.settings import Settings, get_settings

setup_logging()
configure_langsmith()

settings: Settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    await run_all_bootstraps()
    scheduler = start_scheduler()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_allowed_frontend_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Cookie", "Set-Cookie"],
)

app.include_router(api_v1_router)
app.include_router(authentication_router)
register_exception_handlers(app)


@app.get("/")
async def root():
    return {"message": "Hello World"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.port)
