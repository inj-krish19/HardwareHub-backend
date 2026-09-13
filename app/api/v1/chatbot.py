from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rules import DiagnosisRule, Symptom
from app.rule_engine import router as intent_router
from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_result
from app.schemas.chatbot import (
    BotSelectionRequest,
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

    return ChatStepResponse(
        kind="conclusion",
        message=f"{payload.bot_choice.split(' (')[0]} is coming online this sprint.",
    )


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