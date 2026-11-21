import asyncio
import os
from contextlib import asynccontextmanager
from time import perf_counter_ns
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints, field_validator

load_dotenv()

from gateway import Gateway
from storage import Store
DEFAULT_PROMPT = "You are a helpful assistant."


class Turn(BaseModel):
    session_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    system_prompt: str | None = None

    @field_validator("session_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Session ID cannot be blank")
        return value


def create_app():
    @asynccontextmanager
    async def lifespan(app):
        keys = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]
        if len(set(keys)) < 2:
            raise RuntimeError("Configure at least two distinct LLM_API_KEYS.")
        app.state.store = Store(os.getenv("DATABASE_URL", "sqlite:///./data/app.db"))
        app.state.gateway = Gateway(keys, os.getenv("LLM_MODEL", "openai/gpt-4o-mini"), os.getenv("LLM_API_BASE") or None)
        app.state.simulate = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
        app.state.locks = [asyncio.Lock() for _ in range(128)]
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Simulate-Failure"])

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse({"detail": "service temporarily unavailable"}, status_code=503)

    @app.get("/health")
    def health():
        with app.state.store.connect() as db:
            db.execute("SELECT id FROM messages LIMIT 1").fetchone()
        return {"status": "ok", "keys_configured": len(app.state.gateway.keys), "cache_enabled": True}

    @app.get("/sessions/{session_id}/messages")
    def history(session_id: str):
        prompt, messages = app.state.store.history(session_id)
        if prompt is None:
            raise HTTPException(404, "session not found")
        return {"session_id": session_id, "messages": messages}

    @app.post("/chat")
    async def chat(turn: Turn, x_simulate_failure: Annotated[str | None, Header()] = None):
        start = perf_counter_ns()
        gateway = app.state.gateway
        simulated = {}
        if app.state.simulate and x_simulate_failure:
            allowed = {"*", *(f"key_{i+1}" for i in range(len(gateway.keys)))}
            for pair in x_simulate_failure.split(","):
                key, _, status = pair.strip().partition("=")
                if key not in allowed or status not in {"429", "500", "502", "503"}:
                    raise HTTPException(422, "invalid X-Simulate-Failure")
                simulated[key] = int(status)
        async with app.state.locks[hash(turn.session_id) % len(app.state.locks)]:
            saved_prompt, history = app.state.store.history(turn.session_id)
            prompt = turn.system_prompt if turn.system_prompt is not None else saved_prompt
            if prompt is None:
                prompt = DEFAULT_PROMPT
            messages = [{"role": "system", "content": prompt}]
            messages.extend({"role": m["role"], "content": m["content"]} for m in history)
            messages.append({"role": "user", "content": turn.message})
            answer, meta = await gateway.answer(messages, simulated)
            meta.update({k: v for k, v in answer.items() if k != "reply"})
            meta["latency_ms"] = (perf_counter_ns() - start) // 1_000_000
            app.state.store.save(turn.session_id, prompt, turn.message, answer["reply"], meta)
            return {"session_id": turn.session_id, "reply": answer["reply"], "metadata": meta}
    return app


app = create_app()
