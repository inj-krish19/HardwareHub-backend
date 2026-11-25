from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ChatStartRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class ChatAnswerRequest(BaseModel):
    symptom_id: uuid.UUID
    answer_path: list[str] = Field(default_factory=list)


class ChatConfirmRequest(BaseModel):
    symptom_id: uuid.UUID
    confirmed: bool


class BotSelectionRequest(BaseModel):
    bot_choice: str = Field(..., min_length=1)


class SymptomSelectionRequest(BaseModel):
    title: str = Field(..., min_length=1)


class FeedbackRequest(BaseModel):
    symptom_id: uuid.UUID
    answer_path: list[str] = Field(default_factory=list, max_length=15)
    helpful: bool


class ReportRequest(BaseModel):
    symptom_id: uuid.UUID
    answer_path: list[str] = Field(default_factory=list, max_length=15)


class ReportStep(BaseModel):
    question: str
    answer: str


class ReportResponse(BaseModel):
    title: str
    category: str
    steps: list[ReportStep]
    finding: str
    header: str
    body: str
    text: str


class OutcomeStats(BaseModel):
    helpful: int
    total: int


class ChatStepResponse(BaseModel):
    symptom_id: uuid.UUID | None = None
    kind: str  # "question" | "conclusion" | "escalate" | "clarify"
    message: str
    node_id: str | None = None
    options: list[str] | None = None
    # Only on final answers, and only once enough people have voted to mean something.
    stats: OutcomeStats | None = None