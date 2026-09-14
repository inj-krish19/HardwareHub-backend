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


class BudgetTaskSelectionRequest(BaseModel):
    task_type: str = Field(..., min_length=1)


class BudgetAmountRequest(BaseModel):
    task_type: str = Field(..., min_length=1)
    budget_amount: int = Field(..., gt=0)


class ChatStepResponse(BaseModel):
    symptom_id: uuid.UUID | None = None
    # "task_type" is only ever populated for the Budget/Build Advisor flow —
    # the chatbot stays fully stateless, so the frontend echoes this back on
    # the follow-up /chat/budget-amount call instead of the server holding it.
    task_type: str | None = None
    kind: str  # "question" | "conclusion" | "escalate" | "clarify" | "clarify_bot_choice" | "clarify_list" | "confirm" | "not_found" | "budget_amount_request"
    message: str
    node_id: str | None = None
    options: list[str] | None = None