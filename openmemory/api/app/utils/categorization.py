import logging
import os
from pathlib import Path
from typing import List, Optional

import yaml
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()
openai_client = OpenAI()


# --- Custom categories loader (Nolann taxonomy from config/categories.yaml) -----

_custom_categories_cache: Optional[list] = None
_CATEGORIES_PATH = Path(
    os.environ.get("CATEGORIES_CONFIG", "/usr/src/openmemory/config/categories.yaml")
)


def _load_custom_categories() -> list:
    """Load custom categories from YAML config (cached, with local-dev fallback).

    Returns a list of dicts: [{name, description}, ...].
    Empty list if no config file is found (the system falls back to the
    default LLM-driven categorization).
    """
    global _custom_categories_cache
    if _custom_categories_cache is not None:
        return _custom_categories_cache

    path = _CATEGORIES_PATH
    if not path.exists():
        # Local-dev fallback: scripts/seed.py and friends often run with this layout
        alt = Path(__file__).parent.parent.parent.parent / "config" / "categories.yaml"
        if alt.exists():
            path = alt
        else:
            logging.info(f"No custom categories file at {_CATEGORIES_PATH} or {alt}, using default prompt.")
            _custom_categories_cache = []
            return _custom_categories_cache

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cats = data.get("categories", []) or []
        # Validate shape
        cleaned = []
        for c in cats:
            if isinstance(c, dict) and "name" in c:
                cleaned.append({
                    "name": str(c["name"]).strip().lower(),
                    "description": str(c.get("description", "")).strip(),
                })
        _custom_categories_cache = cleaned
        logging.info(f"Loaded {len(cleaned)} custom categories from {path}")
    except Exception as e:
        logging.warning(f"Failed to load custom categories from {path}: {e}. Using default prompt.")
        _custom_categories_cache = []

    return _custom_categories_cache


def reset_custom_categories_cache() -> None:
    """Reset the in-process cache so the next call reloads from disk."""
    global _custom_categories_cache
    _custom_categories_cache = None


def _build_system_prompt() -> str:
    """Build the categorization system prompt, augmented with custom categories if present."""
    custom_cats = _load_custom_categories()
    if not custom_cats:
        return MEMORY_CATEGORIZATION_PROMPT

    categories_block = "\n".join(
        f"- {c['name']}: {c['description']}" for c in custom_cats
    )
    return f"""{MEMORY_CATEGORIZATION_PROMPT}

IMPORTANT: This deployment uses a CUSTOM TAXONOMY. You MUST pick category
names ONLY from the list below. Do NOT invent new categories. If no entry
fits the memory well, use 'inbox' as a fallback (the user will retag later).

CUSTOM CATEGORIES:
{categories_block}

Return 1 to 5 category names from the list above.
"""


class MemoryCategories(BaseModel):
    categories: List[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    try:
        messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": memory},
        ]

        # Let OpenAI handle the pydantic parsing directly
        completion = openai_client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            response_format=MemoryCategories,
            temperature=0,
        )

        parsed: MemoryCategories = completion.choices[0].message.parsed
        return [cat.strip().lower() for cat in parsed.categories]

    except Exception as e:
        logging.error(f"[ERROR] Failed to get categories: {e}")
        try:
            logging.debug(f"[DEBUG] Raw response: {completion.choices[0].message.content}")
        except Exception as debug_e:
            logging.debug(f"[DEBUG] Could not extract raw response: {debug_e}")
        raise
