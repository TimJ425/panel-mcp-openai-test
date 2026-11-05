"""OpenAI-compatible gateway: API-key auth + model allow-list in front of Ollama.

Clients must send `Authorization: Bearer <key>`,
and only the models in ALLOWED_MODELS are listed / callable.
"""
import json
import os
import time

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

API_KEYS = {k.strip() for k in os.environ.get("GATEWAY_API_KEYS", "sk-test-123").split(",") if k.strip()}
MODELS = [m.strip() for m in os.environ.get("ALLOWED_MODELS", "qwen2.5:3b,qwen2.5:1.5b,llama3.2:3b").split(",") if m.strip()]
CONTEXT = int(os.environ.get("MODEL_CONTEXT", "4096"))          # must match OLLAMA_CONTEXT_LENGTH
ENFORCE = os.environ.get("GATEWAY_ENFORCE_CONTEXT", "true").lower() == "true"  # reject like vLLM instead of Ollama's silent truncation
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/v1"

app = FastAPI(title="Fake OpenAI-compatible gateway")
client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5))


def _err(status: int, msg: str, kind: str) -> HTTPException:
    return HTTPException(status, detail={"error": {"message": msg, "type": kind}})


def require_key(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or auth[7:].strip() not in API_KEYS:
        raise _err(401, "Invalid or missing API key", "invalid_api_key")


@app.exception_handler(HTTPException)
async def _http_exc(_, exc: HTTPException):
    body = exc.detail if isinstance(exc.detail, dict) else {"error": {"message": str(exc.detail)}}
    return JSONResponse(body, status_code=exc.status_code)


@app.get("/health")
async def health():
    return {"ok": True, "models": MODELS}


@app.get("/v1/models", dependencies=[Depends(require_key)])
async def list_models():
    now = int(time.time())
    return {"object": "list", "data": [{"id": m, "object": "model", "created": now, "owned_by": "local",
                                       "context_length": CONTEXT, "max_model_len": CONTEXT} for m in MODELS]}


@app.post("/v1/chat/completions", dependencies=[Depends(require_key)])
async def chat(request: Request):
    body = await request.json()
    if body.get("model") not in MODELS:
        raise _err(404, f"Model '{body.get('model')}' not available. Choose from {MODELS}", "model_not_found")

    if ENFORCE:
        # rough token estimate (chars/3); real servers count exactly, this is good enough to exercise the error path
        prompt = len(json.dumps(body.get("messages", []))) // 3 + len(json.dumps(body.get("tools", []))) // 3
        want = prompt + int(body.get("max_tokens") or 0)
        if want > CONTEXT:
            raise _err(400, f"This model's maximum context length is {CONTEXT} tokens. However, you requested {want} tokens "
                            f"({prompt} in the messages, {want - prompt} in the completion).", "context_length_exceeded")

    if body.get("stream"):
        req = client.build_request("POST", f"{OLLAMA}/chat/completions", json=body)
        upstream = await client.send(req, stream=True)

        async def relay():
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(relay(), status_code=upstream.status_code, media_type="text/event-stream")

    r = await client.post(f"{OLLAMA}/chat/completions", json=body)
    return JSONResponse(r.json(), status_code=r.status_code)
