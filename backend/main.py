import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Keep HTTP client noise out of the logs.
for noisy in ("httpx", "httpcore", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("api")

from agent import run_turn  # noqa: E402  (import after logging is configured)

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ecommerce-customer-support-agent.saaim357-a.workers.dev",  # Cloudflare frontend
]
# Extra origins, comma-separated, e.g. FRONTEND_ORIGIN=https://shop.example.com,https://www.shop.example.com
# A trailing slash would never match the browser's Origin header, so it is stripped.
for _origin in os.getenv("FRONTEND_ORIGIN", "").split(","):
    if _origin.strip():
        _cors_origins.append(_origin.strip().rstrip("/"))

app = FastAPI(title="Customer Support API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(max_length=2000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    products: list[dict] = []
    quick_replies: list[str] = []


@app.get("/")
def read_root():
    return {"message": "Customer Support API", "chat": "POST /chat"}


@app.post("/chat", response_model=ChatResponse)
def chat(data: ChatRequest):
    message = data.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        result = run_turn(data.conversation_id, message)
    except ValueError as exc:  # missing config, e.g. env vars
        logger.error("Configuration error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat turn failed for conversation %s", data.conversation_id)
        raise HTTPException(
            status_code=503,
            detail="The assistant is temporarily unavailable. Please try again.",
        ) from exc

    return ChatResponse(
        reply=result.reply,
        conversation_id=result.conversation_id,
        products=result.products,
        quick_replies=result.quick_replies,
    )
