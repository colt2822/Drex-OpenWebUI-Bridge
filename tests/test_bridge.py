import asyncio

import httpx
import pytest

from drex_chat import client, formatter, parser
from drex_chat.app import app


def test_normal_english_hvac_parsing_and_labels():
    prompt = ("My central air conditioner is running, but the house is still 82 degrees and the vents are blowing warm air. "
              "The plumbing and lights are working normally. Which service category best fits this request: HVAC, plumbing, electrical, or something else?")
    parsed = parser.parse_prompt(prompt)
    assert parsed["state"] == prompt
    assert parsed["questions"]["decision"]["criteria"] == {
        "hvac": "HVAC", "plumbing": "plumbing", "electrical": "electrical", "something_else": "something else"
    }


def test_database_choice_normalization_and_display_labels():
    parsed = parser.parse_prompt("Which database should I choose: SQLite, PostgreSQL, MySQL, or MongoDB?")
    assert list(parsed["questions"]["decision"]["criteria"].values()) == ["SQLite", "PostgreSQL", "MySQL", "MongoDB"]
    assert "postgres" in parsed["questions"]["decision"]["criteria"]


def test_formatter_confidence_probabilities_and_tiny_value():
    question = {"criteria": {"hvac": "HVAC", "other": "something else", "electrical": "electrical", "plumbing": "plumbing"}}
    answer = {"choice": "hvac", "confidence": .98, "probabilities": {"hvac": .985, "other": .012, "electrical": .003, "plumbing": .0002}}
    output = formatter.format_answer(question, answer)
    assert "Selected: HVAC" in output and "Decision confidence: 98.0%" in output
    assert "HVAC: 98.5%" in output and "plumbing: <0.1%" in output


@pytest.mark.parametrize("prompt", ["What's the best thing to do here?", "Write an essay about SQLite.", "Should I use Postgres?"])
def test_ambiguous_non_decision_and_yes_no_rejected(prompt):
    with pytest.raises(parser.PromptError):
        parser.parse_prompt(prompt)


def test_rank_score_and_duplicate_choices_rejected():
    with pytest.raises(parser.PromptError, match="rank or score"):
        parser.parse_prompt("Rate these options: local, cloud")
    with pytest.raises(parser.PromptError, match="duplicate"):
        parser.parse_prompt("Which database: SQLite or SQLite?")


def test_provider_response_validation():
    q = {"decision": {"type": "choice", "instructions": "choose", "criteria": {"a": "A", "b": "B"}}}
    payload = {"model": "drex-latest", "answers": {"decision": {"type": "choice", "choice": "a", "confidence": .8, "probabilities": {"a": .8, "b": .2}}}}
    assert client.validate_response(q, payload)
    payload["answers"]["decision"]["choice"] = "invented"
    with pytest.raises(ValueError):
        client.validate_response(q, payload)


@pytest.mark.parametrize("status,kind", [(429, "rate_limited"), (401, "auth_error"), (500, "internal_error")])
def test_provider_status_errors_are_redacted(monkeypatch, status, kind):
    class Response:
        status_code = status
        def json(self): return {"error": {"type": kind, "message": "sensitive"}}
    monkeypatch.setenv("DREX_API_KEY", "nace_sk_" + "x"*43)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: Response())
    with pytest.raises(client.DrexError) as error:
        client.decide("Pick one: A or B", {"decision": {"type": "choice", "instructions": "choose", "criteria": {"a": "A", "b": "B"}}})
    assert error.value.status_code == status and "sensitive" not in str(error.value)


def test_provider_timeout_and_missing_key(monkeypatch):
    monkeypatch.setenv("DREX_API_KEY", "nace_sk_" + "x"*43)
    def timeout(*a, **k): raise httpx.TimeoutException("private credential text")
    monkeypatch.setattr(httpx, "post", timeout)
    q = {"decision": {"type": "choice", "instructions": "choose", "criteria": {"a": "A", "b": "B"}}}
    with pytest.raises(client.DrexError) as error: client.decide("choose: A or B", q)
    assert error.value.kind == "transport_error" and "private" not in str(error.value)
    monkeypatch.delenv("DREX_API_KEY")
    with pytest.raises(client.DrexError) as error: client.decide("choose: A or B", q)
    assert error.value.kind == "credential_unconfigured"


@pytest.mark.anyio
async def test_openwebui_openai_adapter_and_local_rejection(monkeypatch):
    q_result = {"payload": {"model": "drex-latest", "answers": {"decision": {"type": "choice", "choice": "hvac", "confidence": .98, "probabilities": {"hvac": .985, "plumbing": .0002, "electrical": .003, "something_else": .0118}}}}, "latency_ms": 1}
    monkeypatch.setattr(client, "decide", lambda *_: type("R", (), q_result)())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as test_client:
        model_list = await test_client.get("/v1/models")
        assert model_list.json()["data"][0]["id"] == "drex-chat"
        response = await test_client.post("/v1/chat/completions", json={"model": "drex-chat", "messages": [{"role": "user", "content": "Which service: HVAC, plumbing, electrical, or something else?"}]})
        assert "Selected: HVAC" in response.json()["choices"][0]["message"]["content"]
        streamed = await test_client.post("/v1/chat/completions", json={"model": "drex-chat", "stream": True, "messages": [{"role": "user", "content": "Which service: HVAC, plumbing, electrical, or something else?"}]})
        assert "data: [DONE]" in streamed.text and "Selected: HVAC" in streamed.text
        rejected = await test_client.post("/v1/chat/completions", json={"model": "drex-chat", "messages": [{"role": "user", "content": "Write code"}]})
        assert "closed decision" in rejected.json()["choices"][0]["message"]["content"]


@pytest.mark.anyio
async def test_adapter_auth(monkeypatch):
    monkeypatch.setenv("BRIDGE_API_KEY", "bridge-secret")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as test_client:
        denied = await test_client.get("/v1/models")
        allowed = await test_client.get("/v1/models", headers={"Authorization": "Bearer bridge-secret"})
    assert denied.status_code == 401 and allowed.status_code == 200
