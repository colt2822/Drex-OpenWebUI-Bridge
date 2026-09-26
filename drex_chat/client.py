"""Small, validated client for the Nace.AI Drex decision endpoint."""
from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

BASE_URL = "https://drex.nace.ai"
MODEL = "drex-latest"
_KEY = re.compile(r"nace_sk_[A-Za-z0-9_-]{43}\Z")


class DrexError(RuntimeError):
    def __init__(self, status_code: int, kind: str):
        super().__init__(f"Drex request failed ({status_code or 'transport'}; {kind})")
        self.status_code, self.kind = status_code, kind


@dataclass
class Result:
    payload: dict[str, Any]
    latency_ms: float


def _api_key() -> str:
    key = os.getenv("DREX_API_KEY", "").strip()
    if not key:
        raise DrexError(0, "credential_unconfigured")
    if not _KEY.fullmatch(key):
        raise DrexError(0, "credential_format_invalid")
    return key


def _safe_error(response: httpx.Response) -> str:
    try:
        value = response.json().get("error", {}).get("type", "http_error")
        return value if isinstance(value, str) and re.fullmatch(r"[a-z_]{1,64}", value) else "http_error"
    except (ValueError, AttributeError):
        return "http_error"


def validate_request(state: str, questions: dict[str, Any]) -> None:
    if not isinstance(state, str) or not state.strip():
        raise ValueError("state must be non-empty text")
    if not isinstance(questions, dict) or set(questions) != {"decision"}:
        raise ValueError("one decision question is required")
    question = questions["decision"]
    if not isinstance(question, dict) or question.get("type") != "choice" or not isinstance(question.get("instructions"), str):
        raise ValueError("decision must be a typed choice question")
    criteria = question.get("criteria")
    if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 12:
        raise ValueError("decision must contain 2 to 12 choices")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", k) or not isinstance(v, str) for k, v in criteria.items()):
        raise ValueError("invalid choice labels")
    if len(state) > 8000:
        raise ValueError("decision prompt is too long")


def validate_response(questions: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("model") != MODEL:
        raise ValueError("provider response model mismatch")
    answers = payload.get("answers")
    if not isinstance(answers, dict) or set(answers) != {"decision"}:
        raise ValueError("provider response is missing the decision")
    answer = answers["decision"]
    options = questions["decision"]["criteria"]
    probs = answer.get("probabilities") if isinstance(answer, dict) else None
    if answer.get("type") != "choice" or answer.get("choice") not in options or not isinstance(probs, dict) or set(probs) != set(options):
        raise ValueError("provider response contained invalid choices")
    values = list(probs.values())
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in values) or abs(sum(values)-1) > .02:
        raise ValueError("provider response contained invalid probabilities")
    confidence = answer.get("confidence")
    if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        raise ValueError("provider response contained invalid confidence")
    return payload


def decide(state: str, questions: dict[str, Any]) -> Result:
    validate_request(state, questions)
    origin = urlsplit(os.getenv("DREX_BASE_URL", BASE_URL))
    if origin.scheme != "https" or origin.hostname != "drex.nace.ai" or origin.path not in ("", "/") or origin.query or origin.fragment:
        raise DrexError(0, "unverified_api_origin")
    key = _api_key()
    started = time.perf_counter()
    try:
        response = httpx.post(
            BASE_URL + "/v1/systemone", timeout=60,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            json={"model": MODEL, "state": state, "questions": questions},
        )
    except httpx.HTTPError as exc:
        raise DrexError(0, "transport_error") from exc
    finally:
        key = ""
    if response.status_code != 200:
        raise DrexError(response.status_code, _safe_error(response))
    try:
        body = response.json()
        validate_response(questions, body)
    except (ValueError, TypeError, AttributeError) as exc:
        raise DrexError(response.status_code, "invalid_response") from exc
    return Result(body, (time.perf_counter()-started)*1000)
