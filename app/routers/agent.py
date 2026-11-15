"""
routers/agent.py — POST /api/agent/chat: ask the gateway assistant.

The assistant runs an Ollama tool-calling loop whose tools are the
gateway's own read-only management surfaces (nodes, models, metrics,
fine-tune jobs). Requires a platform API key like every /api route.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.middleware.auth import require_api_key
from app.services import agent as agent_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    model: Optional[str] = None
    history: list[ChatMessage] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    reply: str
    tool_trace: list[dict]
    model: str


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(
    body: AgentChatRequest,
    request: Request,
    api_key: str = Depends(require_api_key),
):
    registry = request.app.state.registry
    try:
        result = await agent_svc.chat(
            registry,
            body.message,
            history=[m.model_dump() for m in body.history],
            model=body.model or agent_svc.DEFAULT_MODEL,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except Exception as exc:
        logger.exception("agent chat failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Agent backend error: {exc}")
    return AgentChatResponse(**result)
