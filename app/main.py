from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routers import chat, sessions, ba, dev
from app.config import settings
from app.db.database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create database tables
    create_db_and_tables()
    yield
    # Shutdown: No cleanup needed for SQLite


def create_app() -> FastAPI:
    app = FastAPI(title="dev-team", version="0.1.0", lifespan=lifespan)

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
