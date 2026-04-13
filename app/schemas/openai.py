"""
schemas/openai.py — Pydantic models that match the OpenAI wire format.

These are used for request validation on /v1/* endpoints and for
constructing well-formed responses that any OpenAI-compatible client
(openai-python SDK, LangChain, LiteLLM, curl, etc.) can consume.

References:
  https://platform.openai.com/docs/api-reference/chat
  https://platform.openai.com/docs/api-reference/completions
  https://platform.openai.com/docs/api-reference/embeddings
"""

from __future__ import annotations

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# ── /v1/models ────────────────────────────────────────────────────────────────

class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "ollama"
    # Extra metadata (not in OAI spec, but useful)
    available_on: list[str] = Field(default_factory=list)


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]


# ── /v1/chat/completions ──────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, list[dict]]] = None
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[Union[str, list[str]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    seed: Optional[int] = None
    tools: Optional[list[dict]] = None
    tool_choice: Optional[Union[str, dict]] = None
    # Pass-through: any extra Ollama-specific params (e.g. num_ctx, num_gpu)
    options: Optional[dict[str, Any]] = None

    class Config:
        extra = "allow"


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# Streaming delta
class ChatDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class ChatStreamChoice(BaseModel):
    index: int = 0
    delta: ChatDelta
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatStreamChoice]


# ── /v1/completions ───────────────────────────────────────────────────────────

class CompletionRequest(BaseModel):
    model: str
    prompt: Union[str, list[str]]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[Union[str, list[str]]] = None
    seed: Optional[int] = None
    options: Optional[dict[str, Any]] = None

    class Config:
        extra = "allow"


class CompletionChoice(BaseModel):
    index: int = 0
    text: str
    finish_reason: Optional[str] = "stop"


class CompletionResponse(BaseModel):
    id: str
    object: Literal["text_completion"] = "text_completion"
    created: int
    model: str
    choices: list[CompletionChoice]
    usage: UsageInfo = Field(default_factory=UsageInfo)


# ── /v1/embeddings ────────────────────────────────────────────────────────────

class EmbeddingRequest(BaseModel):
    model: str
    input: Union[str, list[str]]
    encoding_format: Optional[Literal["float", "base64"]] = "float"

    class Config:
        extra = "allow"


class EmbeddingObject(BaseModel):
    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingObject]
    model: str
    usage: UsageInfo = Field(default_factory=UsageInfo)
