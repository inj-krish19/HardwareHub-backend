from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.rules import DiagnosisRule, Symptom
from app.rule_engine import router as intent_router
from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_result
from app.schemas.chatbot import ChatAnswerRequest, ChatConfirmRequest, ChatStartRequest, ChatStepResponse

router = APIRouter(prefix="/chat", tags=["chatbot"])


@router.post("/start", response_model=ChatStepResponse)
def start_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    intent = intent_router.route(payload.query)
    
    # If intent router recognizes a non-diagnostic bot intent
    if intent and intent != "diagnostic":
        return ChatStepResponse(
            kind="clarify",
            message=f"It looks like your query is about {intent.replace('_', ' ')}. Which bot can help you with this? Please choose a category or describe your issue specifically for the diagnostic guide.",
            options=["Diagnostic Bot", "Compatibility Bot", "Budget/Build Bot", "Upgrade Bot", "Maintenance Bot"]
        )

    # Check symptom matching for diagnostic intent/queries
    symptom = _match_symptom(db, payload.query)
    if symptom is not None:
        return ChatStepResponse(
            symptom_id=symptom.id,
            kind="confirm",
            message=f'Are you asking about: "{symptom.title}"?',
            options=["Yes, that's it", "No, that's not it"],
        )
    
    # Pattern not matched and no symptom found: use valid schema kind="clarify" to let user pick a bot category first
    return ChatStepResponse(
        kind="clarify",
        message="I'm not quite sure which specialized bot can help with your issue. Which of these areas does your problem fall under?",
        options=[
            "Diagnostic Bot (Broken/misbehaving part)",
            "Compatibility Bot (Part compatibility)",
            "Budget/Build Bot (New PC builds)",
            "Upgrade Bot (Performance upgrades)",
            "Maintenance Bot (Care & cleaning)"
        ],
    )


@router.post("/bot-selection", response_model=ChatStepResponse)
def select_bot(payload: ChatConfirmRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    selected_choice = getattr(payload, "selected_title", "")
    
    if "Diagnostic" in selected_choice or not selected_choice:
        all_symptoms = db.execute(select(Symptom)).scalars().all()
        if all_symptoms:
            options = [s.title for s in all_symptoms] + ["None of the above"]
            return ChatStepResponse(
                kind="clarify_list",
                message="Here are the diagnostic issues we currently have guides for. Select the one related to your problem:",
                options=options,
            )

    return ChatStepResponse(
        kind="conclusion",
        message=f"Routed to the selected bot — coming online this sprint.",
    )


@router.post("/confirm", response_model=ChatStepResponse)
def confirm_match(payload: ChatConfirmRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    if not payload.confirmed:
        return ChatStepResponse(
            kind="not_found",
            message=(
                "Got it — we don't have a guide for that exact issue yet. "
                "We're adding new ones regularly, so check back soon, or try "
                "describing it a different way."
            ),
        )

    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == payload.symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="No diagnosis rule found for matched symptom.")

    result = tree_walker.start(rule.question_tree)
    formatted = format_result(result)
    return ChatStepResponse(symptom_id=payload.symptom_id, **formatted)


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