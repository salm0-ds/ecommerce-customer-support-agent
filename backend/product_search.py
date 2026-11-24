"""Product search used by the suggest_products tool: hybrid search + relevance threshold."""

import logging
import os
from functools import lru_cache
from typing import Literal

from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field, model_validator

import db

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dims, must match schema.sql
# Cosine similarity a product needs to count as relevant. Tune on your own queries:
# log lines below show the similarity of every candidate.
MIN_SIMILARITY = float(os.getenv("PRODUCT_MIN_SIMILARITY", "0.3"))
MAX_CANDIDATES = 5

Category = Literal["sleep", "gut-health", "focus", "energy", "stress", "hydration"]


class SuggestProducts(BaseModel):
    """Search the catalog for products matching what the customer wants.
    Call this as soon as you have any idea what they want, even if it is vague.
    Products already shown in this conversation are excluded automatically.
    Returns up to 5 relevant candidates, or an empty list if nothing matches well."""

    query: str = Field(
        description="Search phrase combining ALL preferences the customer has stated in this "
        "conversation, e.g. 'non-drowsy stress relief for work anxiety'. Put vague "
        "preferences like 'cheap' or 'natural' here, not in filters."
    )
    category: Category | None = Field(
        default=None, description="Only set if the customer's goal clearly maps to one category."
    )
    min_price: float | None = Field(
        default=None, ge=0, description="Only set if the customer stated an exact minimum price."
    )
    max_price: float | None = Field(
        default=None, ge=0, description="Only set if the customer stated an exact maximum price."
    )

    @model_validator(mode="after")
    def check_prices(self):
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price cannot be greater than max_price")
        return self


@lru_cache
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def build_search_text(product: dict) -> str:
    """The text that represents a product for both keyword and vector search."""
    ingredients = ", ".join(i["name"] for i in product.get("ingredients", []))
    return " | ".join([
        product["name"],
        f"Category: {product['category']}",
        product.get("short_description", ""),
        product.get("description", ""),
        f"Benefits: {', '.join(product.get('benefits', []))}",
        f"Ingredients: {ingredients}",
        f"Tags: {', '.join(product.get('tags', []))}",
        f"Certifications: {', '.join(product.get('certifications', []))}",
    ])


def suggest_products(args: SuggestProducts, exclude_ids: list[str]) -> dict:
    """Run hybrid search and return compact candidates for the LLM to choose from."""
    query_embedding = get_embeddings().embed_query(args.query)

    rows = db.get_client().rpc("search_products", {
        "query_text": args.query,
        "query_embedding": query_embedding,
        "filter_category": args.category,
        "min_price": args.min_price,
        "max_price": args.max_price,
        "exclude_ids": exclude_ids,
    }).execute().data

    for r in rows:
        logger.info("  candidate %s similarity=%.3f score=%.4f", r["id"], r["similarity"] or 0, r["score"])

    relevant = [r for r in rows if (r["similarity"] or 0) >= MIN_SIMILARITY][:MAX_CANDIDATES]
    logger.info(
        "suggest_products query=%r filters=%s -> %d found, %d above threshold",
        args.query, args.model_dump(exclude={"query"}, exclude_none=True), len(rows), len(relevant),
    )

    if not relevant:
        return {"results": [], "note": "No strong matches. Ask the customer one clarifying question."}

    products = db.get_products_by_ids([r["id"] for r in relevant])
    similarity = {r["id"]: round(r["similarity"], 2) for r in relevant}
    # Keep it compact: enough for the LLM to choose and explain, without wasting context.
    return {
        "results": [
            {
                "id": p["id"],
                "name": p["name"],
                "category": p["category"],
                "price": float(p["price"]),
                "short_description": p["short_description"],
                "benefits": p["benefits"],
                "key_ingredients": [i["name"] for i in p["ingredients"]][:4],
                "rating": float(p["rating"]),
                "relevance": similarity[p["id"]],
            }
            for p in products
        ]
    }
