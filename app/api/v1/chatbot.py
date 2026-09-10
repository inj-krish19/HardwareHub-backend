from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rules import DiagnosisRule, Symptom
from app.rule_engine import router as intent_router
from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_result
from app.schemas.chatbot import ChatAnswerRequest, ChatStartRequest, ChatStepResponse

router = APIRouter(prefix="/chat", tags=["chatbot"])


@router.post("/start", response_model=ChatStepResponse)
def start_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    intent = intent_router.route(payload.query)
    if intent is None:
        return ChatStepResponse(
            kind="clarify",
            message=(
                "I'm not sure which kind of help you need yet — is this about "
                "a broken/misbehaving part, compatibility between two parts, "
                "a budget build, or an upgrade decision?"
            ),
        )

    if intent != "diagnostic":
        return ChatStepResponse(
            kind="conclusion",
            message=f"Routed to the {intent.replace('_', ' ')} bot — coming online this sprint.",
        )

    symptom = _match_symptom(db, payload.query)
    if symptom is None:
        return ChatStepResponse(
            kind="clarify",
            message="Which component is this about — RAM, storage, GPU, or something else?",
        )

    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == symptom.id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="No diagnosis rule found for matched symptom.")

    result = tree_walker.start(rule.question_tree)
    formatted = format_result(result)
    return ChatStepResponse(symptom_id=symptom.id, **formatted)


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


def _match_symptom(db: Session, query: str) -> Symptom | None:
    query_words = set(query.lower().split())
    symptoms = db.execute(select(Symptom)).scalars().all()
    best: tuple[Symptom, int] | None = None
    for symptom in symptoms:
        overlap = len(query_words & set(symptom.title.lower().split()))
        if overlap and (best is None or overlap > best[1]):
            best = (symptom, overlap)
    return best[0] if best else None