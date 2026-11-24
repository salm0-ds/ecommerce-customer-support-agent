"""Supabase access: products, conversations and message history."""

import logging
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict
from supabase import Client, create_client

load_dotenv()
logger = logging.getLogger(__name__)


@lru_cache
def get_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in backend/.env")
    # The client wants the project URL, not the REST endpoint.
    url = url.split("/rest/v1")[0]
    return create_client(url, key)


# ---------------------------------------------------------------
# Products
# ---------------------------------------------------------------

def get_products_by_ids(ids: list[str]) -> list[dict]:
    """Fetch products, keeping the order of `ids`. Unknown ids are dropped."""
    if not ids:
        return []
    rows = get_client().table("products").select("*").in_("id", ids).execute().data
    by_id = {row["id"]: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def to_frontend_product(row: dict) -> dict:
    """Map a products row to the frontend `Product` type (camelCase)."""
    product = {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "shortDescription": row["short_description"],
        "price": float(row["price"]),
        "compareAtPrice": float(row["compare_at_price"]) if row.get("compare_at_price") else None,
        "images": row["images"],
        "category": row["category"],
        "tags": row["tags"],
        "benefits": row["benefits"],
        "ingredients": row["ingredients"],
        "rating": float(row["rating"]),
        "reviewCount": row["review_count"],
        "inStock": row["in_stock"],
        "subscriptionAvailable": row["subscription_available"],
        "subscriptionDiscount": row["subscription_discount"],
        "servings": row["servings"],
        "servingSize": row["serving_size"],
        "certifications": row["certifications"],
    }
    return {k: v for k, v in product.items() if v is not None}  # optional fields are omitted, not null


# ---------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------

def _is_uuid(value: str | None) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def get_or_create_conversation(conversation_id: str | None) -> dict:
    """Return the conversation row, creating a new one if the id is missing or unknown."""
    client = get_client()
    if _is_uuid(conversation_id):
        rows = client.table("conversations").select("*").eq("id", conversation_id).execute().data
        if rows:
            return rows[0]
        logger.info("Conversation %s not found, starting a new one", conversation_id)
    row = client.table("conversations").insert({}).execute().data[0]
    logger.info("Created conversation %s", row["id"])
    return row


def update_state(conversation_id: str, state: dict) -> None:
    get_client().table("conversations").update(
        {"state": state, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", conversation_id).execute()


def load_messages(conversation_id: str) -> list[BaseMessage]:
    rows = (
        get_client()
        .table("messages")
        .select("content")
        .eq("conversation_id", conversation_id)
        .order("id")
        .execute()
        .data
    )
    return messages_from_dict([row["content"] for row in rows])


def save_messages(conversation_id: str, messages: list[BaseMessage]) -> None:
    if not messages:
        return
    rows = [
        {"conversation_id": conversation_id, "role": m.type, "content": d}
        for m, d in zip(messages, messages_to_dict(messages))
    ]
    get_client().table("messages").insert(rows).execute()
