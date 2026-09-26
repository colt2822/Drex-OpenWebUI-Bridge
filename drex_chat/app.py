"""OpenAI-compatible API consumed by OpenWebUI's OpenAI connection."""
from __future__ import annotations

import hmac
import os
import time
import uuid
import json
import asyncio

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import client, formatter, parser

app = FastAPI(title="Drex Chat for OpenWebUI", docs_url=None, redoc_url=None)


class Message(BaseModel):
    role: str
    content: str | list


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    stream: bool = False


def _authorize(authorization: str | None) -> None:
    required = os.getenv("BRIDGE_API_KEY", "")
    if required:
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not hmac.compare_digest(supplied, required):
            raise HTTPException(401, "Invalid API key")


def _latest_user(messages: list[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            if isinstance(message.content, str):
                return message.content
            return " ".join(part.get("text", "") for part in message.content if isinstance(part, dict) and part.get("type") == "text")
    raise parser.PromptError("Ask a closed decision and include the choices.")


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)):
    _authorize(authorization)
    return {"object": "list", "data": [{"id": "drex-chat", "object": "model", "created": 0, "owned_by": "nace-ai"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    if request.model != "drex-chat":
        raise HTTPException(404, "Model not found")
    try:
        parsed = parser.parse_prompt(_latest_user(request.messages))
    except parser.PromptError as exc:
        answer = str(exc)
    else:
        try:
            result = await asyncio.to_thread(client.decide, parsed["state"], parsed["questions"])
        except client.DrexError as exc:
            # Never forward provider response bodies, headers, credentials or exception text.
            if exc.status_code == 401 or exc.kind.startswith("credential"):
                answer = "Drex Chat could not authenticate with Drex. Check the server's API key configuration."
            elif exc.status_code == 429:
                answer = "Drex is rate limiting requests right now. Please try again shortly."
            else:
                answer = "Drex is temporarily unavailable. Please try again later."
        else:
            answer = formatter.format_answer(parsed["questions"]["decision"], result.payload["answers"]["decision"])
    response = {"id": "chatcmpl-" + uuid.uuid4().hex, "object": "chat.completion", "created": int(time.time()), "model": "drex-chat", "choices": [{"index": 0, "message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}]}
    if request.stream:
        async def events():
            chunk = {"id": response["id"], "object": "chat.completion.chunk", "created": response["created"], "model": "drex-chat", "choices": [{"index": 0, "delta": {"role": "assistant", "content": answer}, "finish_reason": None}]}
            yield "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n"
            final = {"id": response["id"], "object": "chat.completion.chunk", "created": response["created"], "model": "drex-chat", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield "data: " + json.dumps(final) + "\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(events(), media_type="text/event-stream")
    return JSONResponse(response)
