import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main4 import run_customer_support_agent

load_dotenv()

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
if _extra_origin:
    _cors_origins.append(_extra_origin)

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
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
def read_root():
    return {"message": "Customer Support API", "chat": "POST /chat"}


@app.post("/chat", response_model=ChatResponse)
def chat(data: ChatRequest):
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    try:
        reply = run_customer_support_agent(data.message.strip())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Agent failed to process the message.",
        ) from exc

    return ChatResponse(reply=reply)
