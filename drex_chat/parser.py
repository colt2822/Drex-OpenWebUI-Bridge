"""Deterministic natural-language to Drex choice adapter.

This module deliberately supports only prompts with explicitly supplied options.
It does not call another model or infer a decision schema from open-ended text.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

MAX_PROMPT_CHARS = 8000
MAX_OPTIONS = 12

_NON_DREX = re.compile(r"\b(write|essay|article|summari[sz]e|debug|research|explain|translate)\b", re.I)
_QUESTION = re.compile(r"\b(which|what|should|choose|select|pick|better|best|rate|rank|score)\b", re.I)
_YES_NO = re.compile(r"\bshould\s+(?:i|we|they|you)\b", re.I)
_RANK_SCORE = re.compile(r"\b(rank|rate|score)\b", re.I)


class PromptError(ValueError):
    pass


def classify_prompt(prompt: str) -> str:
    """Return a deterministic task class without contacting Drex."""
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        return "AMBIGUOUS_DECISION"
    if _NON_DREX.search(prompt) and not re.search(r"\b(?:choices|options|or)\b", prompt, re.I):
        return "NON_DREX"
    if _extract_options(prompt):
        return "RANK_OR_SCORE" if _RANK_SCORE.search(prompt) else "EXPLICIT_CHOICE"
    if _YES_NO.search(prompt):
        return "YES_NO"
    if _QUESTION.search(prompt):
        return "AMBIGUOUS_DECISION"
    return "NON_DREX"


def _key(label: str) -> str:
    normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower()
    key = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if key == "postgresql":
        key = "postgres"
    if not key:
        raise PromptError("Each choice must have a usable label.")
    return key


def _extract_options(prompt: str) -> list[str]:
    # Prefer text after a colon; otherwise recognize a final closed list joined by `or`.
    tail = prompt.rsplit(":", 1)[-1] if ":" in prompt else prompt
    if ":" not in prompt:
        match = re.search(r"\b(?:is this|choose between|which of|options are)\b(.+?)(?:\?|$)", prompt, re.I)
        if match:
            tail = match.group(1)
        else:
            return []
    tail = tail.split("?", 1)[0].strip()
    parts = re.split(r"\s*,\s*|\s+or\s+", tail, flags=re.I)
    parts = [re.sub(r"^(?:and|or)\s+", "", p.strip(), flags=re.I) for p in parts]
    parts = [re.sub(r"^[\s\"'`]+|[\s\"'`.,;!?]+$", "", p).strip() for p in parts]
    parts = [p for p in parts if p]
    return parts if len(parts) >= 2 else []


def parse_prompt(prompt: str) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise PromptError("Please enter a short decision prompt with explicit choices.")
    prompt = prompt.strip()
    task_class = classify_prompt(prompt)
    labels = _extract_options(prompt)
    if task_class == "NON_DREX":
        raise PromptError("This doesn't look like a closed decision for Drex. Try phrasing it as a question with choices.")
    if len(labels) > MAX_OPTIONS:
        raise PromptError(f"Please limit the decision to {MAX_OPTIONS} choices.")
    if task_class == "YES_NO":
        raise PromptError("Drex Chat does not yet support yes/no decisions. Give me explicit choices to compare.")
    if task_class == "RANK_OR_SCORE":
        raise PromptError("Drex Chat does not yet support rank or score prompts. Use explicit choices instead.")
    if not labels:
        if not _QUESTION.search(prompt):
            raise PromptError("This doesn't look like a closed decision for Drex. Try phrasing it as a question with choices.")
        raise PromptError("Drex needs a closed decision. Give me the choices you want compared.")
    keys = [_key(label) for label in labels]
    if len(set(keys)) != len(keys):
        raise PromptError("The choices contain duplicate labels after normalization.")
    # Preserve the complete user's wording and all stated context in Drex state.
    state = prompt
    return {
        "state": state,
        "questions": {
            "decision": {
                "type": "choice",
                "instructions": "Which option best fits the user's stated request and requirements?",
                "criteria": dict(zip(keys, labels)),
            }
        },
        "display_labels": dict(zip(keys, labels)),
    }


def format_answer(question: dict[str, Any], answer: dict[str, Any], *, show_probabilities: bool = True) -> str:
    labels = question["criteria"]
    selected = answer["choice"]
    confidence = answer.get("confidence")
    lines = [f"Selected: {labels[selected]}"]
    if isinstance(confidence, (float, int)):
        lines[0] += f"\nDecision confidence: {confidence:.1%}"
    if show_probabilities:
        lines.extend(["", "Probability distribution:"])
        for key, probability in sorted(answer["probabilities"].items(), key=lambda item: item[1], reverse=True):
            value = "<0.1%" if probability < 0.001 else f"{probability:.1%}"
            lines.append(f"- {labels[key]}: {value}")
    return "\n".join(lines)
