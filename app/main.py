from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import chat, sessions, ba, dev
from app.config import settings
from app.db.database import create_db_and_tables
from app.logging_config import setup_logging
from app.middleware.request_logger import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create database tables and setup logging
    create_db_and_tables()
    setup_logging(
        log_level=settings.LOG_LEVEL,
        log_dir=settings.LOG_DIR,
    )
    yield
    # Shutdown: No cleanup needed for SQLite


def create_app() -> FastAPI:
    app = FastAPI(title="dev-team", version="0.1.0", lifespan=lifespan)

    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

    # Include routers
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(sessions.router, prefix="/api/v1")
    app.include_router(ba.router, prefix="/api/v1")
    app.include_router(dev.router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
