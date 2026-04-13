"""
schemas/custom.py — Pydantic models for the custom /api/* endpoints.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class NodeStatus(BaseModel):
    id: str
    label: str
    host: str
    port: int
    os: str
    enabled: bool
    tags: list[str]
    status: str
    failure_count: int
    last_seen: Optional[str]
    ollama_version: Optional[str]
    available_models: list[str]
    base_url: str


class ModelEntry(BaseModel):
    name: str
    available_on: list[str]


class PullRequest(BaseModel):
    model: str
    node_ids: Optional[list[str]] = None   # None = all nodes


class PullStatus(BaseModel):
    node_id: str
    model: str
    status: str                            # queued | pulling | done | error
    error: Optional[str] = None
