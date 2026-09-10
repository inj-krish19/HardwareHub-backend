from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatStartRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class ChatAnswerRequest(BaseModel):
    symptom_id: uuid.UUID
    answer_path: list[str] = Field(default_factory=list)


class ChatStepResponse(BaseModel):
    symptom_id: uuid.UUID | None = None
    kind: str  # "question" | "conclusion" | "escalate" | "clarify"
    message: str
    node_id: str | None = None
    options: list[str] | None = None