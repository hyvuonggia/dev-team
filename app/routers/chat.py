from __future__ import annotations

from fastapi import APIRouter, HTTPException

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from app.config import settings

from app.chat_memory import get_history
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENROUTER_API_KEY not set in environment"
        )

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENAI_API_BASE,
    )

    history = get_history(req.session_id)
    history.add_message(HumanMessage(content=req.message))
    messages = history.messages

    try:
        response = await llm.ainvoke(messages)
        history.add_message(AIMessage(content=str(response.content)))
        return ChatResponse(reply=str(response.content), session_id=history.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
