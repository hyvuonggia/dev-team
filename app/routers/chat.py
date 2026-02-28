from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.tracers import LangChainTracer
from app.config import settings

from app.chat_memory import get_history
from app.models.schemas import ChatRequest, ChatResponse
from app.utils.llm_logger import create_llm_callback
from app.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat/stream")
async def chat_stream_endpoint(req: ChatRequest, request: Request):
    """
    Stream chat response token-by-token via SSE (Server-Sent Events).

    This endpoint provides real-time streaming of the LLM response.
    Events are sent in SSE format:
    - token: Each chunk of the response
    - done: When response is complete
    - error: If an error occurs

    Args:
        req: Chat request containing message and session ID.
        request: FastAPI request object for accessing request ID.

    Returns:
        StreamingResponse with text/event-stream media type
    """
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENROUTER_API_KEY not set in environment"
        )

    request_id = getattr(request.state, "request_id", "unknown")

    async def event_generator():
        """Generate SSE events from the LLM stream."""
        try:
            # Setup callbacks
            callbacks = [
                create_llm_callback(
                    model=settings.OPENAI_MODEL, session_id=req.session_id
                )
            ]

            if settings.LANGCHAIN_TRACING_V2 and settings.LANGSMITH_API_KEY:
                tracer = LangChainTracer(
                    project_name=settings.LANGSMITH_PROJECT,
                    client_kwargs={"api_key": settings.LANGSMITH_API_KEY},
                )
                callbacks.append(tracer)

            # Create streaming LLM
            llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENAI_API_BASE,
                streaming=True,  # Enable streaming
                callbacks=callbacks,
            )

            # Get history and add user message
            history = get_history(req.session_id)
            history.add_message(HumanMessage(content=req.message))
            messages = history.messages

            logger.info(
                f"Chat stream request | Session: {req.session_id} | "
                f"Messages: {len(messages)} | RequestID: {request_id}"
            )

            # Send session_id event
            yield f"event: session_id\ndata: {json.dumps({'session_id': history.session_id})}\n\n"

            # Stream the response using astream
            accumulated_content = ""
            async for chunk in llm.astream(messages):
                if chunk.content:
                    accumulated_content += chunk.content
                    yield f"event: token\ndata: {json.dumps({'content': chunk.content})}\n\n"

            # Add the complete response to history
            history.add_message(AIMessage(content=accumulated_content))

            logger.info(
                f"Chat stream complete | Session: {req.session_id} | "
                f"Response length: {len(accumulated_content)} chars | RequestID: {request_id}"
            )

            # Send done event
            yield f"event: done\ndata: {json.dumps({'session_id': history.session_id, 'total_tokens': len(accumulated_content)})}\n\n"

        except Exception as e:
            logger.error(
                f"Chat stream error | Session: {req.session_id} | "
                f"Error: {e} | RequestID: {request_id}",
                exc_info=True,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, request: Request):
    """Process chat message and return response with full logging.

    Args:
        req: Chat request containing message and session ID.
        request: FastAPI request object for accessing request ID.

    Returns:
        Chat response with AI reply and session ID.
    """
    if not settings.OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500, detail="OPENROUTER_API_KEY not set in environment"
        )

    # Get request ID for correlation
    request_id = getattr(request.state, "request_id", "unknown")

    # Setup callbacks for logging and tracing
    callbacks = [
        create_llm_callback(model=settings.OPENAI_MODEL, session_id=req.session_id)
    ]

    # Add LangSmith tracer if configured
    if settings.LANGCHAIN_TRACING_V2 and settings.LANGSMITH_API_KEY:
        tracer = LangChainTracer(
            project_name=settings.LANGSMITH_PROJECT,
            client_kwargs={"api_key": settings.LANGSMITH_API_KEY},
        )
        callbacks.append(tracer)
        logger.info(
            f"LangSmith tracing enabled | Project: {settings.LANGSMITH_PROJECT}"
        )

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENAI_API_BASE,
        callbacks=callbacks,
    )

    history = get_history(req.session_id)
    history.add_message(HumanMessage(content=req.message))
    messages = history.messages

    logger.info(
        f"Chat request | Session: {req.session_id} | "
        f"Messages: {len(messages)} | RequestID: {request_id}"
    )

    try:
        response = await llm.ainvoke(messages)
        history.add_message(AIMessage(content=str(response.content)))

        logger.info(
            f"Chat response | Session: {req.session_id} | "
            f"Response length: {len(str(response.content))} chars | RequestID: {request_id}"
        )

        return ChatResponse(reply=str(response.content), session_id=history.session_id)
    except Exception as e:
        logger.error(
            f"Chat error | Session: {req.session_id} | "
            f"Error: {e} | RequestID: {request_id}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))
