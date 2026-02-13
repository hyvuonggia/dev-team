from fastapi import FastAPI
from app.routers import chat
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(title="dev-team", version="0.1.0")
    app.include_router(chat.router, prefix="/api/v1")

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
