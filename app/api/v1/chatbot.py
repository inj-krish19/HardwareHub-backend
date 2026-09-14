from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rules import DiagnosisRule, RecommendationRule, Symptom, UseBudgetProfile
from app.rule_engine import router as intent_router
from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_recommendation, format_result
from app.schemas.chatbot import (
    BotSelectionRequest,
    BudgetAmountRequest,
    BudgetTaskSelectionRequest,
    ChatAnswerRequest,
    ChatConfirmRequest,
    ChatStartRequest,
    ChatStepResponse,
    SymptomSelectionRequest,
)

router = APIRouter(prefix="/chat", tags=["chatbot"])

BOT_OPTIONS = [
    "Diagnostic Bot (Broken/misbehaving part)",
    "Compatibility Bot (Part compatibility)",
    "Budget/Build Bot (New PC builds)",
    "Upgrade Bot (Performance upgrades)",
    "Maintenance Bot (Care & cleaning)",
]


@router.post("/start", response_model=ChatStepResponse)
def start_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    intent = intent_router.route(payload.query)

    # Recognized as a different bot's intent (compatibility/budget/etc.) —
    # offer the bot picker rather than guessing further.
    if intent and intent != "diagnostic":
        return ChatStepResponse(
            kind="clarify_bot_choice",
            message=(
                f"It looks like your question is about {intent.replace('_', ' ')}. "
                "Pick the bot that fits, or Diagnostic Bot to search our issue guides directly."
            ),
            options=BOT_OPTIONS,
        )

    # Diagnostic intent (or no clear intent) — try to match an existing symptom.
    symptom = _match_symptom(db, payload.query)
    if symptom is not None:
        return ChatStepResponse(
            symptom_id=symptom.id,
            kind="confirm",
            message=f'Are you asking about: "{symptom.title}"?',
            options=["Yes, that's it", "No, that's not it"],
        )

    # No confident match at all — offer the bot picker.
    return ChatStepResponse(
        kind="clarify_bot_choice",
        message="I'm not quite sure which kind of help you need — pick one below.",
        options=BOT_OPTIONS,
    )


@router.post("/bot-selection", response_model=ChatStepResponse)
def select_bot(payload: BotSelectionRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    if "Diagnostic" in payload.bot_choice:
        symptoms = db.execute(select(Symptom)).scalars().all()
        if not symptoms:
            return ChatStepResponse(
                kind="not_found",
                message="We don't have any diagnostic guides loaded yet — check back soon.",
            )
        return ChatStepResponse(
            kind="clarify_list",
            message="Here are the issues we currently have guides for — pick the closest match.",
            options=[s.title for s in symptoms],
        )

    if "Budget/Build" in payload.bot_choice:
        task_types = db.execute(select(UseBudgetProfile.task_type).distinct()).scalars().all()
        if not task_types:
            return ChatStepResponse(
                kind="not_found",
                message="We don't have any build profiles loaded yet — check back soon.",
            )
        return ChatStepResponse(
            kind="clarify_list",
            message="What will you mainly use this PC for?",
            options=sorted(set(task_types)),
        )

    return ChatStepResponse(
        kind="conclusion",
        message=f"{payload.bot_choice.split(' (')[0]} is coming online this sprint.",
    )


@router.post("/budget-task-selection", response_model=ChatStepResponse)
def select_budget_task(payload: BudgetTaskSelectionRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    """Second step of the Budget/Build Advisor flow — task type is picked
    first (from the distinct task_types actually in the DB), then we ask
    for the budget amount. Stateless like the rest of the chatbot: task_type
    is echoed back to the frontend so it can be sent on the next call."""
    exists = db.execute(
        select(UseBudgetProfile.id).where(UseBudgetProfile.task_type == payload.task_type)
    ).first()
    if exists is None:
        return ChatStepResponse(
            kind="not_found",
            message="We don't have build profiles for that use case yet — check back soon.",
        )
    return ChatStepResponse(
        task_type=payload.task_type,
        kind="budget_amount_request",
        message="What's your approximate budget (in ₹)?",
    )


@router.post("/budget-amount", response_model=ChatStepResponse)
def get_budget_recommendation(payload: BudgetAmountRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    """Final step — looks up the UseBudgetProfile whose range contains the
    given amount for this task_type, then formats its RecommendationRule.
    Simple range + task_type lookup, not a question_tree walk."""
    profile = db.execute(
        select(UseBudgetProfile).where(
            UseBudgetProfile.task_type == payload.task_type,
            UseBudgetProfile.budget_min <= payload.budget_amount,
            UseBudgetProfile.budget_max >= payload.budget_amount,
        )
    ).scalars().first()
    if profile is None:
        return ChatStepResponse(
            kind="not_found",
            message=(
                f"We don't have a build profile for {payload.task_type} at that budget yet — "
                "try a nearby amount or check back soon."
            ),
        )
    rule = db.execute(
        select(RecommendationRule).where(RecommendationRule.profile_id == profile.id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="No recommendation rule found for matched budget profile.")

    formatted = format_recommendation(payload.task_type, payload.budget_amount, rule.component_set)
    return ChatStepResponse(**formatted)


@router.post("/symptom-selection", response_model=ChatStepResponse)
def select_symptom(payload: SymptomSelectionRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    """Explicit pick from the full symptom list — skips the confirm step
    since the user directly chose this exact title, no fuzzy matching involved."""
    symptom = db.execute(
        select(Symptom).where(Symptom.title == payload.title)
    ).scalars().first()
    if symptom is None:
        return ChatStepResponse(
            kind="not_found",
            message="That issue isn't in our guides yet — check back soon.",
        )
    return _start_tree_for_symptom(db, symptom.id)


@router.post("/confirm", response_model=ChatStepResponse)
def confirm_match(payload: ChatConfirmRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    if not payload.confirmed:
        return ChatStepResponse(
            symptom_id=payload.symptom_id,
            kind="not_found",
            message=(
                "Got it — we don't have a guide for that exact issue yet. "
                "We're adding new ones regularly, so check back soon, or try "
                "describing it a different way."
            ),
        )
    return _start_tree_for_symptom(db, payload.symptom_id)


@router.post("/answer", response_model=ChatStepResponse)
def answer_chat(payload: ChatAnswerRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == payload.symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Diagnosis rule not found.")

    try:
        result = tree_walker.answer(rule.question_tree, payload.answer_path)
    except tree_walker.TreeWalkerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    formatted = format_result(result)
    return ChatStepResponse(symptom_id=payload.symptom_id, **formatted)


def _start_tree_for_symptom(db: Session, symptom_id: uuid.UUID) -> ChatStepResponse:
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="No diagnosis rule found for matched symptom.")
    result = tree_walker.start(rule.question_tree)
    formatted = format_result(result)
    return ChatStepResponse(symptom_id=symptom_id, **formatted)


def _match_symptom(db: Session, query: str) -> Symptom | None:
    query_words = set(query.lower().split())
    symptoms = db.execute(select(Symptom)).scalars().all()
    best: tuple[Symptom, int] | None = None
    for symptom in symptoms:
        title_overlap = len(query_words & set(symptom.title.lower().split()))
        keyword_words: set[str] = set()
        if symptom.keywords:
            for phrase in symptom.keywords.split(","):
                keyword_words |= set(phrase.strip().lower().split())
        keyword_overlap = len(query_words & keyword_words)
        score = title_overlap + (keyword_overlap * 2)
        if score and (best is None or score > best[1]):
            best = (symptom, score)
    return best[0] if best else None