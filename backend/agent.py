"""Shopping assistant agent: one LLM, a tool loop, and memory stored in Supabase.

Each user message runs `run_turn` once:
  load history -> loop (LLM -> tools -> LLM ...) until it calls RespondToUser -> save.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

import db
from product_search import SuggestProducts, suggest_products

logger = logging.getLogger(__name__)

MAX_STEPS = 6  # hard cap on LLM calls per user message
MAX_PRODUCTS_SHOWN = 3
FALLBACK_REPLY = "Sorry, I'm having trouble finding that right now. Could you tell me a bit more about what you're looking for?"

SYSTEM_PROMPT = """You are the shopping assistant for a wellness supplement store.
Help the customer find the right product in as few messages as possible.

How to work:
- Search before you ask. Call SuggestProducts as soon as you have any idea what the customer wants, even if it is vague.
- Show at most 3 products. Pick a useful mix (the best match, plus a cheaper or different option) and say in one short sentence why each one fits.
- End with at most ONE question: the one that would narrow the choice down most. Never ask about something the results don't differ on.
- If SuggestProducts returns no results, ask one clarifying question instead of guessing.
- If the customer rejects products, use what they said to search again. Products already shown are excluded from new searches automatically.
- When the customer chooses a product, you may suggest ONE complementary product (search for it), then stop selling.
- Only state facts that come from tool results. Never invent products, prices, ingredients or benefits.
- You are not a doctor. Make no medical claims. For medical conditions, pregnancy or medication, suggest checking with a healthcare professional.
- Always finish by calling RespondToUser on its own, after any other tools have returned."""


class RespondToUser(BaseModel):
    """Send your reply to the customer. This ends your turn. Call it alone, never together with other tools."""

    message: str = Field(description="Your reply. Short, friendly, no markdown headings.")
    product_ids: list[str] = Field(
        default_factory=list,
        description="IDs (from SuggestProducts results) of up to 3 products to show as cards, best first.",
    )
    quick_replies: list[str] = Field(
        default_factory=list,
        description="Up to 4 short answers the customer can tap, e.g. ['Non-drowsy', 'Under £40'].",
    )


@dataclass
class TurnResult:
    conversation_id: str
    reply: str
    products: list[dict] = field(default_factory=list)  # frontend Product shape
    quick_replies: list[str] = field(default_factory=list)


@lru_cache
def get_llm():
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    # tool_choice="required": the model must always call a tool, so every turn ends with RespondToUser.
    return ChatOpenAI(model=model, temperature=0.3, timeout=30, max_retries=2).bind_tools(
        [SuggestProducts, RespondToUser], tool_choice="required"
    )


def run_tool(name: str, args: dict, state: dict) -> dict:
    """Execute one tool call. Errors are returned to the LLM so it can recover."""
    started = time.perf_counter()
    try:
        if name == "SuggestProducts":
            result = suggest_products(SuggestProducts(**args), exclude_ids=state["shown_product_ids"])
        else:
            result = {"error": f"Unknown tool: {name}"}
    except ValidationError as exc:
        logger.warning("Invalid args for %s: %s", name, exc)
        result = {"error": f"Invalid arguments: {exc}"}
    except Exception:
        logger.exception("Tool %s failed", name)
        result = {"error": "Search is temporarily unavailable."}
    logger.info("Tool %s finished in %.0f ms", name, (time.perf_counter() - started) * 1000)
    return result


def finish(conversation: dict, new_messages: list, respond: RespondToUser) -> TurnResult:
    state = conversation["state"]
    # Only show real products from the DB, never IDs the LLM made up.
    product_ids = list(dict.fromkeys(respond.product_ids))[:MAX_PRODUCTS_SHOWN]
    products = db.get_products_by_ids(product_ids)
    if len(products) != len(product_ids):
        logger.warning("Dropped unknown product ids: %s", set(product_ids) - {p["id"] for p in products})

    state["shown_product_ids"] = list(dict.fromkeys(state["shown_product_ids"] + [p["id"] for p in products]))
    db.save_messages(conversation["id"], new_messages)
    db.update_state(conversation["id"], state)

    return TurnResult(
        conversation_id=conversation["id"],
        reply=respond.message,
        products=[db.to_frontend_product(p) for p in products],
        quick_replies=respond.quick_replies[:4],
    )


def run_turn(conversation_id: str | None, user_message: str) -> TurnResult:
    conversation = db.get_or_create_conversation(conversation_id)
    conversation["state"].setdefault("shown_product_ids", [])
    history = db.load_messages(conversation["id"])
    new_messages = [HumanMessage(user_message)]
    logger.info("Turn start conversation=%s history=%d", conversation["id"], len(history))

    for step in range(1, MAX_STEPS + 1):
        ai: AIMessage = get_llm().invoke([SystemMessage(SYSTEM_PROMPT), *history, *new_messages])
        new_messages.append(ai)
        calls = ai.tool_calls
        logger.info("Step %d: tool calls %s", step, [c["name"] for c in calls])

        # Normal exit: the model replied to the user on its own.
        if len(calls) == 1 and calls[0]["name"] == "RespondToUser":
            try:
                respond = RespondToUser(**calls[0]["args"])
            except ValidationError as exc:
                new_messages.append(ToolMessage(f"Invalid reply: {exc}", tool_call_id=calls[0]["id"]))
                continue
            # Every tool call needs a matching tool message, or the next turn's history is invalid.
            new_messages.append(ToolMessage("Delivered.", tool_call_id=calls[0]["id"]))
            logger.info("Turn done in %d steps, showing %s", step, respond.product_ids)
            return finish(conversation, new_messages, respond)

        for call in calls:
            if call["name"] == "RespondToUser":
                result = {"error": "RespondToUser must be called alone, after the other tools return."}
            else:
                result = run_tool(call["name"], call["args"], conversation["state"])
            new_messages.append(ToolMessage(json.dumps(result), tool_call_id=call["id"]))

    # Safety exit: too many steps. Save a clean exchange so history stays valid.
    logger.warning("Hit MAX_STEPS=%d for conversation %s", MAX_STEPS, conversation["id"])
    db.save_messages(conversation["id"], [HumanMessage(user_message), AIMessage(FALLBACK_REPLY)])
    return TurnResult(conversation_id=conversation["id"], reply=FALLBACK_REPLY)
