from main3v2 import run_customer_support_agent

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
) 

class ChatRequest(BaseModel):
    message: str


@app.get("/")
def check_server():
    return {"message": "Server is running!"}

@app.post("/chat")
@app.post("/api/chat")
def chat(data: ChatRequest):

    response = run_customer_support_agent(
        user_input=data.message
    )

    return {"reply": response}