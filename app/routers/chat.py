from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import message classes from LangChain
from langchain_core.messages import HumanMessage, SystemMessage
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
    # Configure LLM for OpenRouter
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )

    messages = [
        HumanMessage(content=req.message),
    ]

    try:
        response = await llm.ainvoke(messages)
        return ChatResponse(reply=response.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
