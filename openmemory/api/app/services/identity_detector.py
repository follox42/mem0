"""
Identity Detection Service (MEM-7).

Goal: detect which person (Nolann / Jess / Yoann / Matt / Djamila) is talking
to an OpenMemory agent, based on:
  - Stage 1: vector kNN on confirmed historical messages per user
  - Stage 2: LLM scorer (gpt-4o-mini) when Stage 1 is ambiguous

Returns ranked predictions with confidence in [0, 1].

See openmemory/IDENTITY.md and the KB doc
projects/openmemory-stack/identity-detection-design-and-code.md
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional

from app.database import SessionLocal
from app.models import IdentityMessage, IdentityProfile, User
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

openai_client = OpenAI()

EMBEDDING_MODEL = "text-embedding-3-small"
SCORER_MODEL = "gpt-4o-mini"

# Cold-start threshold: total confirmed samples below this -> LLM-only fallback
COLD_START_THRESHOLD = 10
# Top-1 confidence to accept silently (>=)
ACCEPT_THRESHOLD = 0.85
# Below this -> full menu of 5 choices
COLD_MENU_THRESHOLD = 0.50
# Top1 - Top2 gap below which Stage 2 LLM scorer is triggered
AMBIGUITY_GAP = 0.10


@dataclass
class IdentityPrediction:
    user_id: str
    confidence: float
    reasoning: str
    stage1_score: Optional[float] = None
    stage2_score: Optional[float] = None


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_text(text: str) -> list:
    """Get OpenAI embedding for a text. Returns list of 1536 floats."""
    res = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return res.data[0].embedding


def list_known_users(db: Session) -> List[str]:
    return [u.user_id for u in db.query(User).all()]


# --- Stage 1: vector kNN ---------------------------------------------------

def stage1_vector_knn(db: Session, query_embedding: list) -> List[IdentityPrediction]:
    """For each user, compute max cosine similarity vs their confirmed messages.

    Falls back to profile's embedding_mean if no individual samples exist.
    Returns predictions ranked by stage1_score desc.
    """
    preds = []
    for user_id in list_known_users(db):
        msgs = (db.query(IdentityMessage)
                  .filter(IdentityMessage.user_id == user_id,
                          IdentityMessage.confirmed.is_(True))
                  .order_by(IdentityMessage.created_at.desc())
                  .limit(200)
                  .all())

        if not msgs:
            profile = (db.query(IdentityProfile)
                         .filter(IdentityProfile.user_id == user_id)
                         .first())
            if profile and profile.embedding_mean:
                score = _cosine(query_embedding, profile.embedding_mean)
                preds.append(IdentityPrediction(
                    user_id=user_id,
                    confidence=score,
                    reasoning="profile_mean (no individual samples)",
                    stage1_score=score,
                ))
            else:
                preds.append(IdentityPrediction(
                    user_id=user_id, confidence=0.0,
                    reasoning="no samples", stage1_score=0.0,
                ))
            continue

        best = 0.0
        for m in msgs:
            sim = _cosine(query_embedding, m.embedding)
            if sim > best:
                best = sim

        preds.append(IdentityPrediction(
            user_id=user_id,
            confidence=best,
            reasoning=f"max cosine over {len(msgs)} confirmed samples",
            stage1_score=best,
        ))

    preds.sort(key=lambda p: p.confidence, reverse=True)
    return preds


# --- Stage 2: LLM scorer ---------------------------------------------------

class LLMScoreResponse(BaseModel):
    scores: dict  # {user_id: float in [0,1]}


STAGE2_SYSTEM_PROMPT = """You are an identity classifier for a household memory system.

You will receive:
- A message
- Profiles of 5 candidate persons (style, topics, history)

Score how likely each person wrote that message, in [0.0, 1.0]. Scores need NOT sum to 1.
Be strict: if you have no signal, output low scores across the board.

Return JSON: {"scores": {"nolann": 0.0, "jess": 0.0, "yoann": 0.0, "matt": 0.0, "djamila": 0.0}}
"""


def _profile_summary(user_id: str, profile: Optional[IdentityProfile]) -> str:
    if not profile or profile.sample_count == 0:
        # Hard-coded priors for cold start
        defaults = {
            "nolann": "Owner. Dev/IA/business. Short sentences, English borrowings, direct tone. Topics: code, AI agents, NoCode18, Zephly, trading, OpenFang, MCPs.",
            "jess": "Companion. Warm tone, longer sentences. Topics: daily life, personal projects, family.",
            "yoann": "Brother. Profile to learn from samples.",
            "matt": "Brother. Profile to learn from samples.",
            "djamila": "Mother. Mature tone, less technical vocabulary. Topics: family, health, daily life.",
        }
        return f"samples=0; prior={defaults.get(user_id, 'no prior available')}"

    sig = profile.style_signature or {}
    cats = profile.top_categories or []
    parts = [f"samples={profile.sample_count}"]
    if "avg_sentence_len" in sig:
        parts.append(f"avg_sentence_len={sig['avg_sentence_len']:.1f}")
    if "anglicism_freq" in sig:
        parts.append(f"anglicisms={sig['anglicism_freq']:.2f}/msg")
    if cats:
        parts.append(f"top_categories={', '.join(cats[:5])}")
    return "; ".join(parts)


def stage2_llm_scorer(db: Session, message_text: str, candidates: List[str]) -> dict:
    profiles_block = []
    for user_id in candidates:
        profile = db.query(IdentityProfile).filter(IdentityProfile.user_id == user_id).first()
        profiles_block.append(f"- {user_id}: {_profile_summary(user_id, profile)}")

    user_prompt = f"""Message:
\"\"\"{message_text}\"\"\"

Candidates:
{chr(10).join(profiles_block)}

Score each one 0.0-1.0. Return JSON."""

    try:
        completion = openai_client.beta.chat.completions.parse(
            model=SCORER_MODEL,
            messages=[
                {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format=LLMScoreResponse,
            temperature=0,
        )
        parsed: LLMScoreResponse = completion.choices[0].message.parsed
        return parsed.scores
    except Exception as e:
        logging.warning(f"Stage 2 LLM scorer failed: {e}")
        return {}


# --- Combined detector -----------------------------------------------------

def identify(message_text: str) -> List[IdentityPrediction]:
    """Main entry. Returns ranked predictions for all known users."""
    db = SessionLocal()
    try:
        candidates = list_known_users(db)
        if not candidates:
            return []

        try:
            query_emb = embed_text(message_text)
        except Exception as e:
            logging.warning(f"Embedding failed: {e}, falling back to LLM-only")
            query_emb = None

        # Cold start: very few samples overall -> rely on LLM scorer
        total_msgs = (db.query(IdentityMessage)
                        .filter(IdentityMessage.confirmed.is_(True))
                        .count())
        if total_msgs < COLD_START_THRESHOLD * len(candidates) or query_emb is None:
            llm_scores = stage2_llm_scorer(db, message_text, candidates)
            preds = [
                IdentityPrediction(
                    user_id=uid,
                    confidence=llm_scores.get(uid, 0.0),
                    reasoning=f"cold-start LLM-only (total samples={total_msgs})",
                    stage2_score=llm_scores.get(uid, 0.0),
                )
                for uid in candidates
            ]
            preds.sort(key=lambda p: p.confidence, reverse=True)
            return preds

        # Stage 1: vector kNN
        preds = stage1_vector_knn(db, query_emb)

        # If top-2 are too close, run Stage 2 and blend
        if len(preds) >= 2 and (preds[0].confidence - preds[1].confidence) < AMBIGUITY_GAP:
            logging.info(
                f"Stage 1 ambiguous (gap={preds[0].confidence - preds[1].confidence:.3f}), "
                f"running Stage 2 LLM scorer"
            )
            llm_scores = stage2_llm_scorer(db, message_text, candidates)
            for p in preds:
                s1 = p.stage1_score or 0.0
                s2 = llm_scores.get(p.user_id, 0.0)
                p.stage2_score = s2
                # 60% stage 1, 40% stage 2 (vector signal stronger when it has data)
                p.confidence = 0.6 * s1 + 0.4 * s2
                p.reasoning = f"blended (s1={s1:.2f}, s2={s2:.2f})"
            preds.sort(key=lambda p: p.confidence, reverse=True)

        return preds
    finally:
        db.close()


# --- Confirmation / learning -----------------------------------------------

def confirm(user_id: str, message_text: str, confidence_at_capture: Optional[float] = None) -> None:
    """Record a confirmed (message, user) pair and update the user's profile."""
    db = SessionLocal()
    try:
        try:
            emb = embed_text(message_text)
        except Exception as e:
            logging.warning(f"Embedding failed during confirm: {e}")
            return

        msg = IdentityMessage(
            user_id=user_id,
            message_text=message_text,
            embedding=emb,
            confirmed=True,
            confidence_at_capture=confidence_at_capture,
        )
        db.add(msg)

        # Update profile (running mean of embeddings)
        profile = db.query(IdentityProfile).filter(IdentityProfile.user_id == user_id).first()
        if not profile:
            profile = IdentityProfile(
                user_id=user_id,
                sample_count=1,
                embedding_mean=emb,
                style_signature={},
                top_categories=[],
            )
            db.add(profile)
        else:
            n = profile.sample_count or 0
            old_mean = profile.embedding_mean or [0.0] * len(emb)
            new_mean = [(old_mean[i] * n + emb[i]) / (n + 1) for i in range(len(emb))]
            profile.embedding_mean = new_mean
            profile.sample_count = n + 1

        db.commit()
    except Exception as e:
        logging.exception(f"Error confirming identity for {user_id}: {e}")
        db.rollback()
    finally:
        db.close()
