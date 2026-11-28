from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatStartRequest(BaseModel):
    # "typed" is what the person wrote. "photo" is text the browser read from a photo
    # (the photo itself never leaves their device). Photo text is longer and can hold
    # personal details (a username, a PC name), so it is never written to the missed-query log.
    query: str = Field(..., min_length=1, max_length=4000)
    source: Literal["typed", "photo"] = "typed"

    @model_validator(mode="after")
    def _typed_text_is_short(self) -> "ChatStartRequest":
        if self.source == "typed" and len(self.query) > 500:
            raise ValueError("query must be 500 characters or fewer")
        return self
    # "photo" means the text was read from a picture on the person's own device. Such text can
    # hold names, serial numbers and other private details, so it is never written to the
    # missed-query log.
    source: Literal["typed", "photo"] = "typed"


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