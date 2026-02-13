from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from app.config import settings


router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENROUTER_API_KEY not set in environment"
        )

    llm = ChatOpenAI(
        model="anthropic/claude-3.5-sonnet",
        openai_api_key=settings.OPENROUTER_API_KEY,
        openai_api_base=settings.OPENAI_API_BASE,
    )

    resp = await llm.apredict(messages=[{"role": "user", "content": req.message}])

    return ChatResponse(reply=str(resp))
