"""Identity detection REST router (MEM-7).

Routes:
  POST /api/v1/identity/guess     -> rank candidates for a message
  POST /api/v1/identity/confirm   -> record a confirmed (message, user)
  GET  /api/v1/identity/profiles  -> list profiles + sample counts
"""
from typing import List, Optional

from app.database import get_db
from app.models import IdentityProfile, User
from app.services.identity_detector import (ACCEPT_THRESHOLD,
                                            COLD_MENU_THRESHOLD,
                                            confirm as confirm_service,
                                            identify as identify_service)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


class GuessRequest(BaseModel):
    message_text: str


class PredictionItem(BaseModel):
    user_id: str
    confidence: float
    reasoning: str


class GuessResponse(BaseModel):
    predictions: List[PredictionItem]
    top_confidence: float
    top_user_id: Optional[str]
    suggestion: str  # "accept" | "confirm" | "ask_menu"


@router.post("/guess", response_model=GuessResponse)
def guess(req: GuessRequest):
    if not req.message_text or not req.message_text.strip():
        raise HTTPException(status_code=400, detail="message_text required")

    preds = identify_service(req.message_text)
    if not preds:
        raise HTTPException(
            status_code=400,
            detail="No candidates available (no users seeded). Run scripts/seed.py first."
        )

    top = preds[0]
    if top.confidence >= ACCEPT_THRESHOLD:
        suggestion = "accept"
    elif top.confidence >= COLD_MENU_THRESHOLD:
        suggestion = "confirm"
    else:
        suggestion = "ask_menu"

    return GuessResponse(
        predictions=[
            PredictionItem(
                user_id=p.user_id,
                confidence=round(p.confidence, 4),
                reasoning=p.reasoning,
            )
            for p in preds
        ],
        top_confidence=round(top.confidence, 4),
        top_user_id=top.user_id,
        suggestion=suggestion,
    )


class ConfirmRequest(BaseModel):
    user_id: str
    message_text: str
    confidence_at_capture: Optional[float] = None


@router.post("/confirm")
def confirm(req: ConfirmRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{req.user_id}' not found")

    confirm_service(req.user_id, req.message_text, req.confidence_at_capture)
    return {"status": "ok", "user_id": req.user_id}


class ProfileItem(BaseModel):
    user_id: str
    sample_count: int


@router.get("/profiles", response_model=List[ProfileItem])
def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(IdentityProfile).all()
    return [
        ProfileItem(user_id=r.user_id, sample_count=r.sample_count or 0)
        for r in rows
    ]
