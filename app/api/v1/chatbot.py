from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.feedback import GuideFeedback
from app.models.rules import DiagnosisRule, Symptom
from app.rule_engine import router as intent_router
from app.rule_engine import tree_walker
from app.rule_engine.formatter import format_result
from app.rule_engine.matcher import rank_matches
from app.schemas.chatbot import (
    BotSelectionRequest,
    ChatAnswerRequest,
    ChatConfirmRequest,
    ChatStartRequest,
    ChatStepResponse,
    FeedbackRequest,
    OutcomeStats,
    SymptomSelectionRequest,
)

router = APIRouter(prefix="/chat", tags=["chatbot"])

# Button label -> Symptom.bot_type. Order here is the order shown to the user.
BOTS = [
    ("Diagnostic Bot (Broken/misbehaving part)", "diagnostic"),
    ("Compatibility Bot (Part compatibility)", "compatibility"),
    ("Budget/Build Bot (New PC builds)", "budget"),
    ("Upgrade Bot (Performance upgrades)", "upgrade"),
    ("Maintenance Bot (Care & cleaning)", "maintenance"),
]
BOT_OPTIONS = [label for label, _ in BOTS]

# Show "X of Y said this fixed it" only once this many people have voted,
# so two early votes can't read as "100% of people".
MIN_VOTES_TO_SHOW = 5
TERMINAL_KINDS = ("conclusion", "escalate")


def _outcome_key(answer_path: list[str]) -> str:
    return " > ".join(answer_path)


def _stats_for(db: Session, symptom_id: uuid.UUID, answer_path: list[str]) -> OutcomeStats | None:
    total, helpful = db.execute(
        select(func.count(), func.count().filter(GuideFeedback.helpful)).where(
            GuideFeedback.symptom_id == symptom_id,
            GuideFeedback.outcome_key == _outcome_key(answer_path),
        )
    ).one()
    return OutcomeStats(helpful=helpful, total=total) if total >= MIN_VOTES_TO_SHOW else None
BOT_NAMES = {
    "diagnostic": "diagnostic",
    "compatibility": "compatibility",
    "budget": "budget & build",
    "upgrade": "upgrade",
    "maintenance": "maintenance",
}


def _bot_type_from_label(label: str) -> str | None:
    for opt, bot_type in BOTS:
        if label == opt or label.split(" (")[0].lower() == opt.split(" (")[0].lower():
            return bot_type
    return None


def _titles_for_bot(db: Session, bot_type: str) -> list[str]:
    rows = db.execute(
        select(Symptom).where(Symptom.bot_type == bot_type).order_by(Symptom.category, Symptom.title)
    ).scalars().all()
    return [s.title for s in rows]


@router.post("/start", response_model=ChatStepResponse)
def start_chat(payload: ChatStartRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    intent = intent_router.route(payload.query)
    bot = intent_router.INTENT_TO_BOT.get(intent) if intent else None

    # Match across every bot's content; the intent only nudges the score.
    symptoms = db.execute(select(Symptom)).scalars().all()
    matches = rank_matches(payload.query, symptoms, bot, limit=3)
    if matches:
        # Up to three candidates. The widget adds its own "None of these" button;
        # picking one goes through /symptom-selection, and "none" through /confirm
        # with confirmed=false (symptom_id is the top match, which that endpoint ignores).
        return ChatStepResponse(
            symptom_id=matches[0].id,
            kind="suggest",
            message=(
                "Is this what you mean?"
                if len(matches) == 1
                else "I found a few guides that might match. Which one is closest?"
            ),
            options=[m.title for m in matches],
        )

    # No confident match. If the intent told us which bot, jump straight to that
    # bot's guide list instead of making the user pick a bot again.
    if bot:
        titles = _titles_for_bot(db, bot)
        if titles:
            return ChatStepResponse(
                kind="clarify_list",
                message=f"I couldn't find an exact match, but here are our {BOT_NAMES[bot]} guides — pick the closest one.",
                options=titles,
            )

    return ChatStepResponse(
        kind="clarify_bot_choice",
        message="I'm not quite sure which kind of help you need — pick one below.",
        options=BOT_OPTIONS,
    )


@router.post("/bot-selection", response_model=ChatStepResponse)
def select_bot(payload: BotSelectionRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    bot_type = _bot_type_from_label(payload.bot_choice) or "diagnostic"
    titles = _titles_for_bot(db, bot_type)
    if not titles:
        return ChatStepResponse(
            kind="not_found",
            message=f"We don't have {BOT_NAMES[bot_type]} guides loaded yet — check back soon.",
        )
    return ChatStepResponse(
        kind="clarify_list",
        message=f"Here are our {BOT_NAMES[bot_type]} guides — pick the closest match.",
        options=titles,
    )


@router.post("/symptom-selection", response_model=ChatStepResponse)
def select_symptom(payload: SymptomSelectionRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    """Explicit pick from a guide list — skips the confirm step since the user
    chose this exact title, no fuzzy matching involved."""
    symptom = db.execute(
        select(Symptom).where(Symptom.title == payload.title)
    ).scalars().first()
    if symptom is None:
        return ChatStepResponse(
            kind="not_found",
            message="That guide isn't available yet — check back soon.",
        )
    return _start_tree_for_symptom(db, symptom.id)


@router.post("/confirm", response_model=ChatStepResponse)
def confirm_match(payload: ChatConfirmRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    if not payload.confirmed:
        # Not a dead end: let the user browse by bot, and from there the full guide list.
        return ChatStepResponse(
            kind="clarify_bot_choice",
            message=(
                "No problem — let's find it another way. Pick the kind of help you need, "
                "and I'll show every guide we have for it. (If yours isn't there, we're "
                "adding new guides regularly.)"
            ),
            options=BOT_OPTIONS,
        )
    return _start_tree_for_symptom(db, payload.symptom_id)


@router.post("/answer", response_model=ChatStepResponse)
def answer_chat(payload: ChatAnswerRequest, db: Session = Depends(get_db)) -> ChatStepResponse:
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == payload.symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Guide not found.")

    try:
        result = tree_walker.answer(rule.question_tree, payload.answer_path)
    except tree_walker.TreeWalkerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    formatted = format_result(result)
    stats = (
        _stats_for(db, payload.symptom_id, payload.answer_path)
        if formatted["kind"] in TERMINAL_KINDS
        else None
    )
    return ChatStepResponse(symptom_id=payload.symptom_id, stats=stats, **formatted)


@router.post("/feedback", status_code=201)
def submit_feedback(payload: FeedbackRequest, db: Session = Depends(get_db)) -> dict:
    """Anonymous vote on a final answer. The path is replayed through the real
    tree, so only genuine final answers of real guides can be rated."""
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == payload.symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Guide not found.")
    try:
        result = tree_walker.answer(rule.question_tree, payload.answer_path)
    except tree_walker.TreeWalkerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.node_type not in TERMINAL_KINDS:
        raise HTTPException(status_code=400, detail="That is not a final answer yet.")

    db.add(
        GuideFeedback(
            symptom_id=payload.symptom_id,
            outcome_key=_outcome_key(payload.answer_path),
            outcome_kind=result.node_type,
            helpful=payload.helpful,
        )
    )
    db.commit()
    return {"status": "recorded"}


def _start_tree_for_symptom(db: Session, symptom_id: uuid.UUID) -> ChatStepResponse:
    rule = db.execute(
        select(DiagnosisRule).where(DiagnosisRule.symptom_id == symptom_id)
    ).scalars().first()
    if rule is None:
        raise HTTPException(status_code=404, detail="No guide found for the matched topic.")
    result = tree_walker.start(rule.question_tree)
    formatted = format_result(result)
    return ChatStepResponse(symptom_id=symptom_id, **formatted)